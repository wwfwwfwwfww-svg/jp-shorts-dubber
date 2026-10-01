"use strict";
(function () {
  const $ = (id) => document.getElementById(id);
  let jid = null;
  let boxes = [];          // {x,y,w,h} 비율(0~1)
  let drawing = false, sx = 0, sy = 0, cx = 0, cy = 0;
  let timer = null;
  let duration = 0;        // 영상 길이(초)
  let seekTimer = null;

  // ---------- 업로드 ----------
  $("upload-btn").addEventListener("click", async () => {
    const f = $("file").files[0];
    if (!f) { alert("영상 파일을 선택하세요."); return; }
    $("upload-btn").disabled = true; $("upload-msg").textContent = "업로드 중...";
    try {
      const fd = new FormData(); fd.append("file", f);
      const r = await fetch("/api/upload", { method: "POST", body: fd });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "업로드 실패");
      jid = d.id;
      duration = Number(d.duration) || 0;
      $("upload-msg").textContent = "완료.";
      loadFrame();
    } catch (e) { $("upload-msg").textContent = "실패: " + e.message; }
    finally { $("upload-btn").disabled = false; }
  });

  function fmtTime(s) {
    s = Math.max(0, Math.floor(s || 0));
    const m = Math.floor(s / 60), r = s % 60;
    return m + ":" + String(r).padStart(2, "0");
  }

  function setupSeek() {
    const row = $("seekrow"), seek = $("seek"), out = $("seek-out");
    if (duration > 0) {
      row.hidden = false;
      seek.max = duration.toFixed(1);
      seek.value = 0;
      out.textContent = "0:00 / " + fmtTime(duration);
    } else {
      row.hidden = true;  // 길이를 못 구하면 숨김(첫 프레임만 사용)
    }
  }

  // 초기 업로드: 카드 표시 → 레이아웃 확정 후 캔버스 크기 맞춤 → 첫 프레임
  function loadFrame() {
    boxes = [];
    setupSeek();
    $("card-edit").hidden = false;
    const img = $("frame");
    img.onload = () => {
      requestAnimationFrame(() => requestAnimationFrame(syncCanvas));
    };
    img.src = "/api/" + jid + "/frame?t=0&_=" + Date.now();
    $("card-edit").scrollIntoView({ behavior: "smooth" });
  }

  // 타임스크롤: 장면만 바꿔 다시 그림(박스는 비율 좌표라 그대로 유지)
  function loadFrameAt(t) {
    const img = $("frame");
    img.onload = () => redraw();
    img.src = "/api/" + jid + "/frame?t=" + encodeURIComponent(t) + "&_=" + Date.now();
  }

  // ---------- 캔버스(네모 그리기) ----------
  const canvas = () => $("canvas");
  function syncCanvas() {
    const img = $("frame"), c = canvas();
    let w = img.clientWidth, h = img.clientHeight;
    if ((!w || !h) && img.naturalWidth) {
      // 레이아웃이 아직이면 자연 비율로 폴백
      const cw = img.parentElement ? img.parentElement.clientWidth : img.naturalWidth;
      w = cw || img.naturalWidth;
      h = Math.round(w * img.naturalHeight / img.naturalWidth);
    }
    c.width = w; c.height = h;
    c.style.width = w + "px"; c.style.height = h + "px";
    redraw();
  }
  window.addEventListener("resize", () => { if (jid) syncCanvas(); });

  // ---------- 타임 슬라이더 ----------
  $("seek").addEventListener("input", () => {
    const v = Number($("seek").value) || 0;
    $("seek-out").textContent = fmtTime(v) + " / " + fmtTime(duration);
    clearTimeout(seekTimer);
    seekTimer = setTimeout(() => { if (jid) loadFrameAt(v); }, 120);
  });

  function redraw() {
    const c = canvas(), ctx = c.getContext("2d");
    ctx.clearRect(0, 0, c.width, c.height);
    ctx.lineWidth = 2;
    // 확정된 박스
    boxes.forEach((b) => {
      ctx.strokeStyle = "#ff4d4d";
      ctx.fillStyle = "rgba(255,77,77,.28)";
      const x = b.x * c.width, y = b.y * c.height, w = b.w * c.width, h = b.h * c.height;
      ctx.fillRect(x, y, w, h); ctx.strokeRect(x, y, w, h);
    });
    // 그리는 중
    if (drawing) {
      ctx.strokeStyle = "#ffd24d"; ctx.fillStyle = "rgba(255,210,77,.25)";
      const x = Math.min(sx, cx), y = Math.min(sy, cy), w = Math.abs(cx - sx), h = Math.abs(cy - sy);
      ctx.fillRect(x, y, w, h); ctx.strokeRect(x, y, w, h);
    }
  }

  function pos(e) {
    const r = canvas().getBoundingClientRect();
    const t = e.touches ? e.touches[0] : e;
    return [t.clientX - r.left, t.clientY - r.top];
  }
  function down(e) { drawing = true; [sx, sy] = pos(e); [cx, cy] = [sx, sy]; e.preventDefault(); }
  function move(e) { if (!drawing) return; [cx, cy] = pos(e); redraw(); }
  function up() {
    if (!drawing) return;
    drawing = false;
    const c = canvas();
    const x = Math.min(sx, cx), y = Math.min(sy, cy), w = Math.abs(cx - sx), h = Math.abs(cy - sy);
    if (w > 6 && h > 6) {
      boxes.push({ x: x / c.width, y: y / c.height, w: w / c.width, h: h / c.height });
    }
    redraw();
  }
  ["mousedown", "touchstart"].forEach((ev) => canvas().addEventListener(ev, down));
  ["mousemove", "touchmove"].forEach((ev) => canvas().addEventListener(ev, move));
  ["touchend"].forEach((ev) => canvas().addEventListener(ev, up));
  // 캔버스 밖에서 손을 떼도 드래그가 끝나도록 document 레벨에서 마무리
  document.addEventListener("mouseup", up);

  $("undo").addEventListener("click", () => { boxes.pop(); redraw(); });
  $("clear").addEventListener("click", () => { boxes = []; redraw(); });
  $("radius").addEventListener("input", () => $("radius-out").textContent = $("radius").value);

  // ---------- 지우기 ----------
  $("run").addEventListener("click", async () => {
    if (!boxes.length) { alert("지울 부분에 네모를 하나 이상 치세요."); return; }
    $("run").disabled = true;
    $("progress").hidden = false; $("progress").textContent = "요청 중...";
    try {
      const r = await fetch("/api/" + jid + "/process", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ boxes, radius: Number($("radius").value) }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "처리 실패");
      poll();
    } catch (e) { $("progress").textContent = "오류: " + e.message; $("run").disabled = false; }
  });

  function poll() {
    clearInterval(timer);
    timer = setInterval(async () => {
      try {
        const r = await fetch("/api/" + jid);
        const d = await r.json();
        $("progress").textContent = d.message || d.status;
        if (d.status === "done") {
          clearInterval(timer); $("run").disabled = false;
          $("result").src = "/api/" + jid + "/result?t=" + Date.now();
          $("download").href = "/api/" + jid + "/download";
          $("card-result").hidden = false;
          $("card-result").scrollIntoView({ behavior: "smooth" });
        } else if (d.status === "error") {
          clearInterval(timer); $("run").disabled = false;
        }
      } catch (e) { clearInterval(timer); $("run").disabled = false; }
    }, 1500);
  }

  $("restart").addEventListener("click", () => {
    jid = null; boxes = []; duration = 0; clearInterval(timer); clearTimeout(seekTimer);
    $("card-edit").hidden = true; $("card-result").hidden = true; $("progress").hidden = true;
    $("seekrow").hidden = true;
    $("file").value = ""; $("upload-msg").textContent = "";
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
})();
