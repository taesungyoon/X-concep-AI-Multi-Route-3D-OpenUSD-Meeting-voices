import { initViewer, loadModel, setView, toggleFullscreen } from './viewer.js';

const state = { project: null, selected2d: null, files: [], inputMode: 'prompt', meeting: { recorder: null, stream: null, chunks: 0, timer: null, seconds: 0, analyserFrame: null } };
const qs = (selector) => document.querySelector(selector);
const qsa = (selector) => [...document.querySelectorAll(selector)];
const goalLabels = { auto: '자동 추천', fast: '빠른 3D', structural: '구조 중심 3D', high_quality: '고품질 3D', motion_openusd: '동작·OpenUSD' };
const routeLabels = { fast: '빠른 3D', structural: '구조 중심 3D', high_quality: '고품질 3D' };
function selectedOutputGoal() { return qs('input[name="output_goal"]:checked')?.value || 'auto'; }
function selectedQualityProfile() { return qs('#qualityProfile')?.value || 'standard'; }
function selectedEngineOverride() { return qs('#engineOverride')?.value || ''; }
const stages = { 1: qs('#stageInput'), 2: qs('#stageCompare'), 3: qs('#stageResult') };

const form = qs('#generateForm');
const promptInput = qs('#promptInput');
const imageInput = qs('#imageInput');
const dropzone = qs('#dropzone');
const uploadPreview = qs('#uploadPreview');
const compareGrid = qs('#compareGrid');
const generate3dButton = qs('#generate3dButton');
const historyDrawer = qs('#historyDrawer');
const loadingOverlay = qs('#loadingOverlay');
const progressRing = qs('.progress-ring');
const promptModePanel = qs('#promptModePanel');
const meetingModePanel = qs('#meetingModePanel');
const meetingLiveBadge = qs('#meetingLiveBadge');
const transcriptStream = qs('#transcriptStream');
const manualTranscript = qs('#manualTranscript');
const analyzeMeetingButton = qs('#analyzeMeetingButton');
const generateMeeting2dButton = qs('#generateMeeting2dButton');
let loadingTimer;

function setStage(step) {
  Object.entries(stages).forEach(([key, el]) => el.classList.toggle('active', Number(key) === step));
  qsa('.step').forEach((el, index) => {
    const n = index + 1;
    el.classList.toggle('active', n === step);
    el.classList.toggle('done', n < step);
  });
  qs('#heroCopy').style.display = step === 1 ? '' : 'none';
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function showToast(message) {
  const toast = qs('#toast');
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => toast.classList.remove('show'), 2600);
}

function startLoading(type) {
  const configs = type === 'meeting'
    ? { title: '회의 요구사항을 분석하고 있음', messages: ['음성 전사 내용을 정리하고 있음', 'Gemma가 결정사항과 변경사항을 분리하고 있음', 'OpenUSD 메타데이터를 준비하고 있음'], labels: ['전사 정리', '요구사항 분석', 'USD 준비'] }
    : type === '3d'
    ? { title: '3D 설계를 생성하고 있음', messages: ['선택한 2D 형상을 분석하고 있음', '3D 구조와 메시를 생성하고 있음', 'GLB·STL 파일을 내보내고 있음'], labels: ['2D 분석', '3D 생성', '파일 출력'] }
    : { title: '2D 컨셉을 생성하고 있음', messages: ['프롬프트와 이미지를 분석하고 있음', '서로 다른 설계 방향을 생성하고 있음', '비교할 결과를 정리하고 있음'], labels: ['요구사항 분석', '2D 생성', '결과 정리'] };
  qs('#loadingTitle').textContent = configs.title;
  qsa('.loading-steps span').forEach((el, i) => el.textContent = configs.labels[i]);
  loadingOverlay.classList.add('open');
  loadingOverlay.setAttribute('aria-hidden', 'false');
  let progress = 8;
  let index = 0;
  updateLoading(progress, configs.messages[0], index);
  clearInterval(loadingTimer);
  loadingTimer = setInterval(() => {
    progress = Math.min(92, progress + Math.ceil(Math.random() * 8));
    index = progress > 68 ? 2 : progress > 34 ? 1 : 0;
    updateLoading(progress, configs.messages[index], index);
  }, 460);
}

