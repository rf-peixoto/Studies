/* DungeonFinder report renderer: cave map (two aligned tracks + ruler),
   histogram, and click-to-copy hashes. */
(function(){
  const el = document.getElementById('report-data');
  if(!el) return;
  let data;
  try{ data = JSON.parse(el.textContent); }catch(e){ return; }
  const size = Math.max(1, data.size||1);
  const pct = x => (100*x/size);

  // entropy -> heat color (matches the section-table pills)
  function heat(e){
    if(e>=6.5) return '#ff2e88';        // magenta: packed/encrypted
    if(e>=3)   return '#ffb020';         // amber: mixed
    return '#17e0d6';                    // cyan: low / padding / text
  }
  function hx(n){ return '0x'+Math.round(n).toString(16); }

  // ---- sections track ----
  const secTrack = document.getElementById('trackSections');
  if(secTrack){
    (data.sections||[]).forEach(s=>{
      if(!s.size) return;
      const w = Math.max(0.3, pct(s.size));
      const d=document.createElement('div');
      d.className='block sec';
      d.style.left=pct(s.offset)+'%';
      d.style.width=w+'%';
      d.style.background=heat(s.entropy);
      d.title=`${s.name}\noffset ${s.offset_hex}  size ${s.size.toLocaleString()} B\nentropy ${s.entropy.toFixed(2)}`;
      if(w>=7){                                   // only label when wide enough
        const lbl=document.createElement('span');
        lbl.className='blabel'; lbl.textContent=s.name;
        d.appendChild(lbl);
      }
      secTrack.appendChild(d);
    });
  }

  // ---- ruler ----
  const ruler=document.getElementById('ruler');
  if(ruler){
    for(let i=0;i<=8;i++){
      const t=document.createElement('div');
      t.className='tick'; t.style.left=(i*12.5)+'%';
      const lab=document.createElement('span');
      lab.textContent=hx(size*i/8);
      if(i===0) lab.style.transform='none';
      if(i===8) lab.style.transform='translateX(-100%)';
      t.appendChild(lab); ruler.appendChild(t);
    }
  }

  // ---- caves track ----
  const caveTrack=document.getElementById('trackCaves');
  if(caveTrack){
    (data.caves||[]).forEach(c=>{
      const d=document.createElement('div');
      d.className='block cave'+(c.is_code?' codey':'');
      d.style.left=pct(c.offset)+'%';
      d.style.width=Math.max(0.25,pct(c.size))+'%';
      d.title=`cave @ ${c.offset_hex} → ${c.end_hex}\nsize ${c.size.toLocaleString()} B  · ${c.section}`
             +(c.is_code? '\nclassified: code-like':'');
      caveTrack.appendChild(d);
    });
    if(!(data.caves||[]).length){
      const empty=document.createElement('div');
      empty.className='mapempty'; empty.textContent='no caves in range';
      caveTrack.appendChild(empty);
    }
  }

  // ---- histogram ----
  const hist = document.getElementById('hist');
  if(hist && data.histogram && data.histogram.length){
    const max = Math.max(1, ...data.histogram.map(h=>h.count));
    data.histogram.forEach(h=>{
      const row=document.createElement('div'); row.className='hrow';
      const label=document.createElement('div'); label.className='hlabel';
      label.textContent=fmt(h.range[0])+'–'+fmt(h.range[1])+' B';
      const bar=document.createElement('div'); bar.className='hbar';
      const i=document.createElement('i'); i.style.width=(100*h.count/max)+'%'; bar.appendChild(i);
      const cnt=document.createElement('div'); cnt.className='hcount'; cnt.textContent=h.count;
      row.append(label,bar,cnt); hist.appendChild(row);
    });
  }
  function fmt(n){ return n>=1024 ? (n/1024).toFixed(n%1024?1:0)+'K' : n; }

  // ---- click-to-copy hashes ----
  document.querySelectorAll('.hval').forEach(node=>{
    node.style.cursor='pointer';
    node.addEventListener('click',()=>{
      const v=node.dataset.copy||node.textContent;
      const done=()=>{ node.classList.add('copied'); setTimeout(()=>node.classList.remove('copied'),900); };
      if(navigator.clipboard && navigator.clipboard.writeText){
        navigator.clipboard.writeText(v).then(done).catch(fallback);
      } else fallback();
      function fallback(){
        const ta=document.createElement('textarea'); ta.value=v; document.body.appendChild(ta);
        ta.select(); try{document.execCommand('copy');}catch(e){} ta.remove(); done();
      }
    });
  });
})();
