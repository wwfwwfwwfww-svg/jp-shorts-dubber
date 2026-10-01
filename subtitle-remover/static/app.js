"use strict";
// BUILD v7 (2026-10-01 폴더경로표시) — 화면 코드 버전 마커
(function () {
  const $ = (id) => document.getElementById(id);
  let jid = null;
  let boxes = [];          // {x,y,w,h} 비율(0~1)
  let drawing = false, sx = 0, sy = 0, cx = 0, cy = 0;
  let timer = null;
  let duration = 0;        // 영상 길이(초), 0이면 모름
  let seekTimer = null;

  // ---------- 버전 표시(화면이 최신 코드인지 바로 확인) ----------
  fetch("/api/version").then((r) => r.json()).then((d) => {
    if ($("build")) $("build").textContent = d.build || "?";
  }).catch(() => { if ($("build")) $("build").textContent = "서버 응답 없음"; });

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
      const fps = Number(d.fps) || 0;
      const durTxt = duration > 0 ? fmtTime(duration) : "길이 미상";
      $("vinfo").textContent = "감지됨: " + (d.width || "?") + "×" + (d.height || "?") +
        " · " + durTxt + (fps ? " · " + fps.toFixed(0) + "fps" : "");
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

  // 슬라이더 라벨: 길이를 알면 시간, 모르면 %만 표시
  function seekLabel(ratio) {
    const pct = Math.round(ratio * 100) + "%";
    if (duration > 0) return fmtTime(ratio * duration) + " / " + fmtTime(duration);
    return pct;
  }

  function setupSeek() {
    const seek = $("seek");
    // 길이 인식 여부와 무관하게 항상 표시(위치 비율 0~100% 기반).
    $("seekrow").hidden = false;
    seek.value = 0;
    $("seek-out").textContent = seekLabel(0);
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
    img.src = "/api/" + jid + "/frame?pos=0&_=" + Date.now();
    $("card-edit").scrollIntoView({ behavior: "smooth" });
  }

  // 타임스크롤: 위치 비율(0~1)로 장면만 바꿔 다시 그림(박스는 비율 좌표라 그대로 유지)
  function loadFrameAtRatio(ratio) {
    const img = $("frame");
    img.onload = () => redraw();
    img.src = "/api/" + jid + "/frame?pos=" + encodeURIComponent(ratio.toFixed(4)) + "&_=" + Date.now();
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

  // ---------- 타임 슬라이더 (위치 비율 0~1000 = 0~100%) ----------
  $("seek").addEventListener("input", () => {
    const ratio = (Number($("seek").value) || 0) / 1000;
    $("seek-out").textContent = seekLabel(ratio);
    clearTimeout(seekTimer);
    seekTimer = setTimeout(() => { if (jid) loadFrameAtRatio(ratio); }, 120);
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
      const maxSide = Number($("quality").value);  // 0=원본
      const r = await fetch("/api/" + jid + "/process", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          boxes, radius: Number($("radius").value),
          max_side: maxSide, target_fps: maxSide === 0 ? 0 : 30,
        }),
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