function updateLoading(progress, message, activeIndex) {
  qs('#loadingPercent').textContent = `${progress}%`;
  progressRing.style.setProperty('--progress', `${progress}%`);
  qs('#loadingMessage').textContent = message;
  qsa('.loading-steps span').forEach((el, i) => el.classList.toggle('active', i <= activeIndex));
}

function stopLoading() {
  clearInterval(loadingTimer);
  updateLoading(100, '완료됨', 2);
  setTimeout(() => {
    loadingOverlay.classList.remove('open');
    loadingOverlay.setAttribute('aria-hidden', 'true');
  }, 320);
}

function renderFilePreviews() {
  uploadPreview.innerHTML = '';
  state.files.forEach((file, index) => {
    const item = document.createElement('div');
    item.className = 'preview-item';
    const img = document.createElement('img');
    img.src = URL.createObjectURL(file);
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.textContent = '×';
    remove.addEventListener('click', () => {
      state.files.splice(index, 1);
      syncInputFiles();
      renderFilePreviews();
    });
    item.append(img, remove);
    uploadPreview.appendChild(item);
  });
}

function syncInputFiles() {
  const transfer = new DataTransfer();
  state.files.forEach(file => transfer.items.add(file));
  imageInput.files = transfer.files;
}

function addFiles(files) {
  const accepted = [...files].filter(file => ['image/jpeg', 'image/png', 'image/webp'].includes(file.type));
  state.files = [...state.files, ...accepted].slice(0, 4);
  syncInputFiles();
  renderFilePreviews();
  if (accepted.length !== files.length) showToast('JPG, PNG, WEBP 이미지만 사용할 수 있음');
}

imageInput.addEventListener('change', () => { state.files = []; addFiles(imageInput.files); });
['dragenter', 'dragover'].forEach(name => dropzone.addEventListener(name, e => { e.preventDefault(); dropzone.classList.add('dragging'); }));
['dragleave', 'drop'].forEach(name => dropzone.addEventListener(name, e => { e.preventDefault(); dropzone.classList.remove('dragging'); }));
dropzone.addEventListener('drop', e => addFiles(e.dataTransfer.files));
promptInput.addEventListener('input', () => qs('#charCount').textContent = `${promptInput.value.length} / 1600`);
qs('.example-btn').addEventListener('click', e => { promptInput.value = e.currentTarget.dataset.example; promptInput.dispatchEvent(new Event('input')); promptInput.focus(); });
qsa('.type-card').forEach(card => card.addEventListener('click', () => { qsa('.type-card').forEach(c => c.classList.remove('selected')); card.classList.add('selected'); }));
qsa('.goal-card').forEach(card => card.addEventListener('click', () => { qsa('.goal-card').forEach(c => c.classList.remove('selected')); card.classList.add('selected'); }));


function setInputMode(mode) {
  state.inputMode = mode;
  promptModePanel.hidden = mode !== 'prompt';
  meetingModePanel.hidden = mode !== 'meeting';
  qsa('[data-input-mode]').forEach(btn => btn.classList.toggle('active', btn.dataset.inputMode === mode));
  qs('#heroCopy h1').innerHTML = mode === 'meeting'
    ? '회의 내용을 들으며<br><em>중간 설계를 계속 생성함</em>'
    : '설명하고 이미지를 넣으면<br><em>2D 비교부터 3D까지</em> 생성함';
}
qsa('[data-input-mode]').forEach(btn => btn.addEventListener('click', () => setInputMode(btn.dataset.inputMode)));

async function ensureMeetingProject() {
  if (state.project?.meeting) return state.project;
  const response = await fetch('/api/meetings', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category: qs('#meetingCategory').value, output_goal: qs('#meetingOutputGoal').value, quality_profile: 'standard' })
  });
  const json = await response.json();
  if (!response.ok) throw new Error(json.error || '회의 프로젝트 생성 실패');
  state.project = json.project;
  return state.project;
}

