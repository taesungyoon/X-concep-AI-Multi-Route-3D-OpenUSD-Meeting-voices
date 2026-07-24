"use strict";

const state = {
  jobs: [],
  training: [],
  apiKey: sessionStorage.getItem("cadAiApiKey") || "",
  pollTimer: null,
};

const byId = (id) => document.getElementById(id);

function apiHeaders(extra = {}) {
  const headers = { ...extra };
  if (state.apiKey) headers["X-API-Key"] = state.apiKey;
  return headers;
}

async function api(path, options = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(path, {
      ...options,
      headers: apiHeaders(options.headers || {}),
      signal: controller.signal,
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error?.message || `HTTP ${response.status}`);
    }
    return payload.data;
  } finally {
    clearTimeout(timeout);
  }
}

function formatDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ko-KR", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  }).format(new Date(value));
}

function textElement(tag, text, className = "") {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) element.className = className;
  return element;
}

function setMessage(element, text, error = false) {
  element.textContent = text;
  element.classList.toggle("error", error);
}

async function refreshHealth() {
  try {
    const health = await api("/api/health");
    byId("health-label").textContent = "서비스 정상";
    byId("health-detail").textContent = `queue ${health.queue_depth} · v${health.version}`;
  } catch (error) {
    byId("health-label").textContent = "연결 필요";
    byId("health-detail").textContent = error.message;
  }
}

function renderMetrics() {
  const completed = state.jobs.filter((job) => ["completed", "partial"].includes(job.status));
  const scores = completed.map((job) => job.quality_score).filter((value) => typeof value === "number");
  byId("metric-total").textContent = String(state.jobs.length);
  byId("metric-completed").textContent = String(completed.length);
  byId("metric-quality").textContent = scores.length
    ? (scores.reduce((sum, value) => sum + value, 0) / scores.length).toFixed(2)
    : "—";
  byId("metric-training").textContent = String(state.training.length);
}

function addCell(row, content) {
  const cell = document.createElement("td");
  if (content instanceof Node) cell.append(content);
  else cell.textContent = content;
  row.append(cell);
}

function renderJobs() {
  const body = byId("jobs-body");
  body.replaceChildren();
  byId("jobs-empty").hidden = state.jobs.length > 0;
  state.jobs.forEach((job) => {
    const row = document.createElement("tr");
    const sample = document.createElement("div");
    sample.append(textElement("strong", job.original_filename), textElement("small", job.id));
    addCell(row, sample);
    addCell(row, job.source_format.toUpperCase());
    const status = textElement("span", `${job.stage} · ${job.progress}%`, `status-pill ${job.status}`);
    addCell(row, status);
    addCell(row, typeof job.quality_score === "number" ? job.quality_score.toFixed(2) : "—");
    row.children[3].className = "quality";
    addCell(row, job.split || "—");
    addCell(row, formatDate(job.created_at));
    const button = textElement("button", "상세", "row-button");
    button.type = "button";
    button.addEventListener("click", () => openJob(job.id));
    addCell(row, button);
    body.append(row);
  });
  renderMetrics();
}

async function refreshJobs() {
  try {
    const data = await api("/api/jobs?limit=100");
    state.jobs = data.items;
    renderJobs();
  } catch (error) {
    setMessage(byId("upload-message"), error.message, true);
  }
}

function renderTraining() {
  const list = byId("training-list");
  list.replaceChildren();
  byId("training-count").textContent = `${state.training.length} runs`;
  if (!state.training.length) {
    list.append(textElement("p", "라벨이 있는 샘플을 준비한 뒤 기준 모델을 학습하세요.", "empty-state"));
  }
  state.training.slice(0, 6).forEach((run) => {
    const item = document.createElement("div");
    item.className = "training-item";
    item.append(
      textElement("strong", run.id),
      textElement("span", run.status, `status-pill ${run.status}`),
      textElement("small", `${run.sample_count} samples · ${run.class_count} classes`),
      textElement(
        "small",
        run.metrics.training_accuracy === undefined
          ? (run.error_message || formatDate(run.created_at))
          : `training accuracy ${(run.metrics.training_accuracy * 100).toFixed(1)}%`,
      ),
    );
    list.append(item);
  });
  renderMetrics();
}

async function refreshTraining() {
  try {
    const data = await api("/api/training/runs");
    state.training = data.items;
    renderTraining();
  } catch (error) {
    setMessage(byId("training-message"), error.message, true);
  }
}

function detailBlock(label, value) {
  const block = document.createElement("div");
  block.className = "detail-block";
  block.append(textElement("span", label), textElement("strong", value));
  return block;
}

