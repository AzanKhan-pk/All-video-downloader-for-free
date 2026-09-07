(() => {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  let media = null;
  let mode = 'video';
  let quality = '720p';

  const style = document.createElement('style');
  style.textContent = `
    #downloader { display:none!important }
    #vidloom-app { max-width:1180px; margin:35px auto 80px; padding:0 18px; font-family:Manrope,system-ui,sans-serif }
    .vl-card { background:#070d20; border:1px solid #263b73; border-radius:18px; padding:22px; box-shadow:0 18px 55px rgba(0,0,0,.22) }
    .vl-title { font-size:30px; font-weight:800; margin:0 0 8px; color:#fff }
    .vl-sub { color:#9da9c8; margin:0 0 22px }
    .vl-form { display:flex; gap:10px }
    .vl-form input { flex:1; min-width:0; padding:15px 16px; border-radius:11px; border:1px solid #30477f; background:#050a18; color:#fff; outline:none }
    .vl-btn { border:0; border-radius:11px; padding:0 22px; background:linear-gradient(100deg,#6424ff,#087fff); color:#fff; font-weight:800; cursor:pointer }
    .vl-btn:disabled { opacity:.55; cursor:wait }
    .vl-result { margin-top:18px; display:none; grid-template-columns:1fr 330px; gap:18px }
    .vl-preview { overflow:hidden; border-radius:13px; border:1px solid #263b73; background:#030714 }
    .vl-preview img { width:100%; aspect-ratio:16/9; object-fit:cover; display:block }
    .vl-info { padding:15px }
    .vl-info h3 { color:#fff; margin:0 0 7px; font-size:19px }
    .vl-info p { color:#9da9c8; margin:4px 0; font-size:12px }
    .vl-controls { border:1px solid #263b73; border-radius:13px; padding:17px; background:#060c1d }
    .vl-tabs { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:15px }
    .vl-tab { padding:11px; border-radius:9px; border:1px solid #2a4077; background:#0a1229; color:#b9c4df; cursor:pointer }
    .vl-tab.active { background:#5224e9; color:#fff; border-color:#6b56ff }
    .vl-controls label { display:block; color:#9da9c8; font-size:12px; margin:12px 0 7px }
    .vl-controls select { width:100%; padding:11px; border-radius:9px; border:1px solid #2a4077; background:#0a1229; color:#fff }
    .vl-download { width:100%; padding:13px; margin-top:15px }
    .vl-status { margin-top:14px; min-height:20px; color:#9da9c8; font-size:12px }
    .vl-status.error { color:#ff9c9c } .vl-status.ok { color:#7ee2b0 }
    .vl-note { margin-top:12px; color:#7583a5; font-size:11px; line-height:1.5 }
    @media(max-width:800px){ .vl-result{grid-template-columns:1fr} .vl-form{flex-direction:column}.vl-btn{padding:13px} }
  `;
  document.head.appendChild(style);

  const app = document.createElement('section');
  app.id = 'vidloom-app';
  app.innerHTML = `
    <div class="vl-card">
      <h2 class="vl-title">VidLoom Video Downloader</h2>
      <p class="vl-sub">Download public media from supported websites. No login or DRM bypass.</p>
      <div class="vl-form"><input id="vl-url" type="url" placeholder="Paste a public video URL…" autocomplete="off"><button id="vl-fetch" class="vl-btn">Fetch media</button></div>
      <div id="vl-status" class="vl-status"></div>
      <div id="vl-result" class="vl-result">
        <div class="vl-preview"><img id="vl-thumb" alt="Media thumbnail"><div class="vl-info"><h3 id="vl-title"></h3><p id="vl-meta"></p></div></div>
        <div class="vl-controls">
          <div class="vl-tabs"><button class="vl-tab active" data-mode="video">Video</button><button class="vl-tab" data-mode="audio">Audio</button></div>
          <label for="vl-quality">Quality</label><select id="vl-quality"></select>
          <button id="vl-download" class="vl-btn vl-download">Download</button>
          <div class="vl-note">Vercel's free serverless environment cannot keep a background download running. This version downloads in the same request and avoids server-side FFmpeg merging.</div>
        </div>
      </div>
    </div>`;
  document.body.appendChild(app);

  const input = $('#vl-url'), fetchBtn = $('#vl-fetch'), status = $('#vl-status'), result = $('#vl-result');
  const qualitySelect = $('#vl-quality'), downloadBtn = $('#vl-download');

  function setStatus(text, type='') { status.textContent = text; status.className = `vl-status ${type}`; }
  function esc(s) { return String(s || '').replace(/[&<>\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

  function renderQualities() {
    const qs = Array.isArray(media?.available_qualities) ? media.available_qualities : [];
    qualitySelect.innerHTML = '';
    const values = qs.length ? qs : ['360p','480p','720p','1080p'];
    values.forEach(q => { const o = document.createElement('option'); o.value=q; o.textContent=q; qualitySelect.appendChild(o); });
    quality = values.includes('720p') ? '720p' : values[0]; qualitySelect.value = quality;
    qualitySelect.disabled = mode === 'audio';
  }

  async function fetchMedia() {
    const url = input.value.trim();
    if (!url) return setStatus('Paste a public video URL first.', 'error');
    fetchBtn.disabled = true; setStatus('Reading media information…');
    try {
      const r = await fetch('/api/info', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url}) });
      const d = await r.json();
      if (!r.ok || !d.ok) throw new Error(d.error || 'Could not read this media.');
      media = d.video || d;
      $('#vl-title').textContent = media.title || 'Untitled media';
      $('#vl-meta').textContent = `${media.platform || 'Media'} · ${media.duration || 'Duration unavailable'} · ${media.views || 'Views unavailable'}`;
      const thumb = $('#vl-thumb');
      if (media.thumbnail) { thumb.src = media.thumbnail; thumb.style.display='block'; } else thumb.style.display='none';
      result.style.display = 'grid'; renderQualities(); setStatus(`${media.platform || 'Media'} found.`, 'ok');
    } catch (e) { result.style.display='none'; setStatus(e.message || 'Could not read this link.', 'error'); }
    finally { fetchBtn.disabled=false; }
  }

  async function download() {
    if (!media) return;
    downloadBtn.disabled = true; setStatus('Preparing your download…');
    try {
      const r = await fetch('/api/download', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url:media.url || input.value, mode, quality}) });
      const type = r.headers.get('content-type') || '';
      if (!r.ok || type.includes('application/json')) { const d=await r.json().catch(()=>({})); throw new Error(d.error || 'Download failed.'); }
      const blob = await r.blob();
      if (!blob.size) throw new Error('The server returned an empty file.');
      const cd = r.headers.get('content-disposition') || '';
      const match = cd.match(/filename="?([^";]+)"?/i);
      const ext = mode === 'audio' ? 'audio' : 'mp4';
      const name = match ? match[1] : `${(media.title || 'video').replace(/[^\w\s.-]/g,'').trim() || 'video'}.${ext}`;
      const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=name; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(()=>URL.revokeObjectURL(a.href),15000); setStatus('Download complete. Check your browser downloads.', 'ok');
    } catch (e) { setStatus(e.message || 'Download failed.', 'error'); }
    finally { downloadBtn.disabled=false; }
  }

  document.addEventListener('click', e => { const tab=e.target.closest('.vl-tab'); if(!tab)return; document.querySelectorAll('.vl-tab').forEach(x=>x.classList.remove('active'));tab.classList.add('active');mode=tab.dataset.mode;renderQualities(); });
  qualitySelect.addEventListener('change', e => quality=e.target.value);
  fetchBtn.addEventListener('click', fetchMedia); input.addEventListener('keydown', e => { if(e.key==='Enter') fetchMedia(); }); downloadBtn.addEventListener('click', download);
})();
