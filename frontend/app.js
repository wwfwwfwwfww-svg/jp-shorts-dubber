"use strict";
const $ = (id) => document.getElementById(id);
let currentJob = null;
let job = null;
let voicesLoaded = false;
let pollTimer = null;
const NATURAL_CPS = 6.0;
const SPEED_MIN = 1.00, SPEED_MAX = 1.18;
const clampSpeed = (s) => Math.min(SPEED_MAX, Math.max(SPEED_MIN, s));
let forcedView = null;   // manual "back" override; null = follow job.status
let lastView = null;     // last shown view, to scroll only when it changes
const PUNCT = new Set([..."、。，．！？!?…「」『』（）()【】《》・:：;；~〜\"'`.,·—–-‥　 \t\n\r"]);

function fmt(t) { const m = Math.floor(t / 60), s = t % 60; return `${m}:${s.toFixed(1).padStart(4, "0")}`; }
function countChars(t) { let n = 0; for (const ch of (t || "")) if (!PUNCT.has(ch) && ch.trim()) n++; return n; }
function setStatus(msg, err) { const e = $("status"); e.textContent = msg || ""; e.classList.toggle("error", !!err); }

async function loadHealth() {
  try {
    const h = await (await fetch("/api/health")).json();
    $("health").textContent =
      (h.anthropic_key ? "Claude키 ✓" : "Claude키 ✗ (1·2·4단계 필요)") + "  ·  " +
      (h.elevenlabs_key ? "ElevenLabs키 ✓" : "ElevenLabs키 ✗ (3단계 필요)");
  } catch (e) {}
}
async function loadVoices() {
  if (voicesLoaded) return;
  try {
    const d = await (await fetch("/api/voices")).json();
    if (!d.voices) return;
    const sel = $("voice-select");
    sel.innerHTML = '<option value="">기본/자동 음성</option>';
    for (const v of d.voices) {
      const o = document.createElement("option"); o.value = v.voice_id; o.textContent = v.name;
      if (v.voice_id === d.default) o.selected = true; sel.appendChild(o);
    }
    voicesLoaded = true;
  } catch (e) {}
}

// --- tabs ---
document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
  t.classList.add("active");
  $("panel-upload").hidden = t.dataset.tab !== "upload";
  $("panel-japaste").hidden = t.dataset.tab !== "japaste";
}));

// --- start: upload ---
$("upload-btn").addEventListener("click", async () => {
  const url = $("url").value.trim(), file = $("file").files[0];
  if (!url && !file) { setStatus("URL 또는 파일을 입력하세요.", true); return; }
  const fd = new FormData();
  if (url) fd.append("url", url);
  if (file) fd.append("file", file);
  fd.append("crop_top_ratio", $("crop_top").value);
  fd.append("crop_bottom_ratio", $("crop_bottom").value);
  $("upload-btn").disabled = true; setStatus("업로드 중...");
  try {
    const r = await fetch("/api/jobs", { method: "POST", body: fd });
    const d = await r.json(); if (!r.ok) throw new Error(d.detail || r.statusText);
    currentJob = d.id; $("card-input").hidden = true; poll();
  } catch (e) { setStatus("오류: " + e.message, true); }
  finally { $("upload-btn").disabled = false; }
});

// --- start: japaste backup ---
$("jadirect-btn").addEventListener("click", async () => {
  const text = $("jadirect-text").value.trim();
  if (!text) { setStatus("일본어 대본이 비어 있습니다.", true); return; }
  $("jadirect-btn").disabled = true; setStatus("가져오는 중...");
  try {
    const r = await fetch("/api/jobs/import_ja", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, title: $("jadirect-title").value.trim() }) });
    const d = await r.json(); if (!r.ok) throw new Error(d.detail || r.statusText);
    currentJob = d.id; $("card-input").hidden = true; poll();
  } catch (e) { setStatus("오류: " + e.message, true); }
  finally { $("jadirect-btn").disabled = false; }
});

// --- gate buttons ---
$("extract-btn").addEventListener("click", () => gate("extract-btn", `/api/jobs/${currentJob}/extract`));
$("to-translate").addEventListener("click", async () => { await saveSource(); gate("to-translate", `/api/jobs/${currentJob}/translate`); });
$("to-tts").addEventListener("click", async () => {
  await saveJa();
  gate("to-tts", `/api/jobs/${currentJob}/tts`, { voice_id: $("voice-select").value, speed: currentSpeed() });
});
function currentSpeed() {
  const v = parseFloat($("speed-range").value);
  return clampSpeed(isNaN(v) ? SPEED_MIN : v);
}
$("to-meta").addEventListener("click", () => { $("card-meta").hidden = false; $("card-meta").scrollIntoView({ behavior: "smooth" }); });
$("meta-btn").addEventListener("click", () => gate("meta-btn", `/api/jobs/${currentJob}/metadata`));
$("meta-regen").addEventListener("click", () => gate("meta-regen", `/api/jobs/${currentJob}/metadata`));

