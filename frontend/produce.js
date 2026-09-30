/* 제작(자막교체) 탭 로직. IIFE로 전역 격리(app.js/finder.js와 충돌 방지). */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const api = "/api/produce";
  let job = null;
  let timer = null;
  const BUSY = ["analyzing", "translating", "rendering"];

  async function jget(p) {
    const r = await fetch(api + p);
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.status);
    return r.json();
  }
  async function jsend(method, p, body, isForm) {
    const opt = { method };
    if (isForm) { opt.body = body; }
    else { opt.headers = { "Content-Type": "application/json" }; opt.body = body ? JSON.stringify(body) : undefined; }
    const r = await fetch(api + p, opt);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || ("오류 " + r.status));
    return data;
  }
  const esc = (s) => String(s || "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---------- 초기화 / 진입점 ----------
  async function init() {
    try {
      const r = await fetch("/api/finder/health");
      const h = r.ok ? await r.json() : null;
      if (h) $("p-health").textContent = h.anthropic_key ? "Claude ✓" : "Claude ✗ (자막 인식·번역에 필요)";
    } catch (_) {}
  }
  window.__produceInit = init;

  // 소재 찾기 → 제작 넘겨받기
  window.__produceFromFinder = async function (videoId) {
    try {
      const j = await jsend("POST", "/from_finder", { video_id: videoId });
      const btn = document.querySelector('.apptab[data-app="produce"]');
      if (btn) btn.click();
      job = j; render();
    } catch (e) { alert("제작으로 보내기 실패: " + e.message); }
  };

  // ---------- 업로드 ----------
  async function upload() {
    const f = $("p-file").files[0];
    if (!f) { alert("MP4 파일을 선택하세요."); return; }
    $("p-upload").disabled = true;
    $("p-input-msg").textContent = "업로드 중...";
    try {
      const fd = new FormData(); fd.append("file", f);
      job = await jsend("POST", "/upload", fd, true);
      $("p-input-msg").textContent = "업로드 완료.";
      await startAnalyze();
    } catch (e) { $("p-input-msg").textContent = "실패: " + e.message; }
    finally { $("p-upload").disabled = false; }
  }

  async function startAnalyze() {
    try { await jsend("POST", "/" + job.id + "/analyze"); poll(); }
    catch (e) { alert("자막 인식 실패: " + e.message); }
  }
  async function startTranslate() {
    try { await jsend("POST", "/" + job.id + "/translate"); poll(); }
    catch (e) { alert("번역 실패: " + e.message); }
  }
  async function startRender() {
    try { await saveJa(true); await jsend("POST", "/" + job.id + "/render"); poll(); }
    catch (e) { alert("렌더 실패: " + e.message); }
  }

  // ---------- 폴링 ----------
  function poll() {
    clearInterval(timer);
    const tick = async () => {
      try {
        job = await jget("/" + job.id);
        render();
        if (!BUSY.includes(job.status)) clearInterval(timer);
      } catch (e) { clearInterval(timer); }
    };
    tick();
    timer = setInterval(tick, 1500);
  }

  // ---------- 렌더링(화면) ----------
  function show(id, on) { const el = $(id); if (el) el.hidden = !on; }
  function render() {
    if (!job) return;
    const busy = BUSY.includes(job.status);
    const prog = $("p-progress");
    prog.hidden = !busy && job.status !== "error";
    prog.textContent = job.message || job.status;

    show("p-card-src", job.status === "analyzed");
    show("p-card-ja", job.status === "translated");
    show("p-card-out", job.status === "done");

    if (job.status === "analyzed") renderSrc();
    if (job.status === "translated") renderJa();
    if (job.status === "done") {
      const v = $("p-out-video"); v.src = api + "/" + job.id + "/output?t=" + Date.now();
      $("p-download").href = api + "/" + job.id + "/download";
    }
  }

  function renderSrc() {
    const box = $("p-src-segs");
    box.innerHTML = "";
    job.segments.forEach((s) => {
      const row = document.createElement("div");
      row.className = "p-seg";
      row.innerHTML = `<div class="t">#${s.index}<br>${s.start.toFixed(1)}~${s.end.toFixed(1)}s</div>
        <div><textarea data-i="${s.index}" rows="2">${esc(s.text_kr)}</textarea>
        ${s.text_ko ? `<div class="kr">${esc(s.text_ko)}</div>` : ""}</div>`;
      box.appendChild(row);
    });
  }

  function renderJa() {
    // 미리보기 영상 + 띠
    const v = $("p-video");
    if (v.dataset.jid !== job.id) { v.src = api + "/" + job.id + "/source"; v.dataset.jid = job.id; }
    $("p-band-top").value = job.band_top;
    $("p-band-bottom").value = job.band_bottom;
    $("p-cover").value = job.cover_mode;
    $("p-fontscale").value = job.font_scale;
    drawBand();
    // 세그먼트(일본어 편집)
    const box = $("p-ja-segs");
    box.innerHTML = "";
    job.segments.forEach((s) => {
      const row = document.createElement("div");
      row.className = "p-seg";
      row.innerHTML = `<div class="t">#${s.index}<br>${s.start.toFixed(1)}~${s.end.toFixed(1)}s</div>
        <div><div class="en">${esc(s.text_kr)}</div>
        <textarea data-i="${s.index}" rows="2">${esc(s.text_ja)}</textarea>
        ${s.text_ja_back ? `<div class="kr">↩ ${esc(s.text_ja_back)}</div>` : ""}</div>`;
      box.appendChild(row);
    });
  }

  function drawBand() {
    const top = parseFloat($("p-band-top").value);
    const bottom = parseFloat($("p-band-bottom").value);
    const band = $("p-band");
    band.style.top = (top * 100) + "%";
    band.style.height = (Math.max(0, bottom - top) * 100) + "%";
  }

  // ---------- 저장 ----------
  async function saveSrc() {
    const segs = Array.from($("p-src-segs").querySelectorAll("textarea"))
      .map((t) => ({ index: +t.dataset.i, text_kr: t.value }));
    await jsend("PATCH", "/" + job.id + "/segments", { segments: segs });
    $("p-src-msg").textContent = "저장됨 ✓";
  }
  async function saveJa(silent) {
    const segs = Array.from($("p-ja-segs").querySelectorAll("textarea"))
      .map((t) => ({ index: +t.dataset.i, text_ja: t.value }));
    if (segs.length) await jsend("PATCH", "/" + job.id + "/segments", { segments: segs });
    await jsend("PUT", "/" + job.id + "/band", {
      band_top: parseFloat($("p-band-top").value),
      band_bottom: parseFloat($("p-band-bottom").value),
      cover_mode: $("p-cover").value,
      font_scale: parseFloat($("p-fontscale").value),
    });
    if (!silent) $("p-ja-msg").textContent = "저장됨 ✓";
  }

  // ---------- 바인딩 ----------
  function bind() {
    $("p-upload").addEventListener("click", upload);
    $("p-save-src").addEventListener("click", () => saveSrc().catch((e) => alert(e.message)));
    $("p-to-translate").addEventListener("click", () => saveSrc().then(startTranslate).catch((e) => alert(e.message)));
    $("p-save-ja").addEventListener("click", () => saveJa(false).catch((e) => alert(e.message)));
    $("p-render").addEventListener("click", startRender);
    $("p-restart").addEventListener("click", () => {
      job = null; clearInterval(timer);
      ["p-card-src", "p-card-ja", "p-card-out"].forEach((id) => show(id, false));
      $("p-progress").hidden = true; $("p-file").value = ""; $("p-input-msg").textContent = "";
    });
    ["p-band-top", "p-band-bottom"].forEach((id) => $(id).addEventListener("input", drawBand));
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
  else bind();
})();
