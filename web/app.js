'use strict';

const $ = (id) => document.getElementById(id);
const kinds = ['original', 'depth'];
const files = { original: null, depth: null };
const urls = {};
let config = null;
let busy = false;
let activeId = null;
let selectedJob = null;
let uploadRequest = null;
let cancelled = false;
let pollTimer = null;
let previewMode = 'video';
let lastJobs = [];
let saving = false;

const sizeLabel = (n) => n >= 1024 ** 3 ? `${(n / 1024 ** 3).toFixed(2)} GB` : `${(n / 1024 ** 2).toFixed(1)} MB`;
const timeLabel = (n) => `${Math.floor(n / 60)}:${String(Math.floor(n % 60)).padStart(2, '0')}`;
const icon = (name) => { const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); const use = document.createElementNS(svg.namespaceURI, 'use'); use.setAttribute('href', `#i-${name}`); svg.append(use); return svg; };

async function api(path, body, method = 'POST') {
  const response = await fetch(path, { method, headers: { 'Content-Type': 'application/json', 'X-Mesh-Token': config?.token || '' }, body: body === undefined ? undefined : JSON.stringify(body) });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function error(message, title = 'Something needs a second look') {
  $('error-title').textContent = title;
  $('error-message').textContent = message;
  $('error-banner').hidden = false;
}

function updateButton() {
  $('create-button').disabled = busy || !config?.ready || !files.original || !files.depth;
  $('create-button').querySelector('span').textContent = busy ? 'Creating your wireframe…' : 'Create wireframe';
  $('create-hint').textContent = busy ? 'Keep this window open, or return to this run later.' : !config?.ready ? 'Connecting to your local engine' : files.original && files.depth ? 'Ready when you are. Processing stays on this PC.' : files.original ? 'Add the matching depth video to continue' : files.depth ? 'Add the original video to continue' : 'Add both videos to get started';
  kinds.forEach((kind) => { $(`file-${kind}`).disabled = busy; });
}

function setBusy(value) {
  busy = value;
  document.body.classList.toggle('busy', value);
  $('cancel-button').disabled = !value;
  updateButton();
  renderHistory(lastJobs);
}

function setFile(kind, file) {
  if (busy) return;
  if (file) {
    if (!/\.(mp4|mov|mkv|webm|m4v|avi)$/i.test(file.name)) return error('Choose an MP4, MOV, MKV, WebM, M4V or AVI video.');
    if (!file.size || file.size > (config?.max_upload_bytes || 4 * 1024 ** 3)) return error('Each video must be nonempty and no larger than 4 GB.');
  }
  const video = $(`preview-${kind}`);
  video.pause();
  video.removeAttribute('src');
  video.load();
  if (urls[kind]) URL.revokeObjectURL(urls[kind]);
  files[kind] = file || null;
  const zone = $(`drop-${kind}`);
  zone.classList.toggle('has-file', !!file);
  zone.querySelector('label').hidden = !!file;
  video.hidden = !file;
  $(`remove-${kind}`).hidden = !file;
  $('error-banner').hidden = true;
  if (file) {
    urls[kind] = URL.createObjectURL(file);
    video.src = urls[kind];
    video.onloadedmetadata = () => { $(`meta-${kind}`).textContent = `${video.videoWidth} × ${video.videoHeight} · ${timeLabel(video.duration)} · ${sizeLabel(file.size)}`; };
    video.onerror = () => { $(`meta-${kind}`).textContent = `${sizeLabel(file.size)} · Preview unavailable`; };
    $(`name-${kind}`).textContent = file.name;
    $(`name-${kind}`).title = file.name;
    $(`meta-${kind}`).textContent = sizeLabel(file.size);
  } else {
    $(`file-${kind}`).value = '';
    $(`name-${kind}`).textContent = kind === 'original' ? 'The video with the facial motion' : 'The matching depth-map export';
    $(`meta-${kind}`).textContent = kind === 'original' ? 'MP4, MOV & more' : 'Same framing & start point';
  }
  updateButton();
}

kinds.forEach((kind) => {
  $(`file-${kind}`).addEventListener('change', (event) => setFile(kind, event.target.files[0]));
  $(`remove-${kind}`).addEventListener('click', () => setFile(kind, null));
  const zone = $(`drop-${kind}`);
  ['dragenter', 'dragover'].forEach((name) => zone.addEventListener(name, (event) => { event.preventDefault(); if (!busy) zone.classList.add('drag-over'); }));
  ['dragleave', 'drop'].forEach((name) => zone.addEventListener(name, () => zone.classList.remove('drag-over')));
  zone.addEventListener('drop', (event) => { event.preventDefault(); if (!busy && event.dataTransfer.files.length) setFile(kind, event.dataTransfer.files[0]); });
});

function settings() {
  return { style: $('style').value, max_faces: Number($('max-faces').value), color: $('color').value.slice(1).toUpperCase(), thickness: Number($('thickness').value), opacity: Number($('opacity').value) / 100, smoothing_ms: 12 };
}

function updateSettings() {
  $('opacity-value').textContent = `${$('opacity').value}%`;
  $('color-value').textContent = $('color').value.toUpperCase();
  const name = { mesh: 'Dense mesh', contours: 'Contours', dots: 'Dots' }[$('style').value];
  const color = $('color').value.toUpperCase() === '#00FFFF' ? 'Cyan' : $('color').value.toUpperCase();
  $('settings-summary').textContent = `${name} · ${color} · Up to ${$('max-faces').value} faces`;
}
['style', 'max-faces', 'color', 'thickness', 'opacity'].forEach((id) => $(id).addEventListener('input', updateSettings));

function showProgress(stage, progress, message) {
  $('progress-card').hidden = false;
  $('progress-message').textContent = message;
  $('progress-percent').textContent = `${Math.round(progress)}%`;
  $('progress-bar').value = progress;
  const stages = ['uploading', 'checking', 'tracking', 'rendering', 'verifying', 'complete'];
  const current = stages.indexOf(stage);
  document.querySelectorAll('.stage-list li').forEach((item) => {
    const index = stages.indexOf(item.dataset.stage);
    item.classList.toggle('active', index === current);
    item.classList.toggle('done', index < current);
  });
  $('rendering-overlay').hidden = false;
  $('rendering-label').textContent = stage === 'uploading' ? 'Bringing your videos into the workspace' : stage === 'tracking' ? 'Following every expression' : stage === 'rendering' ? 'Connecting the dots' : stage === 'verifying' ? 'Checking the finishing touches' : 'Preparing your wireframe';
}

function upload(jobId, kind, completed, total) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    uploadRequest = xhr;
    xhr.open('PUT', `/api/jobs/${jobId}/uploads/${kind}`);
    xhr.setRequestHeader('X-Mesh-Token', config.token);
    xhr.setRequestHeader('Content-Type', 'application/octet-stream');
    xhr.upload.onprogress = (event) => { if (event.lengthComputable) showProgress('uploading', (completed + event.loaded) / total * 10, `Uploading ${kind} video · ${sizeLabel(completed + event.loaded)} of ${sizeLabel(total)}`); };
    xhr.onload = () => {
      uploadRequest = null;
      try { const data = JSON.parse(xhr.responseText); if (xhr.status >= 400) throw new Error(data.error || 'Upload failed'); resolve(data); } catch (e) { reject(e); }
    };
    xhr.onerror = () => { uploadRequest = null; reject(new Error('The local connection was interrupted. Check that Mesh Studio is still running, then try again.')); };
    xhr.onabort = () => { uploadRequest = null; reject(new DOMException('Run cancelled', 'AbortError')); };
    xhr.send(files[kind]);
  });
}

