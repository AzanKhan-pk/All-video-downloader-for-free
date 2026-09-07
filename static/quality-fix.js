(() => {
  'use strict';

  // VidLoom quality controller: one implementation only.
  // No automatic quality fallback and no invented quality values.
  const ORDER = [
    ['144p', 144], ['240p', 240], ['360p', 360], ['480p', 480],
    ['720p', 720], ['1080p', 1080], ['1440p', 1440], ['4K', 2160]
  ];

  let latestVideo = null;
  let selectedQuality = null;
  let lastUrl = '';
  let busy = false;

  const $ = (s, r = document) => r.querySelector(s);
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

  function catalog(video) {
    const map = new Map();

    for (const q of (Array.isArray(video?.qualities) ? video.qualities : [])) {
      const h = Number(q.height || 0);
      if (h) map.set(h, { available: q.available === true, size: Number(q.filesize || 0) });
    }

    for (const f of (Array.isArray(video?.formats) ? video.formats : [])) {
      const h = Number(f.height || 0);
      if (h >= 144 && f.vcodec && f.vcodec !== 'none') {
        const old = map.get(h);
        map.set(h, {
          available: true,
          size: Math.max(Number(f.filesize || f.filesize_approx || 0), old?.size || 0)
        });
      }
    }

    for (const h0 of (Array.isArray(video?.source_heights) ? video.source_heights : [])) {
      const h = Number(h0 || 0);
      if (h >= 144) {
        const old = map.get(h);
        map.set(h, { available: true, size: old?.size || 0 });
      }
    }

    return ORDER.map(([label, height]) => ({
      label, height,
      available: map.get(height)?.available === true,
      size: map.get(height)?.size || 0
    }));
  }

  function render() {
    const list = $('#vlQualities');
    if (!list || !latestVideo) return;

    const data = catalog(latestVideo);
    const available = data.filter(x => x.available);

    if (selectedQuality && !available.some(x => x.label === selectedQuality)) {
      selectedQuality = null;
    }

    const head = $('.vl-quality-head span');
    if (head) head.textContent = available.length
      ? `${available.length} real source qualities`
      : 'No source qualities detected';

    list.innerHTML = data.map(q => `
      <button type="button"
        class="vl-quality ${q.available ? 'available' : 'unavailable'} ${q.label === selectedQuality ? 'selected' : ''}"
        data-vl-quality="${esc(q.label)}"
        ${q.available ? '' : 'disabled'}>
        <span><b>${esc(q.label)}</b>${q.label === '4K' ? ' · 2160p' : ''}</span>
        <small>${q.available ? (q.size ? esc(bytes(q.size)) : 'Available') : 'Not available'}</small>
      </button>
    `).join('');

    list.querySelectorAll('[data-vl-quality]').forEach(button => {
      button.addEventListener('click', () => {
        if (button.disabled) return;
        selectedQuality = button.dataset.vlQuality;
        list.querySelectorAll('.vl-quality').forEach(x => x.classList.remove('selected'));
        button.classList.add('selected');
        const label = $('#qualityLabel');
        if (label) label.textContent = `${selectedQuality} selected`;
        window.VidLoomSelectedQuality = () => selectedQuality;
        window.VidLoomQuality = selectedQuality;
        document.dispatchEvent(new CustomEvent('vidloom:quality-selected', { detail: { quality: selectedQuality } }));
        const download = $('#vlDownloadBtn');
        if (download) download.disabled = false;
      });
    });

    window.VidLoomSelectedQuality = () => selectedQuality;
  }

  async function fetchInfo(url) {
    if (!url || busy) return;
    busy = true;
    lastUrl = url;
    selectedQuality = null;
    const list = $('#vlQualities');
    if (list) list.innerHTML = '<div class="vl-empty" style="padding:25px 5px;font-size:12px">Detecting real source qualities…</div>';

    try {
      const response = await fetch('/api/info', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url})
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || 'Could not read this media.');
      latestVideo = data.video || data;
      render();
    } catch (error) {
      if (list) list.innerHTML = `<div class="vl-empty" style="padding:25px 5px;font-size:12px"><strong>Quality detection failed</strong><br>${esc(error.message || 'Try again.')}</div>`;
    } finally {
      busy = false;
    }
  }

  function bind() {
    const fetchButton = $('#fetchBtn');
    const input = $('#url');

    if (fetchButton && !fetchButton.dataset.qualityBound) {
      fetchButton.dataset.qualityBound = '1';
      fetchButton.addEventListener('click', () => {
        const url = input?.value?.trim() || '';
        if (url) {
          // Let the original downloader request finish first, then query the
          // same endpoint independently so the quality panel cannot depend on
          // another script's internal state.
          setTimeout(() => fetchInfo(url), 350);
        }
      });
    }

    document.addEventListener('vidloom:media-loaded', e => {
      if (e.detail?.video) {
        latestVideo = e.detail.video;
        lastUrl = latestVideo.url || '';
        selectedQuality = null;
        render();
      }
    });

    // Intercept /api/download only to force the manually selected quality.
    // No quality is changed or downgraded automatically.
    const nativeFetch = window.fetch.bind(window);
    window.fetch = async (input, init = {}) => {
      try {
        const requestUrl = typeof input === 'string' ? input : input?.url || '';
        if (/\/api\/download(?:$|\/)/.test(requestUrl) && init.body && selectedQuality) {
          const payload = JSON.parse(init.body);
          if (payload.mode === 'video') payload.quality = selectedQuality;
          init = {...init, body: JSON.stringify(payload)};
        }
      } catch (_) {}
      const response = await nativeFetch(input, init);
      try {
        const requestUrl = typeof input === 'string' ? input : input?.url || '';
        if (/\/api\/info(?:\?|$)/.test(requestUrl) && response.ok) {
          response.clone().json().then(data => {
            if (data?.ok && data.video) {
              latestVideo = data.video;
              lastUrl = data.video.url || lastUrl;
              selectedQuality = null;
              setTimeout(render, 0);
            }
          }).catch(() => {});
        }
      } catch (_) {}
      return response;
    };

    render();
    setTimeout(render, 500);
    setTimeout(render, 1500);
    setTimeout(render, 3000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind);
  else bind();
})();
