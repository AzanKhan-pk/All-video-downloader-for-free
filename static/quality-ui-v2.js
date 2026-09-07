(() => {
  'use strict';

  // Single source of truth for the visible quality selector.
  // This script deliberately does NOT show the old "safe fallback" message.
  const ORDER = [
    ['144p', 144], ['240p', 240], ['360p', 360], ['480p', 480],
    ['720p', 720], ['1080p', 1080], ['1440p', 1440], ['4K', 2160]
  ];

  let latestVideo = null;
  let selected = null;
  let lastUrl = '';

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = v => String(v ?? '').replace(/[&<>'"]/g, c => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;'
  }[c]));

  function bytes(value) {
    const n = Number(value || 0);
    if (!n) return '';
    const units = ['B','KB','MB','GB'];
    const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), units.length - 1);
    return `${(n / Math.pow(1024, i)).toFixed(i ? 1 : 0)} ${units[i]}`;
  }

  function getCatalog(video) {
    const map = new Map();

    // Backend's explicit catalog is preferred.
    for (const q of (Array.isArray(video?.qualities) ? video.qualities : [])) {
      const h = Number(q.height || 0);
      if (h) map.set(h, {
        available: q.available === true,
        size: Number(q.filesize || 0)
      });
    }

    // Raw formats are authoritative when present.
    for (const f of (Array.isArray(video?.formats) ? video.formats : [])) {
      const h = Number(f.height || 0);
      if (h >= 144 && f.vcodec !== 'none') {
        const old = map.get(h);
        map.set(h, {
          available: true,
          size: Math.max(Number(f.filesize || f.filesize_approx || 0), old?.size || 0)
        });
      }
    }

    // Also accept source_heights returned by wsgi.py.
    for (const value of (Array.isArray(video?.source_heights) ? video.source_heights : [])) {
      const h = Number(value || 0);
      if (h >= 144) {
        const old = map.get(h);
        map.set(h, { available: true, size: old?.size || 0 });
      }
    }

    return ORDER.map(([label, height]) => ({
      label,
      height,
      available: map.get(height)?.available === true,
      size: map.get(height)?.size || 0
    }));
  }

  function render() {
    const list = $('#vlQualities');
    if (!list || !latestVideo) return;

    const catalog = getCatalog(latestVideo);
    const available = catalog.filter(q => q.available);

    if (selected && !available.some(q => q.label === selected)) selected = null;

    const head = $('.vl-quality-head span');
    if (head) head.textContent = available.length
      ? `${available.length} real source qualities`
      : 'No source qualities detected';

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

        const label = $('#qualityLabel');
        if (label) label.textContent = `${selected} selected`;

        // Keep the original downloader's variables in sync where possible.
        window.VidLoomSelectedQuality = () => selected;
        window.VidLoomQuality = selected;
        document.dispatchEvent(new CustomEvent('vidloom:quality-selected', { detail: { quality: selected } }));

        const download = $('#vlDownloadBtn');
        if (download) download.disabled = false;
      });
    });

    window.VidLoomSelectedQuality = () => selected;
  }

  async function loadInfo(url) {
    if (!url || url === lastUrl) {
      if (latestVideo) render();
      return;
    }

    lastUrl = url;
    const list = $('#vlQualities');
    if (list) list.innerHTML = '<div class="vl-empty" style="padding:25px 5px;font-size:12px">Detecting source qualities…</div>';

    try {
      const response = await fetch('/api/info', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || 'Could not read this media.');
      latestVideo = data.video || data;
      selected = null;
      render();
    } catch (error) {
      if (list) list.innerHTML = `<div class="vl-empty" style="padding:25px 5px;font-size:12px"><strong>Quality detection failed</strong>${esc(error.message || 'Try fetching the media again.')}</div>`;
    }
  }

  function syncFromInput() {
    const input = $('#url');
    if (!input) return;
    const url = input.value.trim();
    if (url) loadInfo(url);
  }

  function style() {
    if ($('#vl-quality-v3-style')) return;
    const s = document.createElement('style');
    s.id = 'vl-quality-v3-style';
    s.textContent = `
      #vlQualities{display:grid!important;grid-template-columns:1fr 1fr!important;gap:8px!important}
      #vlQualities .vl-quality{display:flex!important;align-items:center!important;justify-content:space-between!important;min-height:46px!important;padding:10px 11px!important}
      #vlQualities .vl-quality.available{cursor:pointer!important}
      #vlQualities .vl-quality.unavailable{opacity:.35!important;cursor:not-allowed!important}
      #vlQualities .vl-quality.selected{background:linear-gradient(100deg,rgba(90,35,255,.58),rgba(20,115,255,.38))!important;border-color:#7d75ff!important;box-shadow:0 0 18px rgba(72,76,255,.25)!important}
      #vlQualities .vl-quality small{font-size:9px!important;color:#8291b4!important;margin-left:6px!important}
    `;
    document.head.appendChild(s);
  }

  function boot() {
    style();

    const fetchButton = $('#fetchBtn');
    if (fetchButton) fetchButton.addEventListener('click', () => {
      setTimeout(syncFromInput, 150);
      setTimeout(syncFromInput, 800);
      setTimeout(syncFromInput, 1800);
    });

    const address = $('#vlAddress');
    if (address) address.addEventListener('change', () => loadInfo(address.value.trim()));

    document.addEventListener('vidloom:media-loaded', event => {
      if (event.detail?.video) {
        latestVideo = event.detail.video;
        lastUrl = latestVideo.url || '';
        selected = null;
        render();
      }
    });

    // The main script's /api/info fetch is also observed so this works even
    // when another UI button performs the request first.
    const nativeFetch = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const response = await nativeFetch(...args);
      try {
        const input = args[0];
        const requestUrl = typeof input === 'string' ? input : input?.url || '';
        if (/\/api\/info(?:\?|$)/.test(requestUrl) && response.ok) {
          response.clone().json().then(data => {
            if (data?.ok && data.video) {
              latestVideo = data.video;
              lastUrl = data.video.url || $('#url')?.value?.trim() || '';
              selected = null;
              setTimeout(render, 0);
            }
          }).catch(() => {});
        }
      } catch (_) {}
      return response;
    };

    setTimeout(syncFromInput, 500);
    setTimeout(render, 1000);
    setTimeout(render, 2500);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