function formatTime(seconds) {
  const m = String(Math.floor(seconds / 60)).padStart(2, '0');
  const s = String(seconds % 60).padStart(2, '0');
  return `${m}:${s}`;
}

function updateMeetingBadge(text, live = false) {
  meetingLiveBadge.textContent = text;
  meetingLiveBadge.classList.toggle('recording', live);
}

async function startMeeting() {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    showToast('이 브라우저는 회의 녹음을 지원하지 않음. 직접 입력을 사용해야 함');
    return;
  }
  try {
    await ensureMeetingProject();
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg'].find(type => MediaRecorder.isTypeSupported(type));
    const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    state.meeting.stream = stream;
    state.meeting.recorder = recorder;
    state.meeting.seconds = 0;
    state.meeting.chunks = Number(state.project.meeting?.chunk_count || 0);
    recorder.addEventListener('dataavailable', event => {
      if (event.data && event.data.size > 500) uploadMeetingChunk(event.data).catch(error => showToast(error.message));
    });
    recorder.addEventListener('stop', () => updateMeetingBadge('분석 가능', false));
    recorder.start(15000);
    qs('#startMeetingButton').disabled = true;
    qs('#stopMeetingButton').disabled = false;
    updateMeetingBadge('● 녹음 중', true);
    state.meeting.timer = setInterval(() => {
      state.meeting.seconds += 1;
      qs('#recordTime').textContent = formatTime(state.meeting.seconds);
    }, 1000);
    startAudioMeter(stream);
  } catch (error) {
    showToast(error.message || '마이크를 시작할 수 없음');
  }
}

function stopMeeting() {
  const recorder = state.meeting.recorder;
  if (recorder && recorder.state !== 'inactive') recorder.stop();
  state.meeting.stream?.getTracks().forEach(track => track.stop());
  state.meeting.stream = null;
  clearInterval(state.meeting.timer);
  cancelAnimationFrame(state.meeting.analyserFrame);
  qs('#audioLevelBar').style.width = '0%';
  qs('#startMeetingButton').disabled = false;
  qs('#stopMeetingButton').disabled = true;
  updateMeetingBadge('전사 정리 중', false);
}

function startAudioMeter(stream) {
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  if (!AudioContext) return;
  const context = new AudioContext();
  const source = context.createMediaStreamSource(stream);
  const analyser = context.createAnalyser();
  analyser.fftSize = 256;
  source.connect(analyser);
  const data = new Uint8Array(analyser.frequencyBinCount);
  const tick = () => {
    analyser.getByteFrequencyData(data);
    const avg = data.reduce((a, b) => a + b, 0) / data.length;
    qs('#audioLevelBar').style.width = `${Math.min(100, avg * 1.5)}%`;
    state.meeting.analyserFrame = requestAnimationFrame(tick);
  };
  tick();
}

async function uploadMeetingChunk(blob) {
  if (!state.project) return;
  const index = state.meeting.chunks++;
  const data = new FormData();
  data.append('chunk_index', String(index));
  data.append('audio', blob, `meeting-${index}.webm`);
  qs('#transcriptProvider').textContent = '음성 전사 중';
  const response = await fetch(`/api/projects/${state.project.id}/meeting/chunks`, { method: 'POST', body: data });
  const json = await response.json();
  if (!response.ok) throw new Error(json.error || '음성 전사 실패');
  state.project = json.project;
  qs('#transcriptProvider').textContent = json.chunk?.provider || '로컬 STT';
  renderTranscript();
}

function renderTranscript() {
  const meeting = state.project?.meeting;
  const segments = meeting?.segments || [];
  if (!segments.length) {
    transcriptStream.innerHTML = '<div class="empty-transcript">회의를 시작하거나 내용을 직접 입력함</div>';
    return;
  }
  transcriptStream.innerHTML = segments.map(segment => `
    <article class="transcript-line"><b>${escapeHtml(segment.speaker || '화자')}</b><p>${escapeHtml(segment.text || '')}</p><small>${Number(segment.start || 0).toFixed(0)}s</small></article>
  `).join('');
  transcriptStream.scrollTop = transcriptStream.scrollHeight;
  if (!manualTranscript.value.trim()) manualTranscript.value = meeting.transcript || '';
}

