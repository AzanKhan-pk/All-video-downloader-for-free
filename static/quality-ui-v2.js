(() => {
  'use strict';

  // Final quality UI for the VidLoom workspace.
  // Important: this reads the actual /api/info response and never invents a
  // quality or silently falls back to another resolution.
  const ORDER = [
    ['144p', 144], ['240p', 240], ['360p', 360], ['480p', 480],
    ['720p', 720], ['1080p', 1080], ['1440p', 1440], ['4K', 2160]
  ];
  let latestVideo = null;
  let selected = null;
  let lastSignature = '';

  const nativeFetch = window.fetch.bind(window);
  window.fetch = async function(input, init) {
    const response = await nativeFetch(input, init);
    try {
      const url = typeof input === 'string' ? input : (input && input.url) || '';
      if (/\/api\/info(?:\?|$)/.test(url) && response.ok) {
        const clone = response.clone();
        clone.json().then(data => {
          if (data && data.ok && data.video) {
            latestVideo = data.video;
            selected = null;
            lastSignature = '';
            setTimeout(render, 0);
          }
        }).catch(() => {});
      }
    } catch (_) {}
    return response;
  };

  const esc = value => String(value ?? '').replace(/[&<>'"]/g, c => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;'
  }[c]));

  const bytes = value => {
    const n = Number(value || 0);
    if (!n) return '';
    const units = ['B','KB','MB','GB'];
    const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), units.length - 1);
    return `${(n / Math.pow(1024, i)).toFixed(i ? 1 : 0)} ${units[i]}`;
  };

  function getCatalog(video) {
    const map = new Map();

    // Prefer the backend's explicit quality catalog.
    (Array.isArray(video?.qualities) ? video.qualities : []).forEach(q => {
      const h = Number(q.height || 0);
      if (h) map.set(h, {
        available: q.available === true,
        size: Number(q.filesize || 0)
      });
    });

    // Also accept compact raw formats returned by wsgi.py.
    (Array.isArray(video?.formats) ? video.formats : []).forEach(f => {
      const h = Number(f.height || 0);
      if (h >= 144 && f.vcodec !== 'none') {
        const previous = map.get(h);
        map.set(h, {
          available: true,
          size: Math.max(Number(f.filesize || f.filesize_approx || 0), previous?.size || 0)
        });
      }
    });

    // source_heights is an additional authoritative signal from wsgi.py.
    (Array.isArray(video?.source_heights) ? video.source_heights : []).forEach(value => {
      const h = Number(value || 0);
      if (h >= 144) {
        const previous = map.get(h);
        map.set(h, {available:true, size:previous?.size || 0});
      }
    });

    return ORDER.map(([label, height]) => ({
      label, height,
      available: map.get(height)?.available === true,
      size: map.get(height)?.size || 0
    }));
  }

  function render() {
    const list = document.querySelector('#vlQualities');
    if (!list || !latestVideo) return;

    const catalog = getCatalog(latestVideo);
    const signature = catalog.map(q => `${q.height}:${q.available}:${q.size}`).join('|');
    if (signature === lastSignature && list.querySelector('.vl-quality')) return;
    lastSignature = signature;

    const available = catalog.filter(q => q.available);
    if (selected && !available.some(q => q.label === selected)) selected = null;

    const head = document.querySelector('.vl-quality-head span');
    if (head) head.textContent = available.length
      ? `${available.length} real source qualities`
      : 'No downloadable qualities detected';

    list.innerHTML = catalog.map(q => `
      <button type="button"
        class="vl-quality ${q.available ? 'available' : 'unavailable'} ${q.label === selected ? 'selected' : ''}"
        data-vl-quality="${esc(q.label)}"
        ${q.available ? '' : 'disabled'}>
        <span><b>${esc(q.label)}</b>${q.label === '4K' ? ' · 2160p' : ''}</span>
        <small>${q.available ? (q.size ? esc(bytes(q.size)) : 'Available') : 'Not available'}</small>
      </button>
    `).join('');

    list.querySelectorAll('[data-vl-quality]').forEach(button => {
      button.addEventListener('click', () => {
        if (button.disabled) return;
        selected = button.dataset.vlQuality;
        list.querySelectorAll('.vl-quality').forEach(x => x.classList.remove('selected'));
        button.classList.add('selected');
        const label = document.querySelector('#qualityLabel');
        if (label) label.textContent = `${selected} selected`;
        const download = document.querySelector('#vlDownloadBtn');
        if (download) download.disabled = false;
      });
    });

    // The main downloader reads this value through the custom event instead of
    // assuming a default quality.
    window.VidLoomSelectedQuality = () => selected;
  }

  function style() {
    if (document.querySelector('#vl-quality-v2-style')) return;
    const style = document.createElement('style');
    style.id = 'vl-quality-v2-style';
    style.textContent = `
      #vlQualities{display:grid!important;grid-template-columns:1fr 1fr!important;gap:8px!important}
      #vlQualities .vl-quality{display:flex!important;align-items:center!important;justify-content:space-between!important;min-height:44px!important;padding:10px 11px!important}
      #vlQualities .vl-quality.available{cursor:pointer!important}
      #vlQualities .vl-quality.unavailable{opacity:.32!important;cursor:not-allowed!important}
      #vlQualities .vl-quality.selected{background:linear-gradient(100deg,rgba(90,35,255,.55),rgba(20,115,255,.35))!important;border-color:#7d75ff!important;box-shadow:0 0 18px rgba(72,76,255,.25)!important}
      #vlQualities .vl-quality small{font-size:9px!important;color:#8291b4!important;margin-left:6px!important}
    `;
    document.head.appendChild(style);
  }

  function boot() {
    style();
    render();
    const observer = new MutationObserver(() => setTimeout(render, 0));
    const list = document.querySelector('#vlQualities');
    if (list) observer.observe(list, {childList:true, subtree:true});
    setTimeout(render, 300);
    setTimeout(render, 1000);
    setTimeout(render, 2500);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