function resetResult() {
  selectedJob = null;
  const video = $('result-video');
  video.pause(); video.removeAttribute('src'); video.load(); video.hidden = true;
  $('empty-result').hidden = false;
  $('result-notes').hidden = true;
  $('save-button').disabled = true;
  $('view-result').disabled = true;
  $('view-comparison').disabled = true;
  $('output-state').textContent = 'PROCESSING';
  $('output-state').classList.remove('complete');
  $('result-format').textContent = 'H.264 MP4';
  $('result-detail').textContent = 'Original depth resolution';
}

$('create-button').addEventListener('click', async () => {
  if (busy || !files.original || !files.depth) return;
  cancelled = false;
  $('error-banner').hidden = true;
  resetResult();
  setBusy(true);
  showProgress('uploading', 0, 'Preparing your videos');
  kinds.forEach((kind) => $(`preview-${kind}`).pause());
  try {
    const job = await api('/api/jobs', { original: { name: files.original.name, size: files.original.size }, depth: { name: files.depth.name, size: files.depth.size }, settings: settings() });
    activeId = job.id;
    localStorage.setItem('mesh-active-job', activeId);
    if (cancelled) { await api(`/api/jobs/${activeId}/cancel`); return; }
    const total = files.original.size + files.depth.size;
    await upload(activeId, 'original', 0, total);
    if (cancelled) return;
    await upload(activeId, 'depth', files.original.size, total);
    if (cancelled) return;
    await api(`/api/jobs/${activeId}/start`);
    refreshHistory();
    pollJob();
  } catch (e) {
    if (activeId) { try { await api(`/api/jobs/${activeId}/cancel`); } catch (_) { /* reconnect via next run */ } }
    if (e.name !== 'AbortError' && !cancelled) error(e.message);
    finishBusy();
  } finally {
    if (cancelled) finishBusy();
  }
});