async function analyzeMeeting() {
  try {
    await ensureMeetingProject();
    const transcript = manualTranscript.value.trim() || state.project.meeting?.transcript || '';
    if (transcript.length < 2) return showToast('분석할 회의 내용을 입력해야 함');
    startLoading('meeting');
    const response = await fetch(`/api/projects/${state.project.id}/meeting/analyze`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ transcript })
    });
    const json = await response.json();
    if (!response.ok) throw new Error(json.error || '회의 분석 실패');
    state.project = json.project;
    renderMeetingAnalysis();
    generateMeeting2dButton.disabled = false;
    updateMeetingBadge('분석 완료', false);
  } catch (error) {
    showToast(error.message);
  } finally { stopLoading(); }
}

function renderMeetingAnalysis() {
  const analysis = state.project?.meeting?.analysis;
  const root = qs('#meetingAnalysisCards');
  if (!analysis) return;
  const list = (value) => (value || []).map(item => `<li>${escapeHtml(typeof item === 'string' ? item : JSON.stringify(item))}</li>`).join('') || '<li>없음</li>';
  const dims = analysis.dimensions || {};
  root.innerHTML = `
    <div class="analysis-card"><span>확정 요구사항</span><ul>${list(analysis.confirmed_requirements)}</ul></div>
    <div class="analysis-card"><span>주요 치수</span><p>W ${dims.width_mm ?? '-'} · D ${dims.depth_mm ?? '-'} · H ${dims.height_mm ?? '-'} mm</p></div>
    <div class="analysis-card"><span>안전·미확정</span><ul>${list([...(analysis.safety_requirements || []), ...(analysis.unresolved_items || [])])}</ul></div>
    <div class="analysis-card wide"><span>생성 프롬프트</span><p>${escapeHtml(analysis.generation_prompt || '')}</p></div>`;
}

async function generateMeeting2d() {
  if (!state.project) return;
  startLoading('2d');
  try {
    const response = await fetch(`/api/projects/${state.project.id}/meeting/generate-2d`, { method: 'POST' });
    const json = await response.json();
    if (!response.ok) throw new Error(json.error || '회의 기반 2D 생성 실패');
    state.project = json.project;
    renderCompare();
    setStage(2);
  } catch (error) { showToast(error.message); }
  finally { stopLoading(); }
}

qs('#startMeetingButton').addEventListener('click', startMeeting);
qs('#stopMeetingButton').addEventListener('click', stopMeeting);
analyzeMeetingButton.addEventListener('click', analyzeMeeting);
generateMeeting2dButton.addEventListener('click', generateMeeting2d);

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const prompt = promptInput.value.trim();
  if (prompt.length < 8) return showToast('프롬프트를 8자 이상 입력해야 함');
  const data = new FormData(form);
  data.delete('images[]');
  state.files.forEach(file => data.append('images[]', file));
  startLoading('2d');
  try {
    const response = await fetch('/api/projects', { method: 'POST', body: data });
    const json = await response.json();
    if (!response.ok) throw new Error(json.error || '2D 생성 실패');
    state.project = json.project;
    renderCompare();
    setStage(2);
  } catch (error) {
    showToast(error.message);
  } finally {
    stopLoading();
  }
});

function renderCompare() {
  compareGrid.innerHTML = '';
  state.selected2d = null;
  generate3dButton.disabled = true;
  qs('#selectionGuide').textContent = '한 가지 안을 선택해야 함';
  (state.project.results_2d || []).forEach((item, index) => {
    const card = document.createElement('article');
    card.className = 'concept-card';
    card.dataset.id = item.id;
    const conceptUrl = safeAssetUrl(item.url);
    card.innerHTML = `<span class="concept-badge">OPTION ${String.fromCharCode(65 + index)}</span><img src="${escapeHtml(conceptUrl)}" alt="2D 컨셉 ${index + 1}"><div class="concept-info"><div><strong>${escapeHtml(item.title || '')}</strong><small>${escapeHtml(item.description || '')}</small></div><span class="select-indicator">✓</span></div>`;
    card.addEventListener('click', () => selectConcept(item, card));
    compareGrid.appendChild(card);
  });
}

