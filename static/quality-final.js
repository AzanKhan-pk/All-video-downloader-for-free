(() => {
  'use strict';

  // Final, single quality controller. Uses the dedicated server endpoint and
  // never displays the obsolete "safe best available fallback" message.
  const ORDER = [
    ['4K', 2160], ['1440p', 1440], ['1080p', 1080], ['720p', 720],
    ['480p', 480], ['360p', 360], ['240p', 240], ['144p', 144]
  ];
  let selected = null;
  let selectedMode = 'video';
  let currentUrl = '';
  let currentVideo = null;
  let jobId = null;

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = v => String(v ?? '').replace(/[&<>\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
  const bytes = n => {
    n = Number(n || 0);
    if (!n) return '—';
    const u = ['B','KB','MB','GB','TB'];
    const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), u.length - 1);
    return `${(n / Math.pow(1024, i)).toFixed(i ? 1 : 0)} ${u[i]}`;
  };
  const eta = n => {
    n = Number(n);
    if (!Number.isFinite(n) || n < 0) return 'ETA —';
    if (n < 60) return `ETA ${Math.ceil(n)}s`;
    return `ETA ${Math.floor(n / 60)}m ${Math.ceil(n % 60)}s`;
  };

  function hostList() { return $('#vlQualities') || $('#qualityGrid'); }

  function sourceCatalog(data) {
    const map = new Map();
    for (const q of (Array.isArray(data?.qualities) ? data.qualities : [])) {
      const h = Number(q.height || 0);
      if (h) map.set(h, { ok: q.available === true, size: Number(q.filesize || 0) });
    }
    for (const f of (Array.isArray(data?.formats) ? data.formats : [])) {
      const h = Number(f.height || 0);
      if (h >= 144 && f.has_video !== false && f.vcodec !== 'none') {
        const old = map.get(h);
        map.set(h, { ok: true, size: Math.max(Number(f.filesize || f.filesize_approx || 0), old?.size || 0) });
      }
    }
    for (const h0 of (Array.isArray(data?.source_heights) ? data.source_heights : [])) {
      const h = Number(h0 || 0);
      if (h >= 144) map.set(h, { ok: true, size: map.get(h)?.size || 0 });
    }
    return ORDER.map(([label, height]) => ({ label, height, ...(map.get(height) || { ok:false, size:0 }) }));
  }

  function renderQuality(data) {
    const list = hostList();
    if (!list) return;
    const catalog = sourceCatalog(data);
    const available = catalog.filter(q => q.ok);
    if (selected && !available.some(q => q.label === selected)) selected = null;

    const head = $('.vl-quality-head span');
    if (head) head.textContent = available.length ? `${available.length} real source qualities` : 'No compatible source quality detected';

    list.innerHTML = catalog.map(q => `
      <button type="button" class="vl-quality ${q.ok ? 'available' : 'unavailable'} ${q.label === selected ? 'selected' : ''}"
        data-final-quality="${esc(q.label)}" ${q.ok ? '' : 'disabled'}>
        <span><b>${esc(q.label)}</b>${q.label === '4K' ? ' · 2160p' : ''}</span>
        <small>${q.ok ? (q.size ? esc(bytes(q.size)) : 'Available') : 'Not available'}</small>
      </button>`).join('');

    $$('[data-final-quality]', list).forEach(b => b.onclick = () => {
      if (b.disabled) return;
      selected = b.dataset.finalQuality;
      $$('[data-final-quality]', list).forEach(x => x.classList.remove('selected'));
      b.classList.add('selected');
      const label = $('#qualityLabel');
      if (label) label.textContent = `${selected} selected`;
      const download = $('#vlDownloadBtn');
      if (download) download.disabled = false;
      window.VidLoomQuality = selected;
      window.VidLoomSelectedQuality = () => selected;
    });

    const download = $('#vlDownloadBtn');
    if (download) download.disabled = !selected;
  }

  async function fetchQualityInfo(url) {
    if (!url || url === currentUrl) return;
    currentUrl = url;
    selected = null;
    const list = hostList();
    if (list) list.innerHTML = '<div class="vl-empty" style="padding:25px 5px;font-size:12px">Detecting real source qualities…</div>';
    try {
      const r = await fetch('/api/quality-info', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({url})
      });
      const d = await r.json();
      if (!r.ok || !d.ok) throw new Error(d.error || 'Could not detect source qualities.');
      currentVideo = d;
      renderQuality(d);
      const meta = $('#vlMeta');
      if (meta) meta.textContent = `${d.title || 'Media'} · Real source formats detected`;
    } catch (e) {
      if (list) list.innerHTML = `<div class="vl-empty" style="padding:25px 5px;font-size:12px"><strong>Quality detection failed</strong><br>${esc(e.message || 'Try Fetch media again.')}</div>`;
    }
  }

  function hideObsolete() {
    const obsolete = /The source did not expose a detailed quality list|The source did not expose|safe best available fallback|Only qualities exposed by the source are offered/i;
    document.querySelectorAll('body *').forEach(el => {
      if (el.children.length === 0 && obsolete.test(el.textContent || '')) el.style.display = 'none';
    });
  }

  function progressPanel() {
    const host = $('#vlProgress');
    if (!host) return;
    host.innerHTML = `<div class="vl-progress"><div class="vl-progress-head"><b id="finalProgressTitle">Preparing download...</b><b id="finalProgressPct">0%</b></div><div class="vl-track"><div id="finalProgressFill" class="vl-fill" style="width:0"></div></div><div class="vl-progress-stats"><span id="finalAmount">0 B / —</span><span id="finalSpeed">—</span><span id="finalEta">ETA —</span></div><div class="vl-progress-actions"><button id="finalPause" type="button">Pause</button><button id="finalResume" type="button" hidden>Resume</button><button id="finalCancel" type="button" class="cancel">Cancel</button></div><div id="finalMessage" class="vl-notice">Starting...</div></div>`;
    $('#finalPause').onclick = () => control('pause');
    $('#finalResume').onclick = () => control('resume');
    $('#finalCancel').onclick = () => control('cancel');
  }

  function updateProgress(j) {
    const pct = Math.max(0, Math.min(100, Number(j.percent || 0)));
    if ($('#finalProgressFill')) $('#finalProgressFill').style.width = `${pct}%`;
    if ($('#finalProgressPct')) $('#finalProgressPct').textContent = `${Math.round(pct)}%`;
    if ($('#finalAmount')) $('#finalAmount').textContent = `${bytes(j.downloaded_bytes)} / ${j.total_bytes ? bytes(j.total_bytes) : '—'}`;
    if ($('#finalSpeed')) $('#finalSpeed').textContent = j.speed ? `${bytes(j.speed)}/s` : '—';
    if ($('#finalEta')) $('#finalEta').textContent = eta(j.eta);
    if ($('#finalProgressTitle')) $('#finalProgressTitle').textContent = j.title || currentVideo?.title || 'Downloading...';
  }

  async function control(action) {
    if (!jobId) return;
    try {
      const r = await fetch(`/api/download/${jobId}/${action}`, {method:'POST'});
      const d = await r.json();
      if (!r.ok || !d.ok) throw new Error(d.error || `Could not ${action} download.`);
      if ($('#finalPause')) $('#finalPause').hidden = action === 'pause';
      if ($('#finalResume')) $('#finalResume').hidden = action !== 'pause';
      if ($('#finalMessage')) $('#finalMessage').textContent = action === 'cancel' ? 'Download cancelled.' : action === 'pause' ? 'Download paused.' : 'Resuming...';
    } catch (e) { if ($('#finalMessage')) $('#finalMessage').textContent = e.message; }
  }

  async function startDownload() {
    if (!currentVideo || !selected) return;
    const button = $('#vlDownloadBtn');
    if (button) { button.disabled = true; button.textContent = 'Starting...'; }
    progressPanel();
    try {
      const r = await fetch('/api/download', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({url: currentVideo.url || currentUrl, mode:selectedMode, quality:selected})
      });
      const d = await r.json();
      if (!r.ok || !d.ok || !d.job_id) throw new Error(d.error || 'Could not start download.');
      jobId = d.job_id;
      for (;;) {
        await new Promise(resolve => setTimeout(resolve, 850));
        const sr = await fetch(`/api/download/${jobId}/status`);
        const sd = await sr.json();
        if (!sr.ok || !sd.ok) throw new Error(sd.error || 'Could not read download status.');
        const j = sd.job || {};
        updateProgress(j);
        if ($('#finalMessage')) $('#finalMessage').textContent = j.status === 'downloading' ? 'Downloading...' : j.status === 'processing' ? 'Processing video...' : j.status === 'paused' ? 'Download paused.' : 'Preparing...';
        if (j.status === 'cancelled') break;
        if (j.status === 'error') throw new Error(j.error || 'Download failed.');
        if (j.status === 'completed') {
          updateProgress({...j, percent:100});
          const fr = await fetch(`/api/download/${jobId}/file`);
          if (!fr.ok) throw new Error('Could not retrieve the downloaded file.');
          const blob = await fr.blob();
          if (!blob.size) throw new Error('Downloaded file is empty.');
          const u = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = u;
          const clean = (currentVideo?.title || 'video').replace(/[^\w\s.-]/g,'').trim().slice(0,90) || 'video';
          a.download = `${clean}.${selectedMode === 'audio' ? 'mp3' : 'mp4'}`;
          document.body.appendChild(a); a.click(); a.remove();
          setTimeout(() => URL.revokeObjectURL(u), 15000);
          if ($('#finalMessage')) $('#finalMessage').textContent = 'Download finished. Check your browser downloads.';
          break;
        }
      }
    } catch (e) {
      if ($('#finalMessage')) $('#finalMessage').textContent = e.message || 'Download failed.';
    } finally {
      if (button) { button.disabled = !selected; button.textContent = `⇩ Download ${selectedMode === 'audio' ? 'MP3' : 'MP4'}`; }
    }
  }

  function boot() {
    hideObsolete();
    // Remove every older quality controller from the DOM/script behavior by
    // making this controller the last writer to the visible quality panel.
    setInterval(hideObsolete, 500);

    const input = $('#url');
    const fetchButton = $('#fetchBtn');
    if (fetchButton) fetchButton.addEventListener('click', () => {
      const u = input?.value?.trim() || '';
      if (u) setTimeout(() => fetchQualityInfo(u), 250);
    });

    document.addEventListener('vidloom:media-loaded', e => {
      const u = e.detail?.video?.url || input?.value?.trim() || '';
      if (u) fetchQualityInfo(u);
    });

    $$('.vl-tab').forEach(b => b.addEventListener('click', () => {
      $$('.vl-tab').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      selectedMode = b.dataset.mode || 'video';
      const button = $('#vlDownloadBtn');
      if (button) button.textContent = `⇩ Download ${selectedMode === 'audio' ? 'MP3' : 'MP4'}`;
    }));

    const download = $('#vlDownloadBtn');
    if (download) download.onclick = startDownload;

    hideObsolete();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