async function gate(btnId, path, body) {
  forcedView = null;   // moving forward: follow the job status again
  $(btnId).disabled = true; setStatus("요청 중...");
  try {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}) });
    const d = await r.json(); if (!r.ok) throw new Error(d.detail || r.statusText);
    poll();
  } catch (e) { setStatus("오류: " + e.message, true); $(btnId).disabled = false; }
}

// --- save edits ---
async function patchSegments(segments) {
  const r = await fetch(`/api/jobs/${currentJob}/segments`, { method: "PATCH",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ segments }) });
  if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
}
async function saveSource() {
  const segs = [];
  document.querySelectorAll("#source-segments .seg").forEach((row) => segs.push({
    index: +row.querySelector("textarea").dataset.index,
    text_kr: row.querySelector("textarea").value, type: row.querySelector("select").value }));
  if (segs.length) await patchSegments(segs);
}
async function saveJa() {
  const segs = [];
  document.querySelectorAll("#ja-segments .seg").forEach((row) => segs.push({
    index: +row.querySelector("textarea").dataset.index, text_ja: row.querySelector("textarea").value }));
  if (segs.length) await patchSegments(segs);
}
$("save-src").addEventListener("click", async () => {
  $("save-src-msg").textContent = "저장 중..."; try { await saveSource(); $("save-src-msg").textContent = "저장됨 ✓"; }
  catch (e) { $("save-src-msg").textContent = "실패: " + e.message; }
  setTimeout(() => ($("save-src-msg").textContent = ""), 1500);
});
$("save-ja").addEventListener("click", async () => {
  $("save-ja-msg").textContent = "저장 중..."; try { await saveJa(); await refreshBudget(); $("save-ja-msg").textContent = "저장됨 ✓"; }
  catch (e) { $("save-ja-msg").textContent = "실패: " + e.message; }
  setTimeout(() => ($("save-ja-msg").textContent = ""), 1500);
});

// --- poll ---
const INPROGRESS = ["created", "downloading", "extracting", "translating", "dubbing", "qa", "generating_meta"];
function poll() {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => {
    try {
      job = await (await fetch(`/api/jobs/${currentJob}`)).json();
      setStatus(`[${job.status}] ${job.message || ""}`, job.status === "error");
      render(job);
      if (INPROGRESS.includes(job.status)) poll();
    } catch (e) { setStatus("폴링 오류: " + e.message, true); }
  }, 1400);
}

const STEP = { uploaded: 0, extracting: 1, stage1_ready: 1, translating: 2, stage2_ready: 2,
  dubbing: 3, qa: 3, stage3_ready: 3, generating_meta: 4, done: 4 };
// Which exclusive card to show. forcedView (from "← 이전 단계") overrides status.
function viewOf(st) {
  if (forcedView) return forcedView;
  if (st === "uploaded") return "uploaded";
  if (st === "stage1_ready") return "stage1";
  if (st === "stage2_ready") return "stage2";
  if (["stage3_ready", "generating_meta", "done"].includes(st)) return "final";
  return "";   // in-progress / error: don't switch cards
}
// A stage can be revisited only if its data exists on the job.
function canView(view, j) {
  const has = (j.segments || []);
  if (view === "stage1") return has.length > 0;
  if (view === "stage2") return has.some((s) => s.text_ja);
  if (view === "final") return has.some((s) => s.audio_file) || !!j.qa;
  return true;
}
function render(j) {
  const st = j.status;
  document.querySelectorAll(".step").forEach((s) => s.classList.toggle("on", +s.dataset.step <= (STEP[st] ?? -1)));

  const view = viewOf(st);
  $("return-latest").hidden = !forcedView;

  $("gate-extract").hidden = view !== "uploaded";
  if (view === "uploaded") {
    const m = j.meta; $("meta-line").textContent = `길이 ${fmt(m.duration)} · ${m.width}×${m.height} · ${m.fps}fps` + (m.title ? ` · ${m.title}` : "");
    $("extract-btn").disabled = false;
  }

  if (view) {
    $("card-source").hidden = view !== "stage1";
    $("card-ja").hidden = view !== "stage2";
    $("card-tts").hidden = view !== "final";
    $("card-meta").hidden = view !== "final";
    if (view === "stage1") renderSource(j);
    if (view === "stage2") { renderJa(j); loadVoices(); }
    if (view === "final") {
      renderTts(j);
      if (j.metadata) renderMeta(j.metadata);
      $("meta-btn").disabled = false; $("meta-regen").disabled = false;
    }
    if (view !== lastView) {
      const card = { uploaded: "gate-extract", stage1: "card-source", stage2: "card-ja", final: "card-tts" }[view];
      if (card && !$(card).hidden) $(card).scrollIntoView({ behavior: "smooth", block: "start" });
      lastView = view;
    }
  }
  if (st === "error") { document.querySelectorAll(".next,#extract-btn,#meta-btn,#meta-regen,.back").forEach((b) => (b.disabled = false)); }
}
// --- back / return navigation (no paid re-calls; data is cached on the job) ---
function goView(v) { forcedView = v; if (job) render(job); }
$("back-to-src").addEventListener("click", () => goView("stage1"));
$("back-to-ja").addEventListener("click", () => goView("stage2"));
$("return-latest").addEventListener("click", () => { forcedView = null; if (job) render(job); });

