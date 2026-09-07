(() => {
  'use strict';

  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await nativeFetch(...args);
    const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
    if (!url.includes('/api/info')) return response;
    try {
      const payload = await response.clone().json();
      if (payload?.ok && payload.video?.qualities) {
        payload.video.formats = payload.video.qualities
          .filter(q => q.available)
          .map(q => ({height:q.height,vcodec:'video',acodec:q.has_audio?'audio':'none',ext:'mp4',filesize:q.filesize||0}));
      }
      return new Response(JSON.stringify(payload), {status:response.status,statusText:response.statusText,headers:{'Content-Type':'application/json'}});
    } catch (_) { return response; }
  };

  const style=document.createElement('style');style.id='vidloom-final-preview-style';style.textContent=`
    #vidloom-workspace{max-width:1280px;margin:0 auto 80px}
    .vl-hero-title{text-align:center;padding:34px 12px 22px}.vl-hero-title h1{margin:0;font-size:clamp(32px,4.5vw,54px);line-height:1.08;letter-spacing:-.055em;color:#f5f7ff}.vl-hero-title h1 span{background:linear-gradient(90deg,#10d9ff,#278cff,#a35cff);-webkit-background-clip:text;background-clip:text;color:transparent}.vl-hero-title p{margin:10px 0 0;color:#a8afc5;font-size:14px}.vl-hero-title b{font-weight:500;color:#dce3ff}
    .vl-urlbar{max-width:760px;margin:0 auto 18px;height:48px;border-radius:25px;border-color:#376dff;box-shadow:0 0 30px rgba(56,91,255,.16),inset 0 0 20px rgba(53,76,170,.1)}.vl-urlbar input{font-size:13px}.vl-go{min-width:78px;height:36px;padding:0 18px!important;border-radius:9px!important}
    .vl-sites{max-width:850px;margin:0 auto 24px;gap:17px}.vl-site .vl-site-icon{width:44px;height:44px;border-radius:11px;background:linear-gradient(145deg,#101936,#202e5c);border-color:#294783}
    .vl-feature-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:0 0 18px}.vl-feature{min-height:76px;padding:13px 14px;border:1px solid #223c75;border-radius:11px;background:linear-gradient(145deg,rgba(9,19,48,.92),rgba(7,12,30,.96));display:grid;grid-template-columns:36px 1fr;gap:9px;align-items:center}.vl-feature-icon{width:34px;height:34px;border-radius:9px;display:grid;place-items:center;background:linear-gradient(145deg,#263cff,#7b24ff);color:#fff;font-weight:800;box-shadow:0 0 18px rgba(75,66,255,.25)}.vl-feature:nth-child(2) .vl-feature-icon{background:linear-gradient(145deg,#00bfae,#057aff)}.vl-feature:nth-child(3) .vl-feature-icon{background:linear-gradient(145deg,#ffb52e,#ff7b1a)}.vl-feature:nth-child(4) .vl-feature-icon{background:linear-gradient(145deg,#c02cff,#ff32b7)}.vl-feature strong{display:block;font-size:12px;color:#eef2ff}.vl-feature small{display:block;margin-top:3px;font-size:9px;line-height:1.35;color:#8995b5}
    .vl-work{gap:16px}.vl-browser,.vl-download{border-color:#28477f;border-radius:14px;box-shadow:0 0 35px rgba(30,83,210,.1)}.vl-browser{min-height:540px}.vl-browser-top{padding:11px;background:#071027}.vl-preview{min-height:470px;padding:17px}.vl-preview iframe,.vl-preview-card{height:425px}.vl-download{padding:17px}.vl-download h3{font-size:18px;margin-bottom:18px}.vl-quality-list{max-height:320px}.vl-quality{min-height:42px}.vl-download-btn{font-size:14px;min-height:47px}.vl-quality.unavailable{display:flex;opacity:.34}.vl-meta{font-size:11px}
    .vl-how{display:grid;grid-template-columns:1.1fr 1fr 1fr 1fr;gap:12px;margin-top:18px;padding:17px;border:1px solid #20386d;border-radius:12px;background:rgba(5,12,31,.72)}.vl-how h3{margin:0 0 6px;font-size:16px;color:#f2f5ff}.vl-how p{margin:0;color:#8996b6;font-size:10px;line-height:1.45}.vl-how-step{border-left:1px solid #263e70;padding-left:13px}.vl-how-step b{display:inline-grid;place-items:center;width:22px;height:22px;border-radius:50%;background:#2a35d9;color:#fff;font-size:10px;margin-bottom:7px}.vl-how-step strong{display:block;font-size:11px;color:#e6ebff}.vl-how-step small{display:block;margin-top:3px;color:#7e8baa;font-size:9px;line-height:1.35}
    @media(max-width:900px){.vl-feature-grid{grid-template-columns:repeat(2,1fr)}.vl-urlbar{max-width:none}.vl-preview iframe,.vl-preview-card{height:330px}.vl-how{grid-template-columns:1fr 1fr}}
    @media(max-width:560px){.vl-feature-grid{grid-template-columns:1fr}.vl-preview iframe,.vl-preview-card{height:250px}.vl-sites{gap:7px}.vl-how{grid-template-columns:1fr}}
  `;document.head.appendChild(style);

  function addReferenceLayout(){
    const workspace=document.querySelector('#vidloom-workspace');if(!workspace)return;
    if(!workspace.querySelector('.vl-hero-title')){
      const title=document.createElement('div');title.className='vl-hero-title';title.innerHTML='<h1>Download <span>Videos &amp; Audios</span></h1><p><b>Fast</b> &nbsp;·&nbsp; <b>Simple</b> &nbsp;·&nbsp; <b>Free</b></p>';workspace.prepend(title);
    }
    const sites=workspace.querySelector('.vl-sites');
    if(sites&&!workspace.querySelector('.vl-feature-grid')){
      const features=document.createElement('div');features.className='vl-feature-grid';features.innerHTML='<div class="vl-feature"><span class="vl-feature-icon">ϟ</span><div><strong>Multiple Platforms</strong><small>YouTube, TikTok, Instagram, Facebook and more.</small></div></div><div class="vl-feature"><span class="vl-feature-icon">◇</span><div><strong>High Quality</strong><small>Choose the real quality exposed by the source.</small></div></div><div class="vl-feature"><span class="vl-feature-icon">ϟ</span><div><strong>Fast &amp; Reliable</strong><small>Live download progress, speed and ETA.</small></div></div><div class="vl-feature"><span class="vl-feature-icon">▣</span><div><strong>All Devices</strong><small>Responsive on PC, Android and iPhone browsers.</small></div></div>';sites.insertAdjacentElement('afterend',features);
    }
    const work=workspace.querySelector('.vl-work');
    if(work&&!workspace.querySelector('.vl-how')){const how=document.createElement('div');how.className='vl-how';how.innerHTML='<div><h3>How It Works</h3><p>Download public videos in a few simple steps.</p></div><div class="vl-how-step"><b>1</b><strong>Paste Link</strong><small>Enter a supported public media URL.</small></div><div class="vl-how-step"><b>2</b><strong>Choose Options</strong><small>Select an available quality or audio mode.</small></div><div class="vl-how-step"><b>3</b><strong>Start Download</strong><small>Watch live progress and save the finished file.</small></div>';work.insertAdjacentElement('afterend',how)}
  }
  function updateMode(){const active=document.querySelector('.vl-tab.active');const heading=document.querySelector('.vl-download h3');const qualityHead=document.querySelector('.vl-quality-head b');const list=document.querySelector('#vlQualities');if(!active||!heading)return;const audio=active.dataset.mode==='audio';heading.textContent=audio?'Download Audio':'Download Video';if(qualityHead)qualityHead.textContent=audio?'Audio quality':'Select Quality';if(list&&audio&&!list.dataset.audioRendered){list.innerHTML='<button type="button" class="vl-quality selected" disabled><span>♫ 192 kbps</span><small>High quality audio</small></button>';list.dataset.audioRendered='1'}if(list&&!audio)delete list.dataset.audioRendered}
  addReferenceLayout();updateMode();new MutationObserver(()=>{addReferenceLayout();updateMode()}).observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['class']});
})();
