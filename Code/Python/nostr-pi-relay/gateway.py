#!/usr/bin/env python3
"""Nostr admission gateway.

Sits between Caddy (TLS) and nostr-rs-relay (loopback only) and enforces the
policy in /etc/nostrgw/policy.json. Requires Python 3.11+, websockets>=14,<16.
coincurve is optional: when installed it is used for fast BIP-340 verification,
otherwise a pure-Python fallback is used (much slower, fine at low volume).
"""
import asyncio, collections, concurrent.futures, hashlib, hmac, ipaddress, json, re, sqlite3, time
from pathlib import Path
from websockets.asyncio.server import serve
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

try:
    from coincurve import PublicKeyXOnly
except ImportError:  # pragma: no cover - depends on host
    PublicKeyXOnly = None

BASE = Path('/var/lib/nostrgw'); POLICY = Path('/etc/nostrgw/policy.json'); STATE = BASE / 'abuse.sqlite3'
BACKEND = 'ws://127.0.0.1:17080'
RATE_WINDOW = 60
CONN = collections.Counter()                       # client network -> open connections
RATES = collections.defaultdict(collections.deque)  # (bucket, key) -> timestamps
MET = collections.Counter()
HEX = re.compile(r'^[0-9a-f]{64}$'); SIG = re.compile(r'^[0-9a-f]{128}$')
# Signature checks and SQLite writes run here so they never stall the event loop.
# Two workers keeps a Pi responsive even if many events arrive at once.
WORKERS = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix='nostrgw')


def policy():
    return json.loads(POLICY.read_text())


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


async def offload(fn, *args):
    return await asyncio.get_running_loop().run_in_executor(WORKERS, fn, *args)


# ---------------------------------------------------------------- abuse state
def db():
    c = sqlite3.connect(STATE, timeout=4)
    c.execute('PRAGMA busy_timeout=4000')
    c.execute('CREATE TABLE IF NOT EXISTS bans (pubkey TEXT PRIMARY KEY, until INTEGER NOT NULL, manual INTEGER DEFAULT 0)')
    c.execute('CREATE TABLE IF NOT EXISTS strikes (pubkey TEXT NOT NULL, at INTEGER NOT NULL)')
    c.execute('CREATE INDEX IF NOT EXISTS strikes_idx ON strikes(pubkey,at)')
    return c


def banned(pk, p):
    if pk in p['blocked_pubkeys']:
        return True
    c = db()
    try:
        a = c.execute('SELECT until FROM bans WHERE pubkey=?', (pk,)).fetchone()
    finally:
        c.close()
    return bool(a and (a[0] == -1 or a[0] > time.time()))


def strike(pk, p):
    if pk in p['trusted_pubkeys']:
        return
    now = int(time.time())
    c = db()
    try:
        with c:
            c.execute('DELETE FROM strikes WHERE at<?', (now - 86400,))
            c.execute('DELETE FROM bans WHERE until!=-1 AND until<?', (now,))
            # Don't generate additional strikes while an existing ban is active
            old = c.execute('SELECT until FROM bans WHERE pubkey=?', (pk,)).fetchone()
            if old and (old[0] == -1 or old[0] > now):
                return
            c.execute('INSERT INTO strikes VALUES (?,?)', (pk, now))
            n = c.execute('SELECT count(*) FROM strikes WHERE pubkey=? AND at>=?', (pk, now - 86400)).fetchone()[0]
            c.execute('INSERT OR REPLACE INTO bans(pubkey,until,manual) VALUES (?,?,0)',
                      (pk, -1 if n >= 3 else now + p['temporary_ban_seconds']))
    finally:
        c.close()


# ------------------------------------------------------------- rate limiting
def client_key(forwarded, p):
    """Caddy overwrites X-Forwarded-For with the real remote address.

    IPv6 clients are grouped by prefix (default /64): a single subscriber
    usually controls a whole /64, so per-address limits would be meaningless.
    """
    try:
        ip = ipaddress.ip_address(forwarded.split(',')[0].strip())
    except ValueError:
        return 'unknown'
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if ip.version == 6:
        return str(ipaddress.ip_network(f'{ip}/{p.get("ipv6_prefix", 64)}', strict=False))
    return str(ip)


