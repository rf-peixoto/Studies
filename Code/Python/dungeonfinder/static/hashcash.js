/* DungeonFinder adaptive hashcash solver.
   Fetches a signed challenge, then brute-forces a nonce whose
   sha256(token:bits:ts:nonce) has >= `bits` leading zero bits.

   Uses a self-contained SHA-256 (no Web Crypto), so it works over plain HTTP
   on a LAN/IP where crypto.subtle is unavailable (non-secure context). */
(function(){
  // ---- SHA-256 (pure JS, operates on a Uint8Array, returns Uint8Array(32)) ----
  const K=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
  const w=new Uint32Array(64);
  function sha256(msg){
    let H0=0x6a09e667,H1=0xbb67ae85,H2=0x3c6ef372,H3=0xa54ff53a,
        H4=0x510e527f,H5=0x9b05688c,H6=0x1f83d9ab,H7=0x5be0cd19;
    const l=msg.length, bitLen=l*8;
    const withOne=l+1, padLen=(withOne%64<=56)?(56-withOne%64):(120-withOne%64);
    const total=withOne+padLen+8;
    const m=new Uint8Array(total);
    m.set(msg); m[l]=0x80;
    m[total-4]=(bitLen>>>24)&0xff; m[total-3]=(bitLen>>>16)&0xff; m[total-2]=(bitLen>>>8)&0xff; m[total-1]=bitLen&0xff;
    for(let i=0;i<total;i+=64){
      for(let t=0;t<16;t++) w[t]=(m[i+4*t]<<24)|(m[i+4*t+1]<<16)|(m[i+4*t+2]<<8)|(m[i+4*t+3]);
      for(let t=16;t<64;t++){
        const a=w[t-15],b=w[t-2];
        const s0=((a>>>7)|(a<<25))^((a>>>18)|(a<<14))^(a>>>3);
        const s1=((b>>>17)|(b<<15))^((b>>>19)|(b<<13))^(b>>>10);
        w[t]=(w[t-16]+s0+w[t-7]+s1)|0;
      }
      let a=H0,b=H1,c=H2,d=H3,e=H4,f=H5,g=H6,h=H7;
      for(let t=0;t<64;t++){
        const S1=((e>>>6)|(e<<26))^((e>>>11)|(e<<21))^((e>>>25)|(e<<7));
        const ch=(e&f)^(~e&g);
        const t1=(h+S1+ch+K[t]+w[t])|0;
        const S0=((a>>>2)|(a<<30))^((a>>>13)|(a<<19))^((a>>>22)|(a<<10));
        const maj=(a&b)^(a&c)^(b&c);
        const t2=(S0+maj)|0;
        h=g;g=f;f=e;e=(d+t1)|0;d=c;c=b;b=a;a=(t1+t2)|0;
      }
      H0=(H0+a)|0;H1=(H1+b)|0;H2=(H2+c)|0;H3=(H3+d)|0;
      H4=(H4+e)|0;H5=(H5+f)|0;H6=(H6+g)|0;H7=(H7+h)|0;
    }
    const out=new Uint8Array(32), Hs=[H0,H1,H2,H3,H4,H5,H6,H7];
    for(let i=0;i<8;i++){ out[4*i]=(Hs[i]>>>24)&0xff; out[4*i+1]=(Hs[i]>>>16)&0xff; out[4*i+2]=(Hs[i]>>>8)&0xff; out[4*i+3]=Hs[i]&0xff; }
    return out;
  }

  const encoder = new TextEncoder();
  function leadingZeroBits(bytes){
    let bits=0;
    for(const b of bytes){
      if(b===0){ bits+=8; continue; }
      bits += 8 - (32 - Math.clz32(b));   // clz32 of an 8-bit value -> leading zeros in that byte
      break;
    }
    return bits;
  }

  async function getChallenge(){
    const r = await fetch('/api/challenge', {headers:{'X-Requested-With':'DungeonFinder'}});
    if(!r.ok) throw new Error('could not fetch challenge');
    return r.json();
  }

  async function solve(ch, ui){
    const prefix = ch.token+':'+ch.bits+':'+ch.ts+':';
    const target = ch.bits;
    const est = Math.pow(2, target);
    let nonce=0, checked=0, last=performance.now();
    if(ui && ui.powEl){ ui.powEl.classList.add('active'); ui.labelEl.textContent='PROOF-OF-WORK // '+target+' BITS'; }
    while(true){
      // hash a batch synchronously, then yield to the event loop
      for(let k=0;k<2000;k++){
        const bytes = sha256(encoder.encode(prefix+nonce));
        if(leadingZeroBits(bytes) >= target){
          if(ui){ ui.barEl.style.width='100%'; ui.statEl.textContent='solved'; }
          return String(nonce);
        }
        nonce++; checked++;
      }
      const now=performance.now();
      if(now-last>80){
        last=now;
        const pct=Math.min(99, Math.round(100*checked/est));
        if(ui){ ui.barEl.style.width=pct+'%'; ui.statEl.textContent=checked.toLocaleString()+' hashes'; }
      }
      await new Promise(r=>setTimeout(r,0));
    }
  }

  async function solveInto(form, ui){
    const ch = await getChallenge();
    const nonce = await solve(ch, ui);
    form.hc_token.value=ch.token; form.hc_bits.value=ch.bits;
    form.hc_ts.value=ch.ts; form.hc_sig.value=ch.sig; form.hc_nonce.value=nonce;
  }

  window.DungeonHashcash={solveInto, solve, getChallenge, _sha256:sha256};
})();