function selectConcept(item, card) {
  state.selected2d = item;
  qsa('.concept-card').forEach(el => el.classList.remove('selected'));
  card.classList.add('selected');
  generate3dButton.disabled = false;
  qs('#selectionGuide').textContent = `${item.title}을 선택함`;
}

generate3dButton.addEventListener('click', async () => {
  if (!state.project || !state.selected2d) return;
  startLoading('3d');
  try {
    const response = await fetch(`/api/projects/${state.project.id}/generate-3d`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
        selected_2d_id: state.selected2d.id,
        output_goal: state.project.output_goal || selectedOutputGoal(),
        quality_profile: state.project.quality_profile || selectedQualityProfile(),
        engine_override: selectedEngineOverride() || null
      })
    });
    const json = await response.json();
    if (!response.ok) throw new Error(json.error || '3D 생성 실패');
    state.project = json.project;
    await renderResult();
    setStage(3);
  } catch (error) {
    showToast(error.message);
  } finally {
    stopLoading();
  }
});

async function renderResult() {
  const result = state.project.result_3d || {};
  const selected = (state.project.results_2d || []).find(item => item.id === state.project.selected_2d_id) || state.selected2d;
  qs('#selectedReference').src = safeAssetUrl(selected?.url || result.preview_url);
  qs('#resultPrompt').textContent = state.project.prompt;
  renderRouteTabs(result);
  renderValidation(result.validation || state.project.validation_report || {});
  renderOpenUsdDownloads(result);
  qs('#openOmniverseButton').dataset.streamUrl = result.omniverse?.stream_url || '';
  await activateResultAsset(result.active_asset || result.route_key || Object.keys(result.assets || {})[0], result);
}

function renderRouteTabs(result) {
  const root = qs('#routeTabs');
  root.innerHTML = '';
  const assets = result.assets || {};
  Object.entries(assets).forEach(([key, asset]) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `route-tab ${key === result.active_asset ? 'active' : ''}`;
    button.dataset.routeKey = key;
    button.innerHTML = `<span>${escapeHtml(routeLabels[key] || asset.title || key)}</span><small>${escapeHtml((asset.tags || []).slice(0, 2).join(' · '))}</small>`;
    button.addEventListener('click', () => activateResultAsset(key, result));
    root.appendChild(button);
  });
  if (!Object.keys(assets).length) {
    root.innerHTML = '<span class="empty-state">생성 자산 정보가 없음</span>';
  }
}

async function activateResultAsset(key, result = state.project.result_3d || {}) {
  const asset = (result.assets || {})[key] || result;
  qsa('.route-tab').forEach(btn => btn.classList.toggle('active', btn.dataset.routeKey === key));
  qs('#resultTitle').textContent = asset.title || result.title || '3D 설계 결과';
  qs('#resultTags').innerHTML = (asset.tags || result.tags || []).map(tag => `<span>${escapeHtml(String(tag))}</span>`).join('');
  setDownload('#downloadGlb', asset.glb_url || result.glb_url);
  setDownload('#downloadStl', asset.stl_url || result.stl_url);
  setDownload('#downloadRender', asset.preview_url || result.preview_url);
  setDownload('#downloadScad', asset.scad_url);
  setDownload('#downloadGeometryJson', asset.geometry_json_url);
  setDownload('#downloadBlenderScript', asset.blender_script_url);
  const viewer = qs('#viewer3d');
  initViewer(viewer);
  const glbUrl = safeAssetUrl(asset.glb_url || result.glb_url);
  if (glbUrl) {
    try { await loadModel(glbUrl); } catch (e) { showToast('3D 모델 뷰어 로딩에 실패함'); }
  }
}

