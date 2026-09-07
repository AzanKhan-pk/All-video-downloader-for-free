(() => {
  'use strict';
  const ORDER = [['144p',144],['240p',240],['360p',360],['480p',480],['720p',720],['1080p',1080],['1440p',1440],['4K',2160]];
  let latestVideo = null;
  let selected = null;
  const nativeFetch = window.fetch.bind(window);
  const esc = v => String(v ?? '').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const bytes = n => { n=Number(n||0); if(!n)return ''; const u=['B','KB','MB','GB']; const i=Math.min(Math.floor(Math.log(n)/Math.log(1024)),3); return `${(n/Math.pow(1024,i)).toFixed(i?1:0)} ${u[i]}`; };

  window.fetch = async function(input, init={}) {
    let body = init && init.body;
    try {
      const url = typeof input === 'string' ? input : input?.url || '';
      if (/\/api\/download(?:$|\/)/.test(url) && body) {
        const payload = JSON.parse(body);
        if (selected && payload.mode === 'video') payload.quality = selected;
        init = {...init, body: JSON.stringify(payload)};
      }
    } catch (_) {}
    const response = await nativeFetch(input, init);
    try {
      const url = typeof input === 'string' ? input : input?.url || '';
      if (/\/api\/info$/.test(url) && response.ok) {
        const clone = response.clone();
        clone.json().then(data => {
          if (data?.ok && data.video) { latestVideo = data.video; setTimeout(render, 0); }
        }).catch(()=>{});
      }
    } catch (_) {}
    return response;
  };

  function catalog(video) {
    const map = new Map();
    (video?.qualities || []).forEach(q => {
      const h = Number(q.height || 0); if(h) map.set(h,{available:q.available !== false,size:q.filesize||0});
    });
    (video?.formats || []).forEach(f => {
      const h=Number(f.height||0); if(h>=144 && f.vcodec !== 'none') map.set(h,{available:true,size:f.filesize||f.filesize_approx||0});
    });
    return ORDER.map(([label,height]) => ({label,height,...(map.get(height)||{available:false,size:0})}));
  }

  function render() {
    const list = document.querySelector('#vlQualities');
    if (!list || !latestVideo) return;
    const data = catalog(latestVideo);
    const available = data.filter(q=>q.available);
    const current = selected && data.some(q=>q.label===selected && q.available) ? selected : (available.find(q=>q.height===2160)?.label || available[0]?.label || null);
    selected = current;
    const head = document.querySelector('.vl-quality-head span');
    if(head) head.textContent = available.length ? `${available.length} real source qualities` : 'No source qualities detected';
    list.innerHTML = data.map(q => `<button type="button" class="vl-quality ${q.available?'available':'unavailable'} ${q.label===selected?'selected':''}" data-vl-quality="${q.label}" ${q.available?'':'disabled'}><span><b>${esc(q.label)}</b>${q.label==='4K'?' · 2160p':''}</span><small>${q.available?(q.size?bytes(q.size):'Available'):'Not available'}</small></button>`).join('');
    list.querySelectorAll('[data-vl-quality]').forEach(btn=>btn.addEventListener('click',()=>{ if(btn.disabled)return; selected=btn.dataset.vlQuality; list.querySelectorAll('.vl-quality').forEach(x=>x.classList.remove('selected')); btn.classList.add('selected'); const label=document.querySelector('#qualityLabel'); if(label)label.textContent=`${selected} selected`; }));
  }

  function style() {
    if(document.querySelector('#vl-manual-quality-style'))return;
    const s=document.createElement('style');s.id='vl-manual-quality-style';s.textContent=`
      #vlQualities{display:grid!important;grid-template-columns:1fr 1fr!important;gap:8px!important}
      #vlQualities .vl-quality{display:flex!important;align-items:center!important;justify-content:space-between!important;min-height:44px!important;padding:10px!important}
      #vlQualities .vl-quality.available{cursor:pointer!important;border-color:#2d579c!important}
      #vlQualities .vl-quality.selected{background:linear-gradient(100deg,rgba(90,35,255,.55),rgba(20,115,255,.35))!important;border-color:#7d75ff!important;box-shadow:0 0 18px rgba(72,76,255,.25)!important}
      #vlQualities .vl-quality.unavailable{opacity:.32!important;cursor:not-allowed!important}
      #vlQualities .vl-quality small{font-size:9px!important;color:#8291b4!important;margin-left:6px!important}
    `;document.head.appendChild(s);
  }

  function boot(){style(); render(); const observer=new MutationObserver(()=>{ if(latestVideo) render(); }); const list=document.querySelector('#vlQualities'); if(list) observer.observe(list,{childList:true,subtree:true}); setTimeout(render,500);setTimeout(render,1500);setTimeout(render,3000); }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',boot); else boot();
})();
