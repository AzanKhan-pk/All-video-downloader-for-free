(() => {
  'use strict';

  const QUALITY_ORDER = [
    ['144p', 144], ['240p', 240], ['360p', 360], ['480p', 480],
    ['720p', 720], ['1080p', 1080], ['1440p', 1440], ['4K', 2160]
  ];
  let selectedQuality = '720p';
  let selectedMode = 'video';
  let currentVideo = null;
  let loadingInfo = false;
  let downloadJob = null;

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = v => String(v ?? '').replace(/[&<>'"]/g, c => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;'
  }[c]));
  const bytes = n => {
    n = Number(n || 0);
    if (!n) return '—';
    const u = ['B','KB','MB','GB','TB'];
    const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), u.length - 1);
    return `${(n / Math.pow(1024, i)).toFixed(i ? 2 : 0)} ${u[i]}`;
  };
  const eta = n => {
    n = Number(n);
    if (!Number.isFinite(n) || n < 0) return 'ETA —';
    if (n < 60) return `ETA ${Math.ceil(n)}s`;
    return `ETA ${Math.floor(n / 60)}m ${Math.ceil(n % 60)}s`;
  };

  function injectStyle() {
    if ($('#vl-quality-runtime-style')) return;
    const s = document.createElement('style');
    s.id = 'vl-quality-runtime-style';
    s.textContent = `
      .vl-quality{position:relative!important;min-height:45px!important}
      .vl-quality .q-main{display:flex;align-items:center;gap:8px;font-weight:700}
      .vl-quality .q-size{font-size:10px;color:#8492b4}
      .vl-quality.available{border-color:#2d579c!important}
      .vl-quality.selected{border-color:#5d72ff!important;background:linear-gradient(90deg,rgba(76,40,255,.38),rgba(17,105,225,.24))!important}
      .vl-quality.unavailable{opacity:.38!important;cursor:not-allowed!important}
      .vl-quality.unavailable::after{content:'Not available';margin-left:auto;font-size:9px;color:#9aa5bf}
      .vl-quality-loading{padding:24px 8px;text-align:center;color:#8b98b8;font-size:11px}
      .vl-real-source{font-size:10px!important;color:#58cfff!important}
      .vl-real-source.error{color:#ff9d9d!important}
      .vl-download-btn.ready{background:linear-gradient(100deg,#6522ff,#078bff)!important}
      .vl-download-btn.ready:disabled{opacity:.45!important}
      .vl-runtime-progress{margin-top:14px;padding:13px;border:1px solid #263b6c;border-radius:10px;background:#060d20}
      .vl-runtime-progress .head,.vl-runtime-progress .stats{display:flex;justify-content:space-between;gap:8px;font-size:11px}
      .vl-runtime-progress .stats{margin-top:8px;color:#8e9ab8;font-size:10px;flex-wrap:wrap}
      .vl-runtime-track{height:7px;margin-top:10px;border-radius:99px;background:#111d3c;overflow:hidden}
      .vl-runtime-fill{height:100%;width:0;background:linear-gradient(90deg,#5b25ff,#16a5ff);transition:width .25s ease}
      .vl-runtime-actions{display:flex;gap:7px;margin-top:10px}.vl-runtime-actions button{flex:1;padding:8px;border:1px solid #2b4177;border-radius:7px;background:#0b1530;color:#dce5ff;cursor:pointer;font-size:11px}
      @media(max-width:560px){.vl-quality .q-size{display:none}}
    `;
    document.head.appendChild(s);
  }

  function sourceUrl() {
    return String($('#url')?.value || $('#vlInnerSearch')?.value || $('#vlAddress')?.value || '').trim();
  }

  function qualityData(video) {
    const qualities = Array.isArray(video?.qualities) ? video.qualities : [];
    const formats = Array.isArray(video?.formats) ? video.formats : [];
    const byHeight = new Map();
    qualities.forEach(q => {
      const h = Number(q.height || 0);
      if (h) byHeight.set(h, q);
    });
    formats.forEach(f => {
      const h = Number(f.height || 0);
      if (h >= 144 && !byHeight.has(h)) byHeight.set(h, {
        height:h, label:h >= 2160 ? '4K' : `${h}p`, available:true,
        has_audio:f.acodec && f.acodec !== 'none', filesize:f.filesize || 0
      });
    });
    return QUALITY_ORDER.map(([label,height]) => {
      const q = byHeight.get(height);
      return {label,height,available:Boolean(q?.available),hasAudio:Boolean(q?.has_audio),filesize:Number(q?.filesize || 0)};
    });
  }

  function renderQualities(video) {
    const list = $('#vlQualities');
    const source = $('.vl-quality-head span');
    if (!list) return;
    const data = qualityData(video);
    const available = data.filter(q => q.available);
    if (source) {
      source.textContent = available.length
        ? `${available.length} real source qualities`
        : 'No video qualities exposed';
      source.classList.add('vl-real-source');
      source.classList.toggle('error', !available.length);
    }
    if (!available.some(q => q.label === selectedQuality)) {
      selectedQuality = available.length ? available[available.length - 1].label : '720p';
    }
    list.innerHTML = data.map(q => `
      <button type="button" class="vl-quality ${q.available ? 'available' : 'unavailable'} ${q.available && q.label === selectedQuality ? 'selected' : ''}" data-vl-quality="${q.label}" ${q.available ? '' : 'disabled'}>
        <span class="q-main">${esc(q.label)}${q.hasAudio ? ' 🔊' : ''}</span>
        <small class="q-size">${q.filesize ? esc(bytes(q.filesize)) : (q.available ? 'Source available' : 'Unavailable')}</small>
      </button>
    `).join('');
    $$('.vl-quality[data-vl-quality]').forEach(b => b.addEventListener('click', () => {
      if (b.disabled) return;
      selectedQuality = b.dataset.vlQuality;
      $$('.vl-quality').forEach(x => x.classList.remove('selected'));
      b.classList.add('selected');
      updateDownloadButton();
    }));
    updateDownloadButton();
  }

  function updateDownloadButton() {
    const b = $('#vlDownloadBtn');
    if (!b) return;
    const selected = $(`.vl-quality[data-vl-quality="${CSS.escape(selectedQuality)}"]`);
    const valid = selected && !selected.disabled && currentVideo;
    b.disabled = !valid || Boolean(downloadJob);
    b.classList.toggle('ready', Boolean(valid));
    b.textContent = selectedMode === 'audio'
      ? '⇩ Download MP3'
      : `⇩ Download ${selectedQuality}`;
  }

  async function fetchInfo(url) {
    if (!url || loadingInfo) return;
    if (!/^https?:\/\//i.test(url)) return;
    loadingInfo = true;
    const list = $('#vlQualities');
    const source = $('.vl-quality-head span');
    if (list) list.innerHTML = '<div class="vl-quality-loading">Detecting real source qualities…</div>';
    if (source) source.textContent = 'Reading source…';
    try {
      const response = await fetch('/api/info', {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url})
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || 'Could not read this media.');
      currentVideo = data.video || data;
      renderQualities(currentVideo);
      renderPreview(currentVideo, url);
      const meta = $('#vlMeta');
      if (meta) meta.textContent = `${currentVideo.title || 'Media'} · ${currentVideo.platform || 'Supported platform'} · ${currentVideo.duration || 'Duration unavailable'}`;
    } catch (e) {
      currentVideo = null;
      if (list) list.innerHTML = `<div class="vl-quality-loading">${esc(e.message || 'Could not detect media qualities.')}</div>`;
      if (source) { source.textContent = 'Quality detection failed'; source.classList.add('error'); }
      updateDownloadButton();
    } finally { loadingInfo = false; }
  }

  function renderPreview(video, url) {
    const p = $('#vlPreview');
    if (!p) return;
    const title = video?.title || 'Public media';
    if (video?.thumbnail) {
      p.innerHTML = `<div class="vl-preview-card"><img src="${esc(video.thumbnail)}" alt="Media thumbnail"><div class="vl-preview-info"><h3>${esc(title)}</h3><p>${esc(video.creator || '')} · ${esc(video.platform || '')}</p></div></div>`;
    }
  }

  async function startDownload() {
    if (!currentVideo || downloadJob) return;
    const selected = $(`.vl-quality[data-vl-quality="${CSS.escape(selectedQuality)}"]`);
    if (selectedMode === 'video' && (!selected || selected.disabled)) {
      alert(`The quality you selected (${selectedQuality}) is not available. Select another quality.`);
      return;
    }
    const b = $('#vlDownloadBtn');
    if (b) { b.disabled = true; b.textContent = 'Starting…'; }
    try {
      const response = await fetch('/api/download', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({url:currentVideo.url || sourceUrl(),mode:selectedMode,quality:selectedQuality})
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || 'Could not start download.');
      downloadJob = data.job_id;
      renderProgress('Preparing download…');
      await pollDownload(data.job_id);
    } catch (e) {
      renderProgress(`Error: ${e.message || 'Download failed.'}`, true);
      downloadJob = null; updateDownloadButton();
    }
  }

  function renderProgress(message, error=false) {
    let box = $('#vlRuntimeProgress');
    if (!box) {
      box = document.createElement('div'); box.id = 'vlRuntimeProgress'; box.className = 'vl-runtime-progress';
      $('#vlDownload')?.appendChild(box);
    }
    box.innerHTML = `<div class="head"><strong id="vlRPTitle">${esc(message)}</strong><b id="vlRPPct">0%</b></div><div class="vl-runtime-track"><div id="vlRPFill" class="vl-runtime-fill"></div></div><div class="stats"><span id="vlRPSize">0 B / —</span><span id="vlRPSpeed">Speed —</span><span id="vlRPEta">ETA —</span></div><div class="vl-runtime-actions"><button id="vlRPPause" type="button">Pause</button><button id="vlRPResume" type="button" hidden>Resume</button><button id="vlRPCancel" type="button">Cancel</button></div><div id="vlRPMsg" style="margin-top:8px;font-size:10px;color:${error ? '#ff9d9d' : '#8794b6'}">${esc(message)}</div>`;
    $('#vlRPPause').onclick = () => controlJob('pause');
    $('#vlRPResume').onclick = () => controlJob('resume');
    $('#vlRPCancel').onclick = () => controlJob('cancel');
  }

  async function controlJob(action) {
    if (!downloadJob) return;
    try {
      const r = await fetch(`/api/download/${downloadJob}/${action}`, {method:'POST'});
      const d = await r.json();
      if (!r.ok || !d.ok) throw new Error(d.error || `Could not ${action} download.`);
      const pause = $('#vlRPPause'), resume = $('#vlRPResume');
      if (pause) pause.hidden = action === 'pause';
      if (resume) resume.hidden = action !== 'pause';
      const m = $('#vlRPMsg'); if (m) m.textContent = action === 'cancel' ? 'Cancelling…' : `${action[0].toUpperCase()+action.slice(1)} requested.`;
    } catch (e) { const m=$('#vlRPMsg'); if(m)m.textContent=e.message; }
  }

  async function pollDownload(id) {
    while (downloadJob === id) {
      await new Promise(r => setTimeout(r, 850));
      const response = await fetch(`/api/download/${id}/status`);
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || 'Could not read download status.');
      const j = data.job || {};
      const pct = Math.max(0, Math.min(100, Number(j.percent || 0)));
      const fill=$('#vlRPFill'), p=$('#vlRPPct'), size=$('#vlRPSize'), speed=$('#vlRPSpeed'), e=$('#vlRPEta'), title=$('#vlRPTitle');
      if(fill)fill.style.width=`${pct}%`; if(p)p.textContent=`${Math.round(pct)}%`;
      if(size)size.textContent=`${bytes(j.downloaded_bytes)} / ${j.total_bytes ? bytes(j.total_bytes) : '—'}`;
      if(speed) speed.textContent=`Speed ${j.speed ? bytes(j.speed)+'/s' : '—'}`;
      if(e)e.textContent=eta(j.eta);
      if(title)title.textContent=j.title || 'Downloading…';
      const msg=$('#vlRPMsg');
      if(j.status === 'paused'){if(msg)msg.textContent='Download paused.';continue}
      if(j.status === 'network_error'){if(msg)msg.textContent=j.error || 'Network issue — use Resume.';continue}
      if(j.status === 'processing'){if(msg)msg.textContent='Processing video…';continue}
      if(j.status === 'error') throw new Error(j.error || 'Download failed.');
      if(j.status === 'cancelled'){if(msg)msg.textContent='Download cancelled.';downloadJob=null;updateDownloadButton();return}
      if(j.status === 'completed'){
        if(fill)fill.style.width='100%';if(p)p.textContent='100%';if(msg)msg.textContent='Download complete. Preparing file…';
        const fileResponse=await fetch(`/api/download/${id}/file`);
        if(!fileResponse.ok) throw new Error('Could not retrieve the completed file.');
        const blob=await fileResponse.blob();
        const u=URL.createObjectURL(blob),a=document.createElement('a');
        const safe=(j.title||currentVideo?.title||'video').replace(/[^\w\s.-]/g,'').trim().slice(0,90)||'video';
        a.href=u;a.download=`${safe}.${selectedMode==='audio'?'mp3':'mp4'}`;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),15000);
        if(msg)msg.textContent='Finished. Check your browser downloads.';downloadJob=null;updateDownloadButton();return;
      }
    }
  }

  function hookModeButtons() {
    $$('.vl-tab').forEach(b => b.addEventListener('click', () => {
      selectedMode = b.dataset.mode || 'video';
      const list=$('#vlQualities');
      if(selectedMode==='audio') {
        if(list)list.innerHTML='<button type="button" class="vl-quality selected" disabled><span class="q-main">♫ 192 kbps</span><small class="q-size">High quality audio</small></button>';
      } else if(currentVideo) renderQualities(currentVideo);
      updateDownloadButton();
    }));
    $('#vlDownloadBtn')?.addEventListener('click', startDownload);
  }

  function boot() {
    injectStyle();
    hookModeButtons();
    const url = sourceUrl();
    if (url && /^https?:\/\//i.test(url)) setTimeout(() => fetchInfo(url), 250);

    document.addEventListener('click', e => {
      const site=e.target.closest('.vl-site');
      if(site) setTimeout(()=>{const u=sourceUrl();if(u.startsWith('http'))fetchInfo(u)},350);
    });

    const observer = new MutationObserver(() => {
      if (!$('#vlQualities')) return;
      if (!$('#vlDownloadBtn')?.dataset.vlRuntimeBound) {
        const b=$('#vlDownloadBtn');
        if(b){b.dataset.vlRuntimeBound='1';b.addEventListener('click',startDownload)}
      }
      updateDownloadButton();
    });
    observer.observe(document.body,{subtree:true,childList:true});
  }

  boot();
})();
