#!/usr/bin/env python3

import ipaddress, json, math, os, platform, queue, re, shutil
import socket, sqlite3, subprocess, threading, time, uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from flask import Flask, render_template, request, Response, jsonify, stream_with_context

try:
    import requests as http
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

app           = Flask(__name__)
PLATFORM      = platform.system()
DB_PATH       = os.path.join(os.path.dirname(__file__), 'traces.db')
ABUSEIPDB_KEY = os.environ.get('ABUSEIPDB_KEY', '')
_DNS_CACHE    = {}
_IPAPI_CACHE  = {}
_RDAP_CACHE   = {}
_LOCK         = threading.Lock()

# ── DB ────────────────────────────────────────────────────────────────────────
def db_conn(): return sqlite3.connect(DB_PATH, check_same_thread=False)
def init_db():
    with db_conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS traces
            (id TEXT PRIMARY KEY, ts TEXT, target TEXT, resolved TEXT, hops TEXT, stats TEXT)''')
        c.commit()
def db_save(tid, target, resolved, hops, stats):
    with db_conn() as c:
        c.execute('INSERT OR REPLACE INTO traces VALUES (?,?,?,?,?,?)',
            (tid, datetime.now(timezone.utc).isoformat(), target, resolved,
             json.dumps(hops), json.dumps(stats))); c.commit()
def db_list():
    with db_conn() as c:
        rows = c.execute('SELECT id,ts,target,resolved FROM traces ORDER BY ts DESC LIMIT 100').fetchall()
    return [{'id':r[0],'ts':r[1],'target':r[2],'resolved':r[3]} for r in rows]
def db_get(tid):
    with db_conn() as c:
        row = c.execute('SELECT * FROM traces WHERE id=?',(tid,)).fetchone()
    return {'id':row[0],'ts':row[1],'target':row[2],'resolved':row[3],
            'hops':json.loads(row[4] or '[]'),'stats':json.loads(row[5] or '{}')} if row else None
def db_del(tid):
    with db_conn() as c: c.execute('DELETE FROM traces WHERE id=?',(tid,)); c.commit()

# ── IP utils ──────────────────────────────────────────────────────────────────
def parse_addr(ip):
    try: return ipaddress.ip_address(ip)
    except ValueError: return None
def ip_ver(ip):
    a=parse_addr(ip); return a.version if a else None
def is_private(ip):
    a=parse_addr(ip)
    return bool(a and (a.is_private or a.is_loopback or a.is_link_local or a.is_unspecified))
def resolve_target(target):
    a=parse_addr(target)
    if a: return str(a),a.version
    for fam in (socket.AF_INET6,socket.AF_INET):
        try:
            res=socket.getaddrinfo(target,None,fam)
            if res:
                ip=res[0][4][0].split('%')[0]
                a=parse_addr(ip)
                if a: return str(a),a.version
        except: pass
    return target,None
def extract_ip(text):
    m=re.search(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b',text)
    if m and parse_addr(m.group(1)): return m.group(1)
    for raw in text.split():
        t=raw.strip('()').split('%')[0]
        if ':' in t:
            a=parse_addr(t)
            if a and a.version==6: return str(a)
    return None

# ── Enrichment ────────────────────────────────────────────────────────────────
def _cached(cache, key, fn, *args):
    with _LOCK:
        if key in cache: return cache[key]
    r=fn(*args)
    with _LOCK: cache[key]=r
    return r
def reverse_dns(ip):
    def f(ip):
        try: return socket.gethostbyaddr(ip)[0]
        except: return None
    return _cached(_DNS_CACHE,ip,f,ip)
def ip_info(ip):
    def f(ip):
        if not HAS_REQUESTS or is_private(ip): return {}
        try:
            r=http.get(f'http://ip-api.com/json/{ip}',
                params={'fields':'status,org,isp,as,country,countryCode,city,regionName,proxy,hosting,mobile'},timeout=3)
            d=r.json(); return d if d.get('status')=='success' else {}
        except: return {}
    return _cached(_IPAPI_CACHE,ip,f,ip)
def ping_ttl(ip):
    try:
        v6=(ip_ver(ip)==6)
        if PLATFORM=='Windows':
            cmd=['ping','-6' if v6 else '-4','-n','1','-w','1000',ip]
            out=subprocess.check_output(cmd,text=True,timeout=3,stderr=subprocess.DEVNULL)
            m=re.search(r'TTL=(\d+)',out,re.I)
        else:
            wf='-W' if PLATFORM=='Linux' else '-t'
            if v6:
                out=None
                for c in (['ping6','-c','1',wf,'1',ip],['ping','-6','-c','1',wf,'1',ip]):
                    try: out=subprocess.check_output(c,text=True,timeout=3,stderr=subprocess.DEVNULL); break
                    except FileNotFoundError: continue
                if out is None: return None
            else:
                out=subprocess.check_output(['ping','-c','1',wf,'1',ip],text=True,timeout=3,stderr=subprocess.DEVNULL)
            m=re.search(r'(?:ttl|hlim)=(\d+)',out,re.I)
        return int(m.group(1)) if m else None
    except: return None
def os_from_ttl(ttl):
    if ttl is None: return None,None
    if ttl<=64:  return 'Linux / BSD / macOS',f'TTL={ttl}'
    if ttl<=128: return 'Windows NT',f'TTL={ttl}'
    return 'Cisco IOS / JunOS',f'TTL={ttl}'
_CITIES={'lax':'Los Angeles','nyc':'New York','lon':'London','ams':'Amsterdam','fra':'Frankfurt',
         'sfo':'San Francisco','tok':'Tokyo','sin':'Singapore','syd':'Sydney','chi':'Chicago',
         'dal':'Dallas','ash':'Ashburn','iad':'Ashburn','sea':'Seattle','mia':'Miami',
         'atl':'Atlanta','bos':'Boston','par':'Paris','mad':'Madrid','hkg':'Hong Kong',
         'nrt':'Tokyo','icn':'Seoul','gru':'São Paulo','gig':'Rio de Janeiro','scl':'Santiago'}
_CARRIERS={'ntt':'NTT','cogent':'Cogent','telia':'Telia','he.net':'HE.net','hurricane':'HE.net',
           'level3':'Level3','lumen':'Lumen','zayo':'Zayo','tata':'TATA','gtt':'GTT',
           'akamai':'Akamai','cloudflare':'Cloudflare','amazon':'AWS','google':'Google',
           'microsoft':'Microsoft','fastly':'Fastly','hetzner':'Hetzner','ovh':'OVH'}
def analyze_rdns(h):
    if not h: return {}
    hl=h.lower(); info={}
    for c,city in _CITIES.items():
        if re.search(rf'(?<![a-z]){re.escape(c)}(?![a-z])',hl): info['rdns_city']=city; break
    for p,n in _CARRIERS.items():
        if p in hl: info['rdns_carrier']=n; break
    return info
def rdap_whois(ip):
    def f(ip):
        if not HAS_REQUESTS: return None
        for url in [f'https://rdap.arin.net/registry/ip/{ip}',f'https://rdap.db.ripe.net/ip/{ip}',
                    f'https://rdap.apnic.net/ip/{ip}',f'https://rdap.lacnic.net/rdap/ip/{ip}']:
            try:
                r=http.get(url,timeout=6,allow_redirects=True,headers={'Accept':'application/json'})
                if r.status_code==200: return _parse_rdap(r.json())
            except: continue
        return None
    return _cached(_RDAP_CACHE,ip,f,ip)
def _parse_rdap(d):
    res={'handle':d.get('handle'),'name':d.get('name'),
         'cidr':f"{d.get('startAddress','?')} – {d.get('endAddress','?')}",
         'type':d.get('type'),'country':d.get('country'),
         'registrar':None,'abuse_email':None,'remarks':[]}
    for ent in d.get('entities',[]):
        roles=ent.get('roles',[]); vc=ent.get('vcardArray',[[],([])])[1]
        for item in vc:
            if not isinstance(item,list) or len(item)<4: continue
            if item[0]=='fn' and ('registrant' in roles or 'administrative' in roles):
                if not res['registrar']: res['registrar']=item[3]
            if item[0]=='email' and 'abuse' in roles:
                if not res['abuse_email']: res['abuse_email']=item[3]
    for rem in d.get('remarks',[]):
        desc=rem.get('description',[])
        if desc: res['remarks'].append(desc[0])
    return res
def check_abuseipdb(ip):
    if not ABUSEIPDB_KEY or is_private(ip) or not HAS_REQUESTS: return None
    try:
        r=http.get('https://api.abuseipdb.com/api/v2/check',
            params={'ipAddress':ip,'maxAgeInDays':90},
            headers={'Key':ABUSEIPDB_KEY,'Accept':'application/json'},timeout=4)
        if r.status_code==200:
            d=r.json()['data']
            return {'confidence':d.get('abuseConfidenceScore',0),
                    'total_reports':d.get('totalReports',0),
                    'usage_type':d.get('usageType',''),
                    'last_reported':d.get('lastReportedAt',''),
                    'whitelisted':d.get('isWhitelisted',False)}
    except: pass
    return None
def enrich_full(ip):
    with ThreadPoolExecutor(max_workers=5) as ex:
        fd=ex.submit(reverse_dns,ip); fi=ex.submit(ip_info,ip)
        ft=ex.submit(ping_ttl,ip)        if not is_private(ip) else None
        fr=ex.submit(rdap_whois,ip)      if not is_private(ip) else None
        fa=ex.submit(check_abuseipdb,ip) if not is_private(ip) else None
        dns=_sf(fd,5); info=_sf(fi,5) or {}
        ttl=_sf(ft,5) if ft else None; rdap=_sf(fr,8) if fr else None; abuse=_sf(fa,5) if fa else None
    rx=analyze_rdns(dns); os_n,os_b=os_from_ttl(ttl)
    org=info.get('org') or info.get('isp') or rx.get('rdns_carrier') or ('Private Network' if is_private(ip) else None)
    return {'rdns':dns,'rdns_city':rx.get('rdns_city'),'rdns_carrier':rx.get('rdns_carrier'),
            'org':org,'asn':info.get('as'),'country':info.get('country'),
            'country_code':info.get('countryCode'),'city':info.get('city') or rx.get('rdns_city'),
            'region':info.get('regionName'),'ttl':ttl,'os':os_n,'os_basis':os_b,
            'private':is_private(ip),'is_hosting':bool(info.get('hosting')),
            'is_proxy':bool(info.get('proxy')),'is_mobile':bool(info.get('mobile')),
            'rdap':rdap,'abuse':abuse}
def _sf(f,t):
    try: return f.result(timeout=t) if f else None
    except: return None
def enrich_and_queue(hop,q):
    try:
        e=enrich_full(hop['ip']); hop.update(e)
        lats=hop.get('latency_ms',[]); total=hop.get('raw_probes',3); lost=total-len(lats)
        if lats:
            avg=sum(lats)/len(lats)
            hop.update({'avg':round(avg,1),'min_ms':min(lats),'max_ms':max(lats),
                'jitter':jitter(lats),'lat_class':'fast' if avg<20 else('med' if avg<80 else 'slow')})
        else:
            hop.update({'avg':None,'min_ms':None,'max_ms':None,'jitter':None,'lat_class':'none'})
        hop['packet_loss']=round((lost/total)*100) if total else 0
        hop['hop_type']=classify_hop_type(False,hop['private'],hop.get('org'),hop.get('asn'),
            hop.get('is_hosting',False),hop.get('is_proxy',False))
    except Exception as err: hop['enrich_error']=str(err)
    q.put(hop)

# ── Classification ────────────────────────────────────────────────────────────
def classify_hop_type(is_last,private,org,asn,is_hosting,is_proxy):
    if is_last: return 'TARGET'
    if private: return 'GATEWAY'
    o=(org or '').lower()
    for kw in ['cloudflare','akamai','fastly','incapsula','imperva','cdn','edgecast','limelight','stackpath']:
        if kw in o: return 'CDN'
    for kw in ['amazon','aws','microsoft azure','google cloud','digitalocean','linode','vultr','hetzner','ovh','oracle cloud']:
        if kw in o: return 'CLOUD'
    for kw in ['level 3','lumen','cogent','ntt ','telia','hurricane electric','zayo','tata ','gtt ','colt ','sparkle','seabone','centurylink']:
        if kw in o: return 'BACKBONE'
    for kw in ['telecom','cable','comcast','at&t','verizon','charter','spectrum','bt ','telefonica','vodafone','orange ','isp','broadband','telstra','rogers','shaw','tim ','claro','vivo','oi ']:
        if kw in o: return 'ISP'
    if is_hosting: return 'HOSTING'
    if is_proxy:   return 'PROXY'
    return 'TRANSIT'
def jitter(v):
    if len(v)<2: return 0.0
    m=sum(v)/len(v)
    return round(math.sqrt(sum((x-m)**2 for x in v)/len(v)),2)

# ── Parsing ───────────────────────────────────────────────────────────────────
_EMPTY={'avg':None,'min_ms':None,'max_ms':None,'jitter':None,'lat_class':'none',
        'packet_loss':100,'hop_type':'TIMEOUT','private':False,'rdns':None,'org':None,
        'asn':None,'country':None,'country_code':None,'city':None,'region':None,'ttl':None,
        'os':None,'os_basis':None,'is_hosting':False,'is_proxy':False,'is_mobile':False,
        'rdap':None,'abuse':None,'rdns_city':None,'rdns_carrier':None,'ip_version':None}
def parse_hop(line):
    line=line.strip()
    m=re.match(r'^\s*(\d+)\s+(.+)$',line)
    if not m: return None
    n,rest=int(m.group(1)),m.group(2).strip()
    if re.match(r'^(\*\s*){1,3}$',rest) or 'timed out' in rest.lower():
        return {'hop':n,'ip':None,'timeout':True,'latency_ms':[],'raw_probes':3}
    ip=extract_ip(rest)
    if not ip: return None
    lats=[round(float(x),2) for x in re.findall(r'(\d+\.?\d*)\s*ms',rest)]
    stars=len(re.findall(r'\*',rest)); total=len(lats)+stars
    return {'hop':n,'ip':ip,'ip_version':ip_ver(ip),'timeout':False,
            'latency_ms':lats,'raw_probes':total if total>0 else 3}

# ── Trace generator ───────────────────────────────────────────────────────────
def trace_gen(target):
    resolved,ver=resolve_target(target); is_v6=(ver==6)
    yield f"data: {json.dumps({'type':'start','target':target,'resolved':resolved,'ip_version':ver})}\n\n"
    if PLATFORM=='Windows': cmd=['tracert','-d','-h','30','-w','2000',target]
    elif is_v6:
        base=['traceroute6'] if shutil.which('traceroute6') else ['traceroute','-6']
        cmd=base+['-n','-q','3','-w','3','-m','30',target]
    else: cmd=['traceroute','-n','-q','3','-w','3','-m','30',target]
    try:
        proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
        rq=queue.Queue(); pending=0; all_hops=[]
        for raw in proc.stdout:
            raw=raw.rstrip()
            if not raw or not re.match(r'^\s*\d',raw): continue
            while not rq.empty():
                try:
                    en=rq.get_nowait()
                    for i,h in enumerate(all_hops):
                        if h['hop']==en['hop']: all_hops[i]=en; break
                    yield f"data: {json.dumps({'type':'hop_enriched','data':en})}\n\n"; pending-=1
                except queue.Empty: break
            hop=parse_hop(raw)
            if not hop: continue
            all_hops.append(hop.copy())
            if hop['ip']:
                yield f"data: {json.dumps({'type':'hop','data':hop})}\n\n"
                pending+=1; threading.Thread(target=enrich_and_queue,args=(hop.copy(),rq),daemon=True).start()
            else:
                hop.update(_EMPTY); yield f"data: {json.dumps({'type':'hop','data':hop})}\n\n"
        proc.wait()
        deadline=time.time()+22
        while pending>0 and time.time()<deadline:
            try:
                en=rq.get(timeout=0.5)
                for i,h in enumerate(all_hops):
                    if h['hop']==en['hop']: all_hops[i]=en; break
                yield f"data: {json.dumps({'type':'hop_enriched','data':en})}\n\n"; pending-=1
            except queue.Empty: pass
        for h in reversed(all_hops):
            if not h.get('timeout') and h.get('ip'):
                h['hop_type']='TARGET'
                yield f"data: {json.dumps({'type':'retag','hop':h['hop'],'hop_type':'TARGET'})}\n\n"; break
        yield f"data: {json.dumps({'type':'done','hops':len(all_hops),'all_hops':all_hops})}\n\n"
    except FileNotFoundError:
        yield f"data: {json.dumps({'type':'error','msg':'traceroute not found — sudo apt install traceroute'})}\n\n"
    except PermissionError:
        yield f"data: {json.dumps({'type':'error','msg':'permission denied — try: sudo python app.py'})}\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'type':'error','msg':str(exc)})}\n\n"

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route('/')
def index(): return render_template('index.html')
@app.route('/trace')
def trace():
    t=request.args.get('t','').strip()
    if not t:
        def e(): yield f"data: {json.dumps({'type':'error','msg':'no target'})}\n\n"
        return Response(e(),mimetype='text/event-stream')
    return Response(stream_with_context(trace_gen(t)),mimetype='text/event-stream',
        headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})
@app.route('/watch')
def watch():
    t=request.args.get('t','').strip(); iv=max(10,min(300,int(request.args.get('interval',60))))
    if not t:
        def e(): yield f"data: {json.dumps({'type':'error','msg':'no target'})}\n\n"
        return Response(e(),mimetype='text/event-stream')
    def gen():
        rnd=0
        while True:
            rnd+=1; yield f"data: {json.dumps({'type':'watch_round','round':rnd})}\n\n"
            yield from trace_gen(t)
            yield f"data: {json.dumps({'type':'watch_round_done','round':rnd,'next_in':iv})}\n\n"
            for s in range(iv):
                time.sleep(1); yield f"data: {json.dumps({'type':'watch_tick','remaining':iv-s-1})}\n\n"
    return Response(stream_with_context(gen()),mimetype='text/event-stream',
        headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})
@app.route('/history',methods=['GET'])
def h_list(): return jsonify(db_list())
@app.route('/history',methods=['POST'])
def h_save():
    d=request.json; tid=d.get('id') or uuid.uuid4().hex[:8]
    db_save(tid,d['target'],d.get('resolved'),d.get('hops',[]),d.get('stats',{}))
    return jsonify({'id':tid,'saved':True})
@app.route('/history/<tid>',methods=['GET'])
def h_get(tid):
    t=db_get(tid); return jsonify(t) if t else (jsonify({'error':'not found'}),404)
@app.route('/history/<tid>',methods=['DELETE'])
def h_del(tid): db_del(tid); return jsonify({'deleted':True})
@app.route('/whois/<ip>')
def whois(ip): return jsonify(rdap_whois(ip) or {'error':'no data'})
if __name__=='__main__':
    init_db(); app.run(debug=True,host='0.0.0.0',port=5000)
