(() => {
  'use strict';
  const ORDER = [['144p',144],['240p',240],['360p',360],['480p',480],['720p',720],['1080p',1080],['1440p',1440],['4K',2160]];
  let selected = null;
  let lastUrl = '';
  const esc = v => String(v ?? '').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const bytes = n => { n=Number(n||0); if(!n)return ''; const u=['B','KB','MB','GB']; const i=Math.min(Math.floor(Math.log(n)/Math.log(1024)),3); return `${(n/Math.pow(1024,i)).toFixed(i?1:0)} ${u[i]}`; };
  const nativeFetch = window.fetch.bind(window);

  function url(){
    return String(document.querySelector('#url')?.value || document.querySelector('#vlInnerSearch')?.value || document.querySelector('#vlAddress')?.value || '').trim();
  }
  function catalog(v){
    const map=new Map();
    (v?.qualities||[]).forEach(q=>{const h=Number(q.height||0);if(h)map.set(h,{ok:q.available!==false,size:q.filesize||0});});
    (v?.formats||[]).forEach(f=>{const h=Number(f.height||0);if(h>=144&&f.vcodec!=='none')map.set(h,{ok:true,size:f.filesize||f.filesize_approx||0});});
    return ORDER.map(([label,height])=>({label,height,...(map.get(height)||{ok:false,size:0})}));
  }
  function draw(v){
    const list=document.querySelector('#vlQualities'); if(!list)return;
    const data=catalog(v), available=data.filter(q=>q.ok);
    if(!selected || !available.some(q=>q.label===selected)) selected=available.find(q=>q.height===2160)?.label || available[0]?.label || null;
    const head=document.querySelector('.vl-quality-head span'); if(head)head.textContent=available.length?`${available.length} real source qualities`:'No source qualities detected';
    list.innerHTML=data.map(q=>`<button type="button" class="vl-quality ${q.ok?'available':'unavailable'} ${q.label===selected?'selected':''}" data-vl-quality="${q.label}" ${q.ok?'':'disabled'}><span><b>${esc(q.label)}</b>${q.label==='4K'?' · 2160p':''}</span><small>${q.ok?(q.size?bytes(q.size):'Available'):'Not available'}</small></button>`).join('');
    list.querySelectorAll('[data-vl-quality]').forEach(b=>b.onclick=()=>{if(b.disabled)return;selected=b.dataset.vlQuality;list.querySelectorAll('.vl-quality').forEach(x=>x.classList.remove('selected'));b.classList.add('selected');const label=document.querySelector('#qualityLabel');if(label)label.textContent=`${selected} selected`;});
  }
  async function refresh(){
    const u=url(); if(!/^https?:\/\//i.test(u)||u===lastUrl)return; lastUrl=u;
    try{const r=await nativeFetch('/api/info',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:u})});const d=await r.json();if(r.ok&&d.ok&&d.video)draw(d.video);}catch(e){}
  }
  window.fetch=async function(input,init={}){
    let body=init?.body;
    try{const u=typeof input==='string'?input:input?.url||'';if(/\/api\/download(?:$|\/)/.test(u)&&body){const p=JSON.parse(body);if(selected&&p.mode==='video')p.quality=selected;init={...init,body:JSON.stringify(p)}}}catch(e){}
    return nativeFetch(input,init);
  };
  function style(){if(document.querySelector('#manual-quality-v9'))return;const s=document.createElement('style');s.id='manual-quality-v9';s.textContent=`#vlQualities{display:grid!important;grid-template-columns:1fr 1fr!important;gap:8px!important}#vlQualities .vl-quality{display:flex!important;align-items:center!important;justify-content:space-between!important;min-height:44px!important;padding:10px!important}#vlQualities .vl-quality.available{cursor:pointer!important}#vlQualities .vl-quality.selected{background:linear-gradient(100deg,rgba(90,35,255,.55),rgba(20,115,255,.35))!important;border-color:#7d75ff!important}#vlQualities .vl-quality.unavailable{opacity:.32!important;cursor:not-allowed!important}`;document.head.appendChild(s)}
  function boot(){style();refresh();setTimeout(refresh,1200);setTimeout(refresh,3000);document.querySelector('#fetchBtn')?.addEventListener('click',()=>{lastUrl='';setTimeout(refresh,200)});document.querySelector('#vlGo')?.addEventListener('click',()=>{lastUrl='';setTimeout(refresh,500)});document.querySelector('#vlInnerGo')?.addEventListener('click',()=>{lastUrl='';setTimeout(refresh,500)});}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