function setDownload(selector, value) {
  const element = qs(selector);
  const url = safeAssetUrl(value || '');
  if (url) { element.href = url; element.hidden = false; }
  else { element.hidden = true; element.removeAttribute('href'); }
}

function renderOpenUsdDownloads(result) {
  const openusd = result.openusd || {};
  setDownload('#downloadUsda', result.usda_url || openusd.usda_url);
  setDownload('#downloadUsdc', result.usdc_url || openusd.usdc_url);
  setDownload('#downloadUsdRoot', result.openusd_root_url || openusd.root_url);
  setDownload('#downloadUsdManifest', result.openusd_manifest_url || openusd.manifest_url);
}

function renderValidation(validation) {
  const grade = validation.grade_label || state.project.validation_grade || '컨셉 검토 가능';
  const score = Math.max(0, Math.min(1, Number(validation.score || 0)));
  qs('#validationGrade').textContent = grade;
  qs('#validationScoreBar').style.width = `${Math.round(score * 100)}%`;
  qs('#validationScope').textContent = (validation.usage_scope || ['생성 결과 검토']).join(' · ');
  const details = qs('#validationDetails');
  details.innerHTML = (validation.checks || []).map(check => `<div class="validation-check ${check.passed ? 'pass' : 'fail'}"><span>${escapeHtml(check.label || check.id)}</span><b>${check.passed ? 'PASS' : 'CHECK'}</b></div>`).join('') +
    `<p>${escapeHtml(validation.manufacturing_note || '')}</p>`;
}

async function regenerateWithGoal(goal) {
  if (!state.project || !state.project.selected_2d_id) return;
  startLoading('3d');
  try {
    const response = await fetch(`/api/projects/${state.project.id}/generate-3d`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
        selected_2d_id: state.project.selected_2d_id,
        output_goal: goal,
        quality_profile: goal === 'high_quality' || goal === 'motion_openusd' ? 'final' : 'standard'
      })
    });
    const json = await response.json();
    if (!response.ok) throw new Error(json.error || '재생성 실패');
    state.project = json.project;
    await renderResult();
    showToast(`${goalLabels[goal] || goal} 결과를 추가함`);
  } catch (error) { showToast(error.message); }
  finally { stopLoading(); }
}

qs('#validationDetailsButton').addEventListener('click', () => {
  const details = qs('#validationDetails');
  details.hidden = !details.hidden;
  qs('#validationDetailsButton').textContent = details.hidden ? '검증 상세 보기' : '검증 상세 닫기';
});
qsa('[data-regenerate-goal]').forEach(button => button.addEventListener('click', () => regenerateWithGoal(button.dataset.regenerateGoal)));
qs('#editPromptButton').addEventListener('click', () => setStage(1));
qs('#newProjectButton').addEventListener('click', () => {
  stopMeeting(); state.project = null; state.selected2d = null; state.files = []; state.meeting.chunks = 0; manualTranscript.value = ''; transcriptStream.innerHTML = '<div class="empty-transcript">회의를 시작하거나 내용을 직접 입력함</div>'; generateMeeting2dButton.disabled = true;
  form.reset(); uploadPreview.innerHTML = ''; compareGrid.innerHTML = ''; promptInput.dispatchEvent(new Event('input'));
  qsa('.type-card').forEach((c, i) => c.classList.toggle('selected', i === 0)); qsa('.goal-card').forEach((c, i) => c.classList.toggle('selected', i === 0));
  setStage(1);
});
qsa('[data-view]').forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));
qs('#fullscreenButton').addEventListener('click', toggleFullscreen);
qs('#openOmniverseButton').addEventListener('click', event => {
  const url = event.currentTarget.dataset.streamUrl;
  if (url) window.open(url, '_blank', 'noopener');
  else showToast('OMNIVERSE_STREAM_URL을 설정하면 RTX Kit WebRTC 뷰어가 열림');
});