async function openJob(jobId) {
  try {
    const job = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
    byId("detail-title").textContent = job.original_filename;
    const content = byId("detail-content");
    content.replaceChildren();
    const grid = document.createElement("div");
    grid.className = "detail-grid";
    grid.append(
      detailBlock("Sample ID", job.id),
      detailBlock("Status", `${job.status} / ${job.stage}`),
      detailBlock("Format · split", `${job.source_format.toUpperCase()} · ${job.split || "pending"}`),
      detailBlock("Quality", typeof job.quality_score === "number" ? job.quality_score.toFixed(4) : "pending"),
      detailBlock("Category", job.category),
      detailBlock("SHA-256", job.sha256.slice(0, 20) + "…"),
    );
    content.append(grid);
    const progress = document.createElement("div");
    progress.className = "progress";
    const bar = document.createElement("span");
    bar.style.width = `${job.progress}%`;
    progress.append(bar);
    content.append(progress);
    const preview = job.artifacts.find((item) => item.relative_path === "images/preview.svg");
    if (preview) {
      const image = document.createElement("img");
      image.className = "preview-frame";
      image.alt = `${job.original_filename} 전처리 미리보기`;
      image.src = `/api/jobs/${encodeURIComponent(job.id)}/artifact?path=${encodeURIComponent(preview.relative_path)}`;
      if (state.apiKey) {
        const note = textElement("p", "API Key 사용 시 미리보기는 목록 링크에서 내려받아 확인하세요.", "form-message");
        content.append(note);
      } else {
        content.append(image);
      }
    }
    if (job.warnings.length) {
      content.append(textElement("h3", "품질 경고"));
      const warningList = document.createElement("ul");
      job.warnings.forEach((warning) => warningList.append(textElement("li", warning)));
      content.append(warningList);
    }
    content.append(textElement("h3", "산출물"));
    const artifactList = document.createElement("ul");
    artifactList.className = "artifact-list";
    job.artifacts.forEach((artifact) => {
      const li = document.createElement("li");
      const link = document.createElement("a");
      link.textContent = artifact.relative_path;
      link.href = `/api/jobs/${encodeURIComponent(job.id)}/artifact?path=${encodeURIComponent(artifact.relative_path)}`;
      link.target = "_blank";
      link.rel = "noopener";
      li.append(link);
      artifactList.append(li);
    });
    content.append(artifactList);
    if (["completed", "partial"].includes(job.status)) {
      const download = document.createElement("a");
      download.className = "button primary";
      download.href = `/api/jobs/${encodeURIComponent(job.id)}/download`;
      download.textContent = "학습 패키지 ZIP 다운로드";
      content.append(download);
    }
    if (job.status === "failed" || job.status === "partial") {
      const retry = textElement("button", "작업 재시도", "button ghost");
      retry.type = "button";
      retry.addEventListener("click", async () => {
        await api(`/api/jobs/${encodeURIComponent(job.id)}/retry`, { method: "POST" });
        byId("job-dialog").close();
        await refreshJobs();
      });
      content.append(retry);
    }
    byId("job-dialog").showModal();
  } catch (error) {
    setMessage(byId("upload-message"), error.message, true);
  }
}

async function submitUpload(event) {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type=submit]");
  const file = byId("cad-file").files[0];
  if (!file) {
    setMessage(byId("upload-message"), "파일을 선택하세요.", true);
    return;
  }
  const form = new FormData();
  form.append("file", file);
  form.append("category", byId("category").value);
  form.append("project_group", byId("project-group").value);
  form.append("description", byId("description").value);
  button.disabled = true;
  setMessage(byId("upload-message"), "업로드 및 검증 중…");
  try {
    const data = await api("/api/jobs", { method: "POST", body: form }, 60000);
    setMessage(byId("upload-message"), `${data.job_id} 작업이 등록되었습니다.`);
    event.currentTarget.reset();
    byId("category").value = "unlabeled";
    byId("file-summary").textContent = "DXF · STEP · STP / 최대 50 MB";
    await refreshJobs();
  } catch (error) {
    setMessage(byId("upload-message"), error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function startTrainingRun() {
  const button = byId("start-training");
  button.disabled = true;
  setMessage(byId("training-message"), "학습 작업을 등록하는 중…");
  try {
    const data = await api("/api/training/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    setMessage(byId("training-message"), `${data.run_id} 실행이 시작되었습니다.`);
    setTimeout(refreshTraining, 800);
  } catch (error) {
    setMessage(byId("training-message"), error.message, true);
  } finally {
    button.disabled = false;
  }
}

function initialize() {
  byId("api-key").value = state.apiKey;
  byId("api-key").addEventListener("change", (event) => {
    state.apiKey = event.target.value.trim();
    sessionStorage.setItem("cadAiApiKey", state.apiKey);
    refreshHealth();
    refreshJobs();
    refreshTraining();
  });
  byId("cad-file").addEventListener("change", (event) => {
    const file = event.target.files[0];
    byId("file-summary").textContent = file
      ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB`
      : "DXF · STEP · STP / 최대 50 MB";
  });
  const dropZone = byId("drop-zone");
  ["dragenter", "dragover"].forEach((name) => dropZone.addEventListener(name, () => dropZone.classList.add("dragging")));
  ["dragleave", "drop"].forEach((name) => dropZone.addEventListener(name, () => dropZone.classList.remove("dragging")));
  byId("upload-form").addEventListener("submit", submitUpload);
  byId("refresh-jobs").addEventListener("click", refreshJobs);
  byId("start-training").addEventListener("click", startTrainingRun);
  byId("close-dialog").addEventListener("click", () => byId("job-dialog").close());
  refreshHealth();
  refreshJobs();
  refreshTraining();
  state.pollTimer = window.setInterval(() => {
    if (!document.hidden) {
      refreshJobs();
      refreshTraining();
    }
  }, 3500);
}

document.addEventListener("DOMContentLoaded", initialize);