function segRow(seg, cls, val, withType) {
  const back = cls === "ja" ? seg.text_ja_back : (cls === "src" ? seg.text_ko : "");
  const div = document.createElement("div"); div.className = "seg" + (withType ? "" : " ja-row");
  div.innerHTML = `<div class="time"><b>#${seg.index}</b> ${fmt(seg.start)}→${fmt(seg.end)}<div>(${seg.duration.toFixed(1)}s)</div></div>
    <div><textarea data-index="${seg.index}" ${cls === "ja" ? 'lang="ja"' : ""}></textarea>${back ? `<div class="back"></div>` : ""}</div>
    ${withType ? `<div><select data-index="${seg.index}"><option value="narration">나레이션</option><option value="dialogue">대사</option></select></div>` : ""}`;
  div.querySelector("textarea").value = val;
  if (withType) div.querySelector("select").value = seg.type;
  if (back) div.querySelector(".back").textContent = "🇰🇷 " + back;
  return div;
}
function renderSource(j) {
  $("card-source").hidden = false; $("src-count").textContent = `· ${j.segments.length}구간 · ${j.source_lang || "?"}`;
  // Coherent Korean plot summary from Stage 1 (falls back to joined raw text).
  const raw = j.segments.map((s) => (s.text_ko || s.text_kr || "").trim()).filter(Boolean).join(" ");
  $("source-story").value = j.summary_ko || raw || "(인식된 텍스트가 없습니다)";
  const title = j.title_ko || j.title_ja;
  $("src-title").innerHTML = title
    ? `🎬 추정 제목: <b>${j.title_ko || ""}</b>${j.title_ja ? ` <span>(${j.title_ja})</span>` : ""}`
    : "";
  const w = $("source-segments"); w.innerHTML = "";
  j.segments.forEach((s) => w.appendChild(segRow(s, "src", s.text_kr, true)));
  $("to-translate").disabled = false;
}
function renderJa(j) {
  $("card-ja").hidden = false; $("ja-count").textContent = `· ${j.segments.length}구간`;
  const w = $("ja-segments"); w.innerHTML = "";
  j.segments.forEach((s) => {
    const row = segRow(s, "ja", s.text_ja, false);
    row.querySelector("textarea").addEventListener("input", liveBudget);
    w.appendChild(row);
  });
  $("to-tts").disabled = false;
  // Default the speed slider to the speed Stage 2 computed (clamped to range).
  $("speed-range").value = clampSpeed(j.speed || SPEED_MIN).toFixed(2);
  $("speed-range").oninput = refreshEstimate;
  renderBudget(j.char_actual, clampSpeed(j.speed), j.char_target_min, j.char_target_max);
  refreshEstimate();
}
function renderBudget(chars, speed, cmin, cmax) {
  const ok = chars >= cmin && chars <= cmax;
  $("ja-budget").innerHTML = `총 글자수 <b>${chars}</b> (목표 ${cmin}~${cmax}) ` +
    (ok ? '<span class="fit-ok">✓ 범위 내</span>' : '<span class="fit-warn">⚠ 목표 범위 밖</span>');
}
// Live estimate of the final dub length vs the narration span, for the chosen speed.
function refreshEstimate() {
  let total = 0;
  document.querySelectorAll("#ja-segments textarea").forEach((t) => (total += countChars(t.value)));
  const span = job.active_seconds || 0;
  const speed = currentSpeed();
  $("speed-out").textContent = "x" + speed.toFixed(2);
  const est = total / (NATURAL_CPS * speed);
  const diff = span ? est - span : 0;
  const pct = span ? (diff / span * 100) : 0;
  const cls = Math.abs(pct) <= 5 ? "fit-ok" : "fit-warn";
  $("len-est").innerHTML = `예상 길이 <b>${est.toFixed(1)}s</b> / 목표 ${span.toFixed(1)}s ` +
    `<span class="${cls}">(${diff >= 0 ? "+" : ""}${diff.toFixed(1)}s, ${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%)</span>`;
}
function liveBudget() {
  let total = 0;
  document.querySelectorAll("#ja-segments textarea").forEach((t) => (total += countChars(t.value)));
  renderBudget(total, currentSpeed(), job.char_target_min, job.char_target_max);
  refreshEstimate();
}
async function refreshBudget() {
  try { const d = await (await fetch(`/api/jobs/${currentJob}/speed_preview`)).json();
    renderBudget(d.char_actual, currentSpeed(), d.char_target_min, d.char_target_max); refreshEstimate(); } catch (e) {}
}
function renderTts(j) {
  $("card-tts").hidden = false;
  $("dl-mp3").href = `/api/jobs/${j.id}/download/mp3`;
  $("dl-wav").href = `/api/jobs/${j.id}/download/wav`;
  $("dl-srt-ja").href = `/api/jobs/${j.id}/download/srt_ja`;
  $("dl-srt-kr").href = `/api/jobs/${j.id}/download/srt_kr`;
  $("dl-zip").href = `/api/jobs/${j.id}/download/zip`;
  const qa = j.qa || { checks: [] };
  $("qa-box").innerHTML = `<div class="qa-head">자동 QA · 배속 x${(j.speed || 1).toFixed(3)}</div>` +
    qa.checks.map((c) => `<div class="qa-item ${c.ok ? "ok" : "warn"}">${c.ok ? "✅" : "⚠"} ${c.label} — <span>${c.detail}</span></div>`).join("");
  const w = $("tts-segments"); w.innerHTML = "";
  j.segments.forEach((s) => {
    const ad = s.audio_duration || 0;
    const div = document.createElement("div"); div.className = "seg-ja";
    div.innerHTML = `<div class="head"><span>#${s.index} · seq ${s.seq_start.toFixed(1)}s (+${ad.toFixed(1)}s)</span></div>
      <div class="ja"></div><div class="kr"></div>
      ${s.audio_file ? `<audio controls preload="none" src="/api/jobs/${j.id}/audio/${s.index}"></audio>` : ""}
      <div class="regen"><textarea data-index="${s.index}" lang="ja"></textarea><button data-index="${s.index}">이 구간 재생성</button></div>`;
    div.querySelector(".ja").textContent = s.text_ja || "(없음)";
    if (s.text_ja_back) div.querySelector(".kr").textContent = "KR: " + s.text_ja_back; else div.querySelector(".kr").remove();
    div.querySelector(".regen textarea").value = s.text_ja || "";
    div.querySelector(".regen button").addEventListener("click", (e) => regen(+e.target.dataset.index, div.querySelector(".regen textarea").value));
    w.appendChild(div);
  });
  $("to-meta").disabled = false;
}
async function regen(index, text_ja) {
  setStatus(`#${index} 재생성 요청...`);
  try {
    const r = await fetch(`/api/jobs/${currentJob}/segment/${index}/regenerate`, { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text_ja }) });
    const d = await r.json(); if (!r.ok) throw new Error(d.detail || r.statusText); poll();
  } catch (e) { setStatus("오류: " + e.message, true); }
}
function renderMeta(m) {
  const box = $("meta-result"); box.innerHTML = "";
  const block = (title, html) => { const d = document.createElement("div"); d.className = "mblock"; d.innerHTML = `<h4>${title}</h4>${html}`; box.appendChild(d); };
  if (m.titles) block("제목 후보", m.titles.map((t) => `<div class="pair"><b>JP</b> ${t.ja || ""}<br><span>KR ${t.ko || ""}</span></div>`).join(""));
  const thumbs = m.thumbnails || (m.thumbnail ? [m.thumbnail] : []);
  if (thumbs.length) block("썸네일 후킹 문구 (2줄 · 후보 " + thumbs.length + "개)",
    thumbs.map((t, i) => `<div class="pair"><b>#${i + 1} JP</b><pre>${(t.ja_lines || []).join("\n")}</pre><span>KR</span><pre>${(t.ko_lines || []).join("\n")}</pre></div>`).join(""));
  if (m.description) block("설명란", `<div class="pair"><b>JP</b><pre>${m.description.ja || ""}</pre><span>KR</span><pre>${m.description.ko || ""}</pre></div>`);
  if (m.tags) block("태그", `<pre>${(m.tags || []).join(", ")}</pre>`);
  $("meta-msg").textContent = "완료 ✓"; setTimeout(() => ($("meta-msg").textContent = ""), 1500);
}

// Resume an existing job via ?job=<id> (skips re-analysis).
(function resumeFromUrl() {
  const id = new URLSearchParams(location.search).get("job");
  if (id) { currentJob = id; $("card-input").hidden = true; poll(); }
})();

loadHealth();