def allowed_rate(key, limit, window=RATE_WINDOW):
    now = time.monotonic(); q = RATES[key]
    while q and q[0] < now - window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now); return True


async def janitor():
    """Drop idle rate windows so memory doesn't grow with every new IP/pubkey."""
    while True:
        await asyncio.sleep(120)
        cutoff = time.monotonic() - RATE_WINDOW
        for k in [k for k, q in RATES.items() if not q or q[-1] < cutoff]:
            del RATES[k]


def storage(p):
    root = Path(p['data_path'])
    return sum(x.stat().st_size for x in root.glob('nostr.db*') if x.is_file())


# ----------------------------------------------------------- event checking
def leading_zero_bits(d):
    return 256 - int.from_bytes(d, 'big').bit_length()


# BIP-340 Schnorr signature verification (Nostr NIP-01), stdlib-only fallback.
_FIELD = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_G = (55066263022277343669578718895168534326250603453777594175500187360389116729240, 32670510020758816978083085130507043184471273380659243275938904335757337482424)


def _add(a, b):
    if a is None: return b
    if b is None: return a
    if a[0] == b[0]:
        if (a[1] + b[1]) % _FIELD == 0: return None
        m = (3 * a[0] * a[0]) * pow(2 * a[1], -1, _FIELD) % _FIELD
    else:
        m = (b[1] - a[1]) * pow((b[0] - a[0]) % _FIELD, -1, _FIELD) % _FIELD
    x = (m * m - a[0] - b[0]) % _FIELD
    return (x, (m * (a[0] - x) - a[1]) % _FIELD)


def _mul(n, point):
    out = None
    while n:
        if n & 1: out = _add(out, point)
        point = _add(point, point); n >>= 1
    return out


def _tag_hash(tag, message):
    h = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(h + h + message).digest()


