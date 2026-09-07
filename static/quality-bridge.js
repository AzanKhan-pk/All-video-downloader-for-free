(() => {
  'use strict';

  // Final UI bridge: the legacy script can render its fallback notice before
  // the authoritative quality endpoint responds. This bridge replaces that
  // stale state with the real /api/quality-info catalog.
  const HEIGHTS = [2160, 1440, 1080, 720, 480, 360, 240, 144];
  const labelFor = h => h >= 2160 ? '4K' : `${h}p`;
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const bytes = n => {
    n = Number(n || 0);
    if (!n) return 'Available';
    const u = ['B','KB','MB','GB'];
    const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), u.length - 1);
    return `${(n / 1024 ** i).toFixed(i ? 1 : 0)} ${u[i]}`;
  };

  function root() { return document.querySelector('#vlQualities') || document.querySelector('#qualityGrid'); }
  function currentUrl() { return (document.querySelector('#url')?.value || document.querySelector('#vlAddress')?.value || '').trim(); }

  async function refresh() {
    const box = root();
    const url = currentUrl();
    if (!box || !url || !/^https?:\/\//i.test(url)) return;
    try {
      const r = await fetch('/api/quality-info', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({url}), cache: 'no-store'
      });
      const d = await r.json();
      if (!r.ok || !d.ok) return;
      const v = d.video || d;
      const exact = new Map();
      (v.qualities || d.qualities || []).forEach(q => {
        const h = Number(q.height || 0);
        if (h) exact.set(h, {available: q.available === true, size: Number(q.filesize || 0)});
      });
      (v.formats || d.formats || []).forEach(f => {
        const h = Number(f.height || 0);
        if (h >= 144 && f.vcodec !== 'none') exact.set(h, {available:true, size:Math.max(Number(f.filesize || 0), exact.get(h)?.size || 0)});
      });
      const available = HEIGHTS.filter(h => exact.get(h)?.available);
      box.innerHTML = HEIGHTS.map(h => {
        const q = exact.get(h);
        const ok = !!q?.available;
        return `<button type="button" class="vl-quality ${ok ? 'available' : 'unavailable'}" data-bridge-quality="${h}" ${ok ? '' : 'disabled'}><span><b>${labelFor(h)}</b>${h === 2160 ? ' · 2160p' : ''}</span><small>${ok ? esc(bytes(q.size)) : 'Not available'}</small></button>`;
      }).join('');
      box.querySelectorAll('[data-bridge-quality]').forEach(btn => btn.addEventListener('click', () => {
        box.querySelectorAll('[data-bridge-quality]').forEach(x => x.classList.remove('selected'));
        btn.classList.add('selected');
        const q = labelFor(Number(btn.dataset.bridgeQuality));
        window.__vidloomSelectedQuality = q;
        const label = document.querySelector('#qualityLabel');
        if (label) label.textContent = `${q} selected`;
        const download = document.querySelector('#vlDownloadBtn');
        if (download) {
          download.disabled = false;
          download.textContent = `⇩ Download ${document.querySelector('.vl-tab.active')?.dataset.mode === 'audio' ? 'MP3' : 'MP4'}`;
        }
      }));
      const count = available.length;
      const head = document.querySelector('.vl-quality-head span');
      if (head) head.textContent = count ? `${count} real source qualities` : 'No compatible source quality detected';

      // Remove every old fallback sentence, including copies created by the
      // legacy renderer, without touching the rest of the interface.
      document.querySelectorAll('body *').forEach(el => {
        if (el.children.length === 0 && /source did not expose|safe best available fallback|only qualities exposed by the source are offered/i.test(el.textContent || '')) {
          el.remove();
        }
      });
    } catch (_) {
      // Keep the existing UI intact on transient network errors.
    }
  }

  function start() {
    refresh();
    const input = document.querySelector('#url');
    input?.addEventListener('change', refresh);
    input?.addEventListener('blur', refresh);
    input?.addEventListener('input', () => { if (/^https?:\/\//i.test(input.value.trim())) refresh(); });
    const address = document.querySelector('#vlAddress');
    address?.addEventListener('change', refresh);
    setTimeout(refresh, 500);
    setTimeout(refresh, 1500);
    setTimeout(refresh, 3000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
