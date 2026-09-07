(() => {
  'use strict';

  // Bridge the API's compact quality catalog to the existing preview renderer.
  // This keeps the original UI code intact while making the quality buttons
  // reflect the real formats returned by yt-dlp.
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await nativeFetch(...args);
    const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
    if (!url.includes('/api/info')) return response;
    try {
      const payload = await response.clone().json();
      if (payload?.ok && payload.video?.qualities && !payload.video.formats) {
        payload.video.formats = payload.video.qualities
          .filter(q => q.available)
          .map(q => ({
            height: q.height,
            vcodec: 'video',
            acodec: q.has_audio ? 'audio' : 'none',
            ext: 'mp4',
            filesize: q.filesize || 0,
          }));
      }
      return new Response(JSON.stringify(payload), {
        status: response.status,
        statusText: response.statusText,
        headers: {'Content-Type': 'application/json'}
      });
    } catch (_) {
      return response;
    }
  };

  const style = document.createElement('style');
  style.id = 'vidloom-final-preview-style';
  style.textContent = `
    /* Screenshot-inspired final workspace polish */
    #vidloom-workspace{max-width:1280px;margin:26px auto 80px}
    .vl-urlbar{max-width:760px;margin:0 auto 18px;height:48px;border-radius:25px;border-color:#376dff;box-shadow:0 0 30px rgba(56,91,255,.16),inset 0 0 20px rgba(53,76,170,.1)}
    .vl-urlbar input{font-size:13px}
    .vl-go{min-width:78px;height:36px;padding:0 18px!important;border-radius:9px!important}
    .vl-sites{max-width:850px;margin:0 auto 28px;gap:17px}
    .vl-site .vl-site-icon{width:44px;height:44px;border-radius:11px;background:linear-gradient(145deg,#101936,#202e5c);border-color:#294783}
    .vl-work{gap:16px}
    .vl-browser,.vl-download{border-color:#28477f;border-radius:14px;box-shadow:0 0 35px rgba(30,83,210,.1)}
    .vl-browser{min-height:540px}
    .vl-browser-top{padding:11px;background:#071027}
    .vl-preview{min-height:470px;padding:17px}
    .vl-preview iframe,.vl-preview-card{height:425px}
    .vl-download{padding:17px}
    .vl-download h3{font-size:18px;margin-bottom:18px}
    .vl-quality-list{max-height:320px}
    .vl-quality{min-height:42px}
    .vl-download-btn{font-size:14px;min-height:47px}
    .vl-media-badge{display:inline-flex;align-items:center;gap:7px;margin-bottom:9px;color:#59caff;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em}
    .vl-available-count{color:#4fd4ff;font-size:11px;margin-top:3px}
    .vl-quality.unavailable{display:flex;opacity:.34}
    @media(max-width:900px){.vl-urlbar{max-width:none}.vl-preview iframe,.vl-preview-card{height:330px}}
    @media(max-width:560px){.vl-preview iframe,.vl-preview-card{height:250px}.vl-sites{gap:7px}}
  `;
  document.head.appendChild(style);

  // Keep the quality list synchronized with the selected media mode.
  const updateModeVisuals = () => {
    const active = document.querySelector('.vl-tab.active');
    const heading = document.querySelector('.vl-download h3');
    const qualityHead = document.querySelector('.vl-quality-head b');
    const list = document.querySelector('#vlQualities');
    if (!active || !heading) return;
    const audio = active.dataset.mode === 'audio';
    heading.textContent = audio ? 'Download Audio' : 'Download Video';
    if (qualityHead) qualityHead.textContent = audio ? 'Audio quality' : 'Select Quality';
    if (list && audio && window.__vlLastAudioMessage !== audio) {
      list.innerHTML = '<button type="button" class="vl-quality selected" disabled><span>♫ 192 kbps</span><small>High quality audio</small></button>';
      window.__vlLastAudioMessage = audio;
    }
    if (list && !audio) window.__vlLastAudioMessage = false;
  };
  new MutationObserver(updateModeVisuals).observe(document.body, {subtree:true, childList:true, attributes:true, attributeFilter:['class']});
  setTimeout(updateModeVisuals, 300);
})();