def _verify_py(pk, eid, sig):
    try:
        x = int(pk, 16); r = int(sig[:64], 16); s = int(sig[64:], 16)
        if x >= _FIELD or r >= _FIELD or s >= _ORDER: return False
        y = pow((pow(x, 3, _FIELD) + 7) % _FIELD, (_FIELD + 1) // 4, _FIELD)
        if y * y % _FIELD != (pow(x, 3, _FIELD) + 7) % _FIELD: return False
        if y & 1: y = _FIELD - y
        challenge = int.from_bytes(_tag_hash('BIP0340/challenge', bytes.fromhex(sig[:64]) + bytes.fromhex(pk) + bytes.fromhex(eid)), 'big') % _ORDER
        v = _add(_mul(s, _G), _mul(challenge, (x, (-y) % _FIELD)))
        return v is not None and v[0] == r and v[1] % 2 == 0
    except (ValueError, ZeroDivisionError):
        return False


def verify_signature(pk, eid, sig):
    if PublicKeyXOnly is not None:
        try:
            return PublicKeyXOnly(bytes.fromhex(pk)).verify(bytes.fromhex(sig), bytes.fromhex(eid))
        except Exception:  # invalid point / malformed input
            return False
    return _verify_py(pk, eid, sig)


def check_event(e, p):
    """Cheap checks, including NIP-13 PoW. Signature is verified separately,
    afterwards, so unsolicited junk costs one SHA-256 rather than an EC check.
    Returns a NIP-01 OK reason string or None."""
    if not isinstance(e, dict): return 'invalid: event must be an object'
    try:
        pk = e['pubkey']; eid = e['id']; sig = e['sig']; ts = e['created_at']; kind = e['kind']; tags = e['tags']; content = e['content']
        if not (isinstance(pk, str) and HEX.fullmatch(pk) and isinstance(eid, str) and HEX.fullmatch(eid) and isinstance(sig, str) and SIG.fullmatch(sig)):
            return 'invalid: bad id, pubkey or sig field'
        if type(ts) != int or type(kind) != int or not isinstance(content, str) or not isinstance(tags, list): return 'invalid: bad field types'
        if kind not in p['allowed_kinds']: return f'blocked: kind {kind} not accepted here'
        if kind == 1 and len(content) > p['max_note_characters']: return f'blocked: notes are limited to {p["max_note_characters"]} characters'
        max_tags = p.get('max_tags_by_kind', {}).get(str(kind), p['max_tags'])
        if len(tags) > max_tags: return f'blocked: at most {max_tags} tags for kind {kind}'
        if any(not isinstance(t, list) or len(t) > 8 or any(not isinstance(z, str) or len(z) > 512 for z in t) for t in tags): return 'invalid: malformed tags'
        now = time.time()
        if ts > now + 1800: return 'invalid: created_at is in the future'
        if ts < now - p['max_event_age_seconds']: return 'blocked: event is too old'
        digest = hashlib.sha256(dumps([0, pk, ts, kind, tags, content]).encode()).digest()
        if not hmac.compare_digest(digest.hex(), eid): return 'invalid: event id does not match content'
        if pk not in p['trusted_pubkeys']:
            need = p['min_pow_bits']
            if leading_zero_bits(digest) < need: return f'pow: difficulty {leading_zero_bits(digest)} is less than {need}'
            nonce = [t for t in tags if len(t) >= 3 and t[0] == 'nonce']
            if not nonce or not nonce[-1][1].isdigit() or not nonce[-1][2].isdigit() or not need <= int(nonce[-1][2]) <= leading_zero_bits(digest):
                return f'pow: missing or invalid nonce tag (target must be >= {need})'
        return None
    except (KeyError, ValueError, TypeError, OverflowError, UnicodeEncodeError):
        return 'invalid: malformed event'


def validate_filter(f, p):
    """Only precise lookups: every filter must name authors, ids, #e or #p.
    since/until/kinds narrow a query but don't make it precise on their own."""
    if not isinstance(f, dict) or not f or len(f) > 8 or 'search' in f: return None
    if not any(k in f for k in ('authors', 'ids', '#e', '#p')): return None
    for k, v in f.items():
        if k in ('ids', 'authors', '#e', '#p'):
            if not isinstance(v, list) or not 1 <= len(v) <= 10 or any(not isinstance(x, str) or not HEX.fullmatch(x) for x in v): return None
        elif k == 'kinds':
            if not isinstance(v, list) or not 1 <= len(v) <= 8 or any(type(x) != int or x not in p['allowed_kinds'] for x in v): return None
        elif k in ('since', 'until', 'limit'):
            if type(v) != int or v < 0: return None
        else:
            return None
    f = dict(f); f['limit'] = min(f.get('limit', p['max_limit']), p['max_limit'])
    return f


# ------------------------------------------------------------------ session
async def handler(ws):
    p = policy()
    ip = client_key(ws.request.headers.get('X-Forwarded-For', ''), p)
    # No await between check and increment, so this is race-free on the loop.
    if CONN[ip] >= p['connections_per_ip']:
        MET['rejected_connections'] += 1
        await ws.close(1008, 'connection limit'); return
    CONN[ip] += 1; MET['connections_total'] += 1
    subs = set(); up = None; down = None
    try:
        try:
            up = await connect(BACKEND, max_size=p['max_ws_message_bytes'], open_timeout=5, ping_interval=30)
        except (OSError, asyncio.TimeoutError, ConnectionClosed):
            MET['backend_unavailable'] += 1
            await ws.close(1011, 'relay temporarily unavailable'); return

        async def downstream():
            async for raw in up:
                MET['bytes_out'] += len(raw.encode() if isinstance(raw, str) else raw)
                if isinstance(raw, str) and raw.startswith('["CLOSED"'):
                    try: subs.discard(json.loads(raw)[1])
                    except (ValueError, IndexError, TypeError): pass
                await ws.send(raw)
            await ws.close(1011, 'relay closed the connection')
        down = asyncio.create_task(downstream())

        async def notice(text):
            await ws.send(dumps(['NOTICE', text]))

        async for raw in ws:
            MET['bytes_in'] += len(raw.encode() if isinstance(raw, str) else raw)
            try: msg = json.loads(raw)
            except (ValueError, TypeError):
                MET['rejected'] += 1; await notice('invalid: could not parse message'); continue
            if not isinstance(msg, list) or not msg or not isinstance(msg[0], str):
                MET['rejected'] += 1; await notice('invalid: message must be a JSON array'); continue
            op = msg[0]
            if op == 'EVENT':
                if len(msg) != 2 or not isinstance(msg[1], dict):
                    MET['rejected'] += 1; await notice('invalid: EVENT takes exactly one event object'); continue
                e = msg[1]; pk = e.get('pubkey'); eid = e.get('id') if isinstance(e.get('id'), str) else ''
                reason = None
                if not allowed_rate(('eventip', ip), p['incoming_per_min']): reason = 'rate-limited: too many events from your network'
                if not reason: reason = check_event(e, p)
                if not reason and await offload(banned, pk, p): reason = 'blocked: publisher banned'
                if not reason and storage(p) >= p['stop_bytes']: reason = 'error: relay storage full'
                if not reason and not await offload(verify_signature, pk, eid, e['sig']): reason = 'invalid: bad signature'
                # Strikes only after the signature is proven, so nobody can get someone else's key banned.
                if not reason and not allowed_rate(('pub', pk), p['events_per_min']):
                    reason = 'rate-limited: publishing too fast'; await offload(strike, pk, p)
                if reason:
                    MET['rejected'] += 1
                    await ws.send(dumps(['OK', eid, False, reason])); continue
                MET['forwarded'] += 1
                # Forward exactly what was validated, not the original bytes.
                await up.send(dumps(['EVENT', e]))
            elif op == 'REQ':
                sid = msg[1] if len(msg) >= 2 and isinstance(msg[1], str) else None
                if sid is None or not 1 <= len(sid) <= 64:
                    MET['rejected'] += 1; await notice('invalid: REQ needs a subscription id of 1-64 characters'); continue
                if len(msg) < 3:
                    await ws.send(dumps(['CLOSED', sid, 'invalid: REQ needs at least one filter'])); continue
                if len(msg) - 2 > p['max_filters_per_req']:
                    await ws.send(dumps(['CLOSED', sid, f'blocked: at most {p["max_filters_per_req"]} filters per REQ'])); continue
                if sid not in subs and len(subs) >= p['subscriptions_per_connection']:
                    await ws.send(dumps(['CLOSED', sid, 'blocked: subscription limit'])); continue
                if not allowed_rate(('req', ip), p['subscriptions_per_min']):
                    await ws.send(dumps(['CLOSED', sid, 'rate-limited: subscriptions'])); continue
                filters = [validate_filter(f, p) for f in msg[2:]]
                if any(f is None for f in filters):
                    await ws.send(dumps(['CLOSED', sid, 'blocked: filters must name authors, ids, #e or #p (full 64-char hex)'])); continue
                subs.add(sid)
                await up.send(dumps(['REQ', sid, *filters]))
            elif op == 'CLOSE':
                if len(msg) == 2 and isinstance(msg[1], str):
                    subs.discard(msg[1]); await up.send(dumps(['CLOSE', msg[1]]))
            else:
                MET['rejected'] += 1; await notice(f'unsupported: {op[:16]}')
    except (OSError, ConnectionClosed, asyncio.TimeoutError):
        pass
    finally:
        if down:
            down.cancel(); await asyncio.gather(down, return_exceptions=True)
        if up: await up.close()
        CONN[ip] -= 1
        if CONN[ip] <= 0: del CONN[ip]


async def metrics(reader, writer):
    try:
        await asyncio.wait_for(reader.read(1024), 5)
        p = policy(); data = dict(MET)
        data.update(active_connections=sum(CONN.values()), tracked_rate_keys=len(RATES),
                    storage_bytes=storage(p), fast_signatures=PublicKeyXOnly is not None)
        body = json.dumps(data).encode()
        writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nCache-Control: no-store\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)
        await writer.drain()
    except (OSError, asyncio.TimeoutError):
        pass
    finally:
        writer.close()


async def main():
    BASE.mkdir(exist_ok=True); db().close()
    p = policy()
    janitor_task = asyncio.create_task(janitor())  # keep a reference so it isn't garbage-collected
    async with serve(handler, '127.0.0.1', 17081, max_size=p['max_ws_message_bytes'], max_queue=8, ping_interval=30), \
            await asyncio.start_server(metrics, '127.0.0.1', 17082):
        await asyncio.Future()

if __name__ == '__main__':
    asyncio.run(main())