function finishBusy() {
  clearTimeout(pollTimer);
  setBusy(false);
  $('progress-card').hidden = true;
  $('rendering-overlay').hidden = true;
  if (!selectedJob) $('output-state').textContent = 'PREVIEW';
  localStorage.removeItem('mesh-active-job');
  activeId = null;
  refreshHistory();
}

async function pollJob() {
  if (!activeId || cancelled) return;
  try {
    const response = await fetch(`/api/jobs/${activeId}`, { cache: 'no-store' });
    const job = await response.json();
    if (!response.ok) throw new Error(job.error || 'Cannot find this run.');
    if (job.status === 'complete') { finishBusy(); showResult(job); return; }
    if (job.status === 'failed') { finishBusy(); error(job.message, 'This run could not finish'); return; }
    if (job.status === 'cancelled') { finishBusy(); return; }
    showProgress(job.stage, job.status === 'queued' ? 10 : 10 + job.progress * .9, job.message);
    pollTimer = setTimeout(pollJob, 900);
  } catch (e) {
    $('progress-message').textContent = 'Connection lost. Waiting for the local engine…';
    pollTimer = setTimeout(pollJob, 2500);
  }
}

$('cancel-button').addEventListener('click', async () => {
  cancelled = true;
  $('cancel-button').disabled = true;
  if (uploadRequest) uploadRequest.abort();
  try { if (activeId) await api(`/api/jobs/${activeId}/cancel`); } catch (e) { error(e.message); }
  finishBusy();
});

function sourceUrl(kind = previewMode, download = false) {
  return `/api/jobs/${selectedJob.id}/files/${kind}${download ? '?download=1' : ''}`;
}

function view(mode) {
  if (!selectedJob) return;
  previewMode = mode;
  const video = $('result-video');
  video.pause();
  video.src = sourceUrl(mode);
  video.load();
  video.hidden = false;
  $('view-result').classList.toggle('active', mode === 'video');
  $('view-comparison').classList.toggle('active', mode === 'comparison');
  $('save-button').querySelector('span').textContent = mode === 'video' ? 'Save video' : 'Save comparison';
  $('result-format').textContent = mode === 'video' ? 'H.264 MP4 · Silent' : 'Side-by-side comparison';
}

function showResult(job) {
  selectedJob = job;
  localStorage.setItem('mesh-last-result', job.id);
  $('empty-result').hidden = true;
  $('rendering-overlay').hidden = true;
  $('output-state').textContent = 'READY';
  $('output-state').classList.add('complete');
  $('view-result').disabled = false;
  $('view-comparison').disabled = false;
  $('save-button').disabled = false;
  const r = job.result;
  $('result-detail').textContent = `${r.width} × ${r.height} · ${r.duration.toFixed(1)}s · ${sizeLabel(r.bytes)}`;
  $('save-hint').textContent = window.showSaveFilePicker ? 'Save directly to a folder of your choice.' : 'Your browser will download the file. Enable “Ask where to save” to choose a folder.';
  $('result-notes').replaceChildren();
  (r.notes || []).forEach((note) => { const p = document.createElement('p'); p.textContent = note; $('result-notes').append(p); });
  $('result-notes').hidden = !(r.notes || []).length;
  view('video');
  renderHistory(lastJobs);
}

