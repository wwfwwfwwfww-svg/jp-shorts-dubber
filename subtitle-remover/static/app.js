"use strict";
(function () {
  const $ = (id) => document.getElementById(id);
  let jid = null;
  let boxes = [];          // {x,y,w,h} 비율(0~1)
  let drawing = false, sx = 0, sy = 0, cx = 0, cy = 0;
  let timer = null;

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
      $("upload-msg").textContent = "완료.";
      loadFrame();
    } catch (e) { $("upload-msg").textContent = "실패: " + e.message; }
    finally { $("upload-btn").disabled = false; }
  });

  function loadFrame() {
    const img = $("frame");
    img.onload = () => { syncCanvas(); $("card-edit").hidden = false;
      $("card-edit").scrollIntoView({ behavior: "smooth" }); };
    img.src = "/api/" + jid + "/frame?t=" + Date.now();
    boxes = [];
  }

  // ---------- 캔버스(네모 그리기) ----------
  const canvas = () => $("canvas");
  function syncCanvas() {
    const img = $("frame"), c = canvas();
    c.width = img.clientWidth; c.height = img.clientHeight;
    redraw();
  }
  window.addEventListener("resize", () => { if (jid) syncCanvas(); });

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
  ["mouseup", "touchend", "mouseleave"].forEach((ev) => canvas().addEventListener(ev, up));

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
    jid = null; boxes = []; clearInterval(timer);
    $("card-edit").hidden = true; $("card-result").hidden = true; $("progress").hidden = true;
    $("file").value = ""; $("upload-msg").textContent = "";
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
})();