async function openHistory() {
  historyDrawer.classList.add('open');
  historyDrawer.setAttribute('aria-hidden', 'false');
  const list = qs('#historyList');
  list.innerHTML = '<div class="empty-state">작업 이력을 불러오고 있음</div>';
  try {
    const response = await fetch('/api/projects');
    const json = await response.json();
    if (!json.items?.length) { list.innerHTML = '<div class="empty-state">아직 생성한 작업이 없음</div>'; return; }
    list.innerHTML = '';
    json.items.forEach(item => {
      const row = document.createElement('article');
      row.className = 'history-item';
      const thumbnail = item.thumbnail ? safeAssetUrl(item.thumbnail) : '';
      row.innerHTML = `${thumbnail ? `<img src="${escapeHtml(thumbnail)}" alt="">` : '<div></div>'}<div><h3>${escapeHtml(item.prompt.slice(0, 46))}</h3><p>${labelCategory(item.category)} · ${labelStatus(item.status)}<br>${new Date(item.updated_at).toLocaleString('ko-KR')}</p></div>`;
      row.addEventListener('click', () => loadProject(item.id));
      list.appendChild(row);
    });
  } catch { list.innerHTML = '<div class="empty-state">작업 이력을 불러오지 못함</div>'; }
}

async function loadProject(id) {
  try {
    const response = await fetch(`/api/projects/${id}`);
    const json = await response.json();
    if (!response.ok) throw new Error(json.error);
    state.project = json.project;
    closeHistory();
    if (state.project.status === 'completed' && state.project.result_3d) { await renderResult(); setStage(3); }
    else { renderCompare(); setStage(2); }
  } catch (error) { showToast(error.message || '프로젝트를 열 수 없음'); }
}

function closeHistory() { historyDrawer.classList.remove('open'); historyDrawer.setAttribute('aria-hidden', 'true'); }
qs('#historyButton').addEventListener('click', openHistory);
qsa('[data-close-history]').forEach(el => el.addEventListener('click', closeHistory));
function labelCategory(value) { return ({ equipment: '설비', module: '모듈', part: '부품' })[value] || value; }
function labelStatus(value) { return ({ completed: '3D 완료', '2d_ready': '2D 완료', generating_3d: '3D 생성 중' })[value] || value; }
function escapeHtml(value) { const div = document.createElement('div'); div.textContent = String(value ?? ''); return div.innerHTML; }
function safeAssetUrl(value) {
  const url = String(value || '').trim();
  if (url === '#') return '#';
  if (/^\/storage\/projects\/[A-Za-z0-9-]+\/(results-2d|result)\/[A-Za-z0-9_./-]+$/.test(url)) return url;
  return '';
}

setStage(1);
setInputMode('prompt');


async function loadSystemStatus() {
  const strip = qs('#systemStrip');
  if (!strip) return;
  try {
    const response = await fetch('/api/system-status');
    const json = await response.json();
    const worker = json.worker || {};
    const values = [
      { label: `GPT Image · ${worker.image?.model || 'configured'}`, active: worker.image?.mode !== 'mock' },
      { label: `${worker.llm?.model || 'Gemma local'} · vLLM/Ray`, active: worker.llm?.mode !== 'mock' },
      { label: 'Hunyuan3D Local', active: worker.hunyuan3d?.mode !== 'mock' },
      { label: 'OpenSCAD Structure', active: Boolean(worker.openscad?.binary) || worker.openscad?.mode === 'mock' },
      { label: 'Blender Asset Bridge', active: Boolean(worker.blender?.binary) || worker.blender?.mode === 'mock' },
      { label: `Speech · ${worker.speech?.model || 'local'}`, active: worker.speech?.mode !== 'mock' },
      { label: 'OpenUSD Layers', active: worker.openusd?.enabled === true },
      { label: 'Omniverse Kit · PhysX', active: worker.omniverse?.enabled === true },
      { label: 'Nucleus · WebRTC', active: worker.omniverse?.webrtc === true },
    ];
    strip.innerHTML = values.map(item => `<span class="${item.active ? 'active' : 'mock'}"><i></i>${item.label}</span>`).join('');
  } catch {
    strip.classList.add('offline');
  }
}
loadSystemStatus();