$('view-result').addEventListener('click', () => view('video'));
$('view-comparison').addEventListener('click', () => view('comparison'));
$('save-button').addEventListener('click', async () => {
  if (!selectedJob || saving) return;
  const url = sourceUrl(previewMode, true);
  const base = selectedJob.names.original.replace(/\.[^.]+$/, '').replace(/[<>:"/\\|?*\x00-\x1F]/g, '_');
  const name = `${base}_${previewMode === 'video' ? 'depth_wireframe' : 'comparison'}.mp4`;
  if (!window.showSaveFilePicker) {
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = name; document.body.append(anchor); anchor.click(); anchor.remove();
    $('save-hint').textContent = 'Download started. Check your browser’s downloads.';
    return;
  }
  let writable;
  saving = true;
  $('save-button').disabled = true;
  try {
    // Request the location while this click still has browser user activation.
    const handle = await window.showSaveFilePicker({ suggestedName: name, types: [{ description: 'MP4 video', accept: { 'video/mp4': ['.mp4'] } }] });
    const response = await fetch(url);
    if (!response.ok || !response.body) throw new Error('The result could not be downloaded. Please try again.');
    writable = await handle.createWritable();
    await response.body.pipeTo(writable);
    writable = null;
    $('save-hint').textContent = `Saved as ${handle.name}`;
  } catch (e) {
    if (writable) { try { await writable.abort(); } catch (_) { /* picker/stream already closed */ } }
    if (e.name !== 'AbortError') error(e.message, 'Could not save the video');
  } finally {
    saving = false;
    $('save-button').disabled = !selectedJob;
  }
});

function renderHistory(jobs) {
  const list = $('history-list');
  list.replaceChildren();
  const visible = jobs.filter((job) => job.status !== 'uploading').slice(0, 6);
  if (!visible.length) { const p = document.createElement('p'); p.className = 'history-empty'; p.textContent = 'Your finished videos will be kept here, so you can come back to them.'; list.append(p); return; }
  visible.forEach((job) => {
    const row = document.createElement('button');
    row.className = `history-row${selectedJob?.id === job.id ? ' current' : ''}`;
    row.disabled = busy;
    const image = document.createElement('span'); image.className = 'history-icon'; image.append(icon('video'));
    const name = document.createElement('span'); name.className = 'history-name';
    const title = document.createElement('strong'); title.textContent = job.names.original;
    const date = document.createElement('span'); date.textContent = `${new Date(job.created_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}${job.result ? ` · ${job.result.width} × ${job.result.height} · ${job.result.duration.toFixed(1)}s` : ''}`;
    name.append(title, date);
    const status = document.createElement('span'); status.className = `history-status ${job.status}`; status.textContent = { complete: 'Ready to save', failed: 'Could not finish', cancelled: 'Cancelled', queued: 'Queued', running: 'Processing' }[job.status] || job.status;
    const arrow = icon('arrow'); arrow.classList.add('history-arrow');
    row.append(image, name, status, arrow);
    row.addEventListener('click', () => {
      $('error-banner').hidden = true;
      if (job.status === 'complete') { showResult(job); $('output-heading').scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
      else if (['running', 'queued'].includes(job.status)) { cancelled = false; activeId = job.id; setBusy(true); resetResult(); pollJob(); }
      else error(job.message, job.status === 'cancelled' ? 'This run was cancelled' : 'This run could not finish');
    });
    list.append(row);
  });
}

async function refreshHistory() {
  try { const response = await fetch('/api/jobs', { cache: 'no-store' }); if (!response.ok) return; lastJobs = await response.json(); renderHistory(lastJobs); } catch (_) { /* restored at the next refresh */ }
}

$('help-button').addEventListener('click', () => $('help-dialog').showModal());
$('close-help').addEventListener('click', () => $('help-dialog').close());
$('help-dialog').addEventListener('click', (event) => { if (event.target === $('help-dialog')) { const r = event.target.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) event.target.close(); } });
$('result-video').addEventListener('error', () => { if (selectedJob) error('The browser could not preview this video. You can still save the MP4 using Save video.', 'Preview unavailable'); });

async function connect() {
  try {
    const response = await fetch('/api/config', { cache: 'no-store' });
    if (!response.ok) throw new Error('Cannot connect to the local engine.');
    config = await response.json();
    $('engine-status').className = `engine-status ${config.ready ? 'ready' : 'offline'}`;
    $('engine-status').lastElementChild.textContent = config.message;
    if (!config.ready) error(config.message, 'The local engine needs attention');
    await refreshHistory();
    const remembered = localStorage.getItem('mesh-active-job');
    const active = lastJobs.find((job) => job.id === remembered && ['running', 'queued'].includes(job.status)) || lastJobs.find((job) => ['running', 'queued'].includes(job.status));
    if (active) { activeId = active.id; setBusy(true); resetResult(); pollJob(); }
    else {
      if (remembered) {
        const interrupted = lastJobs.find((job) => job.id === remembered);
        if (interrupted?.status === 'uploading') { await api(`/api/jobs/${remembered}/cancel`); error('The upload was interrupted. Select your two videos and start again.'); await refreshHistory(); }
        localStorage.removeItem('mesh-active-job');
      }
      const last = lastJobs.find((job) => job.id === localStorage.getItem('mesh-last-result') && job.status === 'complete') || lastJobs.find((job) => job.status === 'complete');
      if (last) showResult(last);
    }
    updateButton();
  } catch (e) {
    $('engine-status').className = 'engine-status offline';
    $('engine-status').lastElementChild.textContent = 'Engine disconnected';
    error('Start Mesh Studio with Start-Mesh-Studio.ps1, then refresh this page.', 'The local engine is offline');
    setTimeout(connect, 4000);
  }
}

window.addEventListener('beforeunload', (event) => { if (uploadRequest) { event.preventDefault(); event.returnValue = ''; } });
connect();
