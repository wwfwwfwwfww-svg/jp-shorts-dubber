/* 소재 찾기 탭 — 전용 클라이언트 로직.
   전체를 IIFE로 감싸 전역을 오염시키지 않는다(app.js와 같은 전역 스코프를 공유하므로 필수). */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const el = (sel, root) => (root || document).querySelector(sel);
  const api = "/api/finder";
  let loaded = false;          // 첫 진입 시에만 초기 로드
  let categories = [];
  let searchTimer = null;
  let allVideos = [];          // 현재 필터로 받아온 전체 목록
  let shown = 0;               // 화면에 그린 개수(페이지네이션)
  const PAGE = 24;

  // ---------- 유틸 ----------
  async function jget(path) {
    const r = await fetch(api + path);
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.status);
    return r.json();
  }
  async function jsend(method, path, body) {
    const r = await fetch(api + path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || ("오류 " + r.status));
    return data;
  }
  function fmtViews(n) {
    n = Number(n) || 0;
    if (n >= 1e8) return (n / 1e8).toFixed(1) + "억";
    if (n >= 1e4) return Math.round(n / 1e4).toLocaleString() + "만";
    return n.toLocaleString();
  }
  function fmtDate(iso) {
    if (!iso) return "";
    return iso.slice(0, 10);
  }
  function fmtDur(sec) {
    sec = Number(sec) || 0;
    const m = Math.floor(sec / 60), s = sec % 60;
    return m + ":" + String(s).padStart(2, "0");
  }

  // ---------- 탭 전환 ----------
  function switchApp(which) {
    const panels = { dubbing: "tab-dubbing", finder: "tab-finder", produce: "tab-produce" };
    document.querySelectorAll(".apptab").forEach((b) =>
      b.classList.toggle("active", b.dataset.app === which));
    Object.entries(panels).forEach(([k, id]) => {
      const el = $(id); if (el) el.hidden = (k !== which);
    });
    if (which === "finder") {
      if (!loaded) { loaded = true; initFinder(); } else { refreshQuota(); }
    } else if (which === "produce" && typeof window.__produceInit === "function") {
      window.__produceInit();
    }
  }

  // ---------- 초기 로드 ----------
  async function initFinder() {
    await Promise.all([loadHealth(), loadCategories(), loadSettings(), refreshQuota()]);
    refreshGrid();
    loadChannels();
  }

  async function loadHealth() {
    try {
      const h = await jget("/health");
      const parts = [];
      parts.push(h.youtube_key ? "YouTube ✓" : "YouTube ✗(키 필요)");
      parts.push(h.anthropic_key ? "Claude ✓" : "Claude ✗");
      parts.push(h.telegram ? "Telegram ✓" : "Telegram –");
      $("f-health").textContent = parts.join("   ·   ");
      if (!h.youtube_key) { $("f-settings").hidden = false; }
    } catch (e) { $("f-health").textContent = "상태 확인 실패: " + e.message; }
  }

  async function refreshQuota() {
    try {
      const q = await jget("/quota");
      const q_el = $("f-quota");
      q_el.textContent = `쿼터 ${q.used.toLocaleString()} / ${q.limit.toLocaleString()}`;
      q_el.classList.toggle("warn", q.near_limit);
    } catch (_) {}
  }

  async function loadCategories() {
    categories = await jget("/categories");
    const wrap = $("f-categories");
    wrap.innerHTML = "";
    const filter = $("f-cat-filter");
    filter.innerHTML = '<option value="">카테고리 전체</option>';
    categories.forEach((c) => {
      const chip = document.createElement("div");
      chip.className = "f-chip";
      chip.dataset.name = c.name;
      chip.innerHTML = c.warn_tag
        ? `${c.name} <span class="warn" title="${c.warn_tag}">⚠</span>` : c.name;
      chip.addEventListener("click", () => chip.classList.toggle("on"));
      wrap.appendChild(chip);
      const opt = document.createElement("option");
      opt.value = c.name; opt.textContent = c.name;
      filter.appendChild(opt);
    });
  }

  async function loadSettings() {
    try {
      const s = await jget("/settings");
      $("f-set-floor").value = s.view_floor ?? "";
      $("f-set-perkw").value = s.per_keyword ?? "";
      $("f-set-morning").value = s.morning_hour ?? "";
      $("f-set-scan").value = s.scan_hours ?? "";
      $("f-set-regions").value = (s.regions || []).join(",");
      $("f-set-morning-en").checked = !!s.morning_enabled;
      $("f-floor").placeholder = "설정값 사용 (" + fmtViews(s.view_floor) + ")";
      $("f-perkw").value = s.per_keyword ?? 50;
    } catch (_) {}
  }

  // ---------- 설정 저장/검사 ----------
  async function saveSettings() {
    const patch = {
      view_floor: numOrNull($("f-set-floor").value),
      per_keyword: numOrNull($("f-set-perkw").value),
      morning_hour: numOrNull($("f-set-morning").value),
      scan_hours: numOrNull($("f-set-scan").value),
      regions: $("f-set-regions").value.split(",").map((x) => x.trim().toUpperCase()).filter(Boolean),
      morning_enabled: $("f-set-morning-en").checked,
    };
    const yt = $("f-yt-key").value.trim();
    const tgT = $("f-tg-token").value.trim();
    const tgC = $("f-tg-chat").value.trim();
    if (yt) patch.youtube_api_key = yt;
    if (tgT) patch.telegram_bot_token = tgT;
    if (tgC) patch.telegram_chat_id = tgC;
    $("f-settings-msg").textContent = "저장 중...";
    try {
      await jsend("PUT", "/settings", patch);
      $("f-settings-msg").textContent = "저장됨 ✓";
      $("f-yt-key").value = ""; $("f-tg-token").value = "";
      await Promise.all([loadHealth(), loadSettings()]);
    } catch (e) { $("f-settings-msg").textContent = "실패: " + e.message; }
  }

  async function validateKeys() {
    $("f-yt-status").textContent = "검사 중...";
    try {
      const body = {};
      const yt = $("f-yt-key").value.trim();
      if (yt) body.youtube_api_key = yt;
      const tgT = $("f-tg-token").value.trim();
      if (tgT) { body.telegram_bot_token = tgT; body.telegram_chat_id = $("f-tg-chat").value.trim(); }
      const res = await jsend("POST", "/validate_keys", body);
      let msg = res.youtube ? (res.youtube.ok ? "YouTube 키 유효 ✓" : "YouTube: " + res.youtube.error) : "";
      if (res.telegram) msg += res.telegram.ok ? "  ·  Telegram ✓" : "  ·  Telegram: " + res.telegram.error;
      $("f-yt-status").textContent = msg;
    } catch (e) { $("f-yt-status").textContent = "실패: " + e.message; }
  }

  function numOrNull(v) { v = String(v).trim(); return v === "" ? null : Number(v); }

  // ---------- 검색 요청 빌드 ----------
  function buildSearchReq() {
    const cats = Array.from(document.querySelectorAll(".f-chip.on")).map((c) => c.dataset.name);
    const kws = $("f-keywords").value.split(",").map((x) => x.trim()).filter(Boolean);
    return {
      keywords: kws,
      categories: cats,
      period: $("f-period").value,
      order: $("f-order").value,
      per_keyword: Number($("f-perkw").value) || 50,
      view_floor: numOrNull($("f-floor").value),
      translate_titles: true,
    };
  }

  async function estimate() {
    try {
      const est = await jsend("POST", "/estimate", buildSearchReq());
      $("f-estimate-out").textContent =
        `예상 ${est.estimated_points.toLocaleString()}포인트 ` +
        `(검색 ${est.search_calls}회 · 키워드 ${est.keyword_count} × 국가 ${est.region_count})` +
        (est.would_exceed ? " ⚠ 한도 초과 위험" : "");
    } catch (e) { $("f-estimate-out").textContent = "실패: " + e.message; }
  }

  async function startSearch() {
    const req = buildSearchReq();
    if (!req.keywords.length && !req.categories.length) {
      alert("카테고리를 선택하거나 키워드를 입력하세요."); return;
    }
    const log = $("f-search-log");
    log.hidden = false; log.textContent = "검색 시작 요청 중...";
    $("f-search").disabled = true;
    try {
      const { run_id } = await jsend("POST", "/search", req);
      pollSearch(run_id);
    } catch (e) {
      log.textContent = "오류: " + e.message;
      $("f-search").disabled = false;
    }
  }

  function pollSearch(runId) {
    clearInterval(searchTimer);
    const log = $("f-search-log");
    searchTimer = setInterval(async () => {
      try {
        const r = await jget("/search/" + runId);
        log.textContent = `${r.message}\n후보 ${r.collected || 0} · 신규 ${r.new || 0} · 쿼터 ${(r.quota_used||0).toLocaleString()}`;
        refreshQuota();
        if (["done", "error", "stopped_quota"].includes(r.status)) {
          clearInterval(searchTimer);
          $("f-search").disabled = false;
          if (r.error) log.textContent += "\n" + r.error;
          refreshGrid();
        }
      } catch (e) {
        clearInterval(searchTimer);
        $("f-search").disabled = false;
        log.textContent = "상태 조회 실패: " + e.message;
      }
    }, 1500);
  }

  // ---------- 결과 그리드 ----------
  function currentFilters() {
    return {
      sort: $("f-sort").value,
      min_multiple: $("f-mult").value,
      min_views: $("f-minviews").value,
      unentered_only: $("f-t-unentered").checked,
      small_channel_only: $("f-t-small").checked,
      hide_watched: $("f-t-hidewatched").checked,
      category: $("f-cat-filter").value,
    };
  }
  function filterQS() {
    const f = currentFilters();
    const p = new URLSearchParams();
    Object.entries(f).forEach(([k, v]) => { if (v !== "" && v !== false) p.set(k, v); });
    return p.toString();
  }

  async function refreshGrid() {
    try {
      const data = await jget("/videos?" + filterQS());
      allVideos = data.videos || [];
      shown = Math.min(PAGE, allVideos.length);
      renderGrid();
      const c = data.counts || {};
      window._f_total = c.total || 0;
      updateCount();
      $("f-export").href = api + "/videos/export.csv?" + filterQS();
    } catch (e) { $("f-count").textContent = "불러오기 실패: " + e.message; }
  }

  function updateCount() {
    $("f-count").textContent =
      `표시 ${Math.min(shown, allVideos.length)}/${allVideos.length} · 전체 ${window._f_total || 0}`;
  }

  function renderGrid() {
    const grid = $("f-grid");
    grid.innerHTML = "";
    $("f-empty").hidden = allVideos.length > 0;
    const catWarn = {};
    categories.forEach((c) => { if (c.warn_tag) catWarn[c.name] = c.warn_tag; });
    allVideos.slice(0, shown).forEach((v) => grid.appendChild(card(v, catWarn)));
    const more = $("f-more");
    if (more) more.hidden = shown >= allVideos.length;
    updateCount();
  }

  function card(v, catWarn) {
    const d = document.createElement("div");
    d.className = "f-vcard" + (v.status === "excluded" ? " excluded" : "");
    const subM = Number(v.sub_multiple) || 0;
    const chM = Number(v.chan_avg_multiple) || 0;
    const hot = subM >= 10;
    const un = v.japan_unentered === 1;
    const warn = catWarn[v.category];
    d.innerHTML = `
      <div class="f-thumb" data-vid="${v.video_id}">
        ${v.thumbnail ? `<img src="${v.thumbnail}" loading="lazy" alt="">` : ""}
        ${un ? '<span class="f-badge-un">일본 미진출</span>' : ""}
        ${v.region ? `<span class="f-region">${v.region}</span>` : ""}
        <span class="f-dur">${fmtDur(v.duration_sec)}</span>
      </div>
      <div class="f-vbody">
        <div class="f-vtitle" title="${escapeHtml(v.title)}">${escapeHtml(v.title)}</div>
        ${v.title_ko ? `<div class="f-vtitle-ko">${escapeHtml(v.title_ko)}</div>` : ""}
        <div class="f-vchan">${escapeHtml(v.channel_title)} · 구독 ${fmtViews(v.subscribers)}</div>
        <div class="f-vmetrics">
          <span><b>${fmtViews(v.views)}</b> 조회</span>
          <span class="f-mult ${hot ? "hot" : ""}">구독×${subM}</span>
          <span class="f-mult">채널평균×${chM}</span>
          <span>좋아요 ${(Number(v.like_rate) * 100).toFixed(1)}%</span>
        </div>
        <div class="f-vmetrics">
          <span>하루 ${fmtViews(v.daily_views)}</span>
          <span>${fmtDate(v.published_at)}</span>
          ${v.category ? `<span class="f-cat ${v.category_ai ? "ai" : ""}">${escapeHtml(v.category)}</span>` : ""}
        </div>
        ${warn ? `<span class="f-cat-warn">${warn}</span>` : ""}
        <div class="f-vbtns">
          <button data-act="bookmark" class="${v.status === "bookmark" ? "on" : ""}">${v.status === "bookmark" ? "★" : "☆"} 북마크</button>
          <button data-act="register">채널등록</button>
          <button data-act="exclude">제외</button>
          <button data-act="work" class="f-primary-mini">작업하기</button>
          <button data-act="produce">제작으로</button>
          <a href="https://youtu.be/${v.video_id}" target="_blank" rel="noopener">유튜브</a>
        </div>
      </div>`;
    d.querySelector(".f-thumb").addEventListener("click", () => openModal(v));
    d.querySelectorAll(".f-vbtns button").forEach((b) =>
      b.addEventListener("click", () => cardAction(b.dataset.act, v, d)));
    return d;
  }

  async function cardAction(act, v, node) {
    try {
      if (act === "bookmark") {
        const to = v.status === "bookmark" ? "new" : "bookmark";
        await jsend("PATCH", "/videos/" + v.video_id, { status: to });
        v.status = to; refreshGrid();
      } else if (act === "exclude") {
        await jsend("PATCH", "/videos/" + v.video_id, { status: "excluded" });
        refreshGrid();
      } else if (act === "register") {
        const cat = prompt("레퍼런스 채널 카테고리(선택):", v.category || "") || "";
        await jsend("POST", "/channels/" + v.channel_id + "/register", { category: cat });
        alert("채널을 레퍼런스에 등록했습니다.");
        loadChannels();
      } else if (act === "work") {
        await workVideo(v);
      } else if (act === "produce") {
        if (typeof window.__produceFromFinder === "function") window.__produceFromFinder(v.video_id);
      }
    } catch (e) { alert("실패: " + e.message); }
  }

  async function workVideo(v) {
    // 2단계(제작) 연결. 다운로드 엔드포인트는 M-C에서 활성화된다.
    try {
      const res = await jsend("POST", "/videos/" + v.video_id + "/work", {});
      alert(res.message || "작업 폴더로 다운로드를 시작했습니다.");
      refreshGrid();
    } catch (e) {
      if (String(e.message).includes("404")) {
        alert("‘작업하기’(다운로드 → 2단계 제작)는 다음 업데이트에서 활성화됩니다.");
      } else { alert("실패: " + e.message); }
    }
  }

  // ---------- 모달(임베드) ----------
  function openModal(v) {
    $("f-modal-body").innerHTML =
      `<h3 style="margin:0 0 8px;font-size:15px">${escapeHtml(v.title)}</h3>
       <iframe src="https://www.youtube.com/embed/${v.video_id}" allowfullscreen></iframe>`;
    $("f-modal").hidden = false;
    // 재생 = '본 영상'으로 표시
    if (!v.watched) { jsend("PATCH", "/videos/" + v.video_id, { watched: true }).catch(() => {}); v.watched = true; }
  }
  function closeModal() { $("f-modal").hidden = true; $("f-modal-body").innerHTML = ""; }

  // ---------- 레퍼런스 채널 ----------
  async function loadChannels() {
    try {
      const { channels } = await jget("/channels");
      const wrap = $("f-channels");
      if (!channels.length) { wrap.innerHTML = '<div class="f-channels-empty">등록된 레퍼런스 채널이 없습니다. 카드의 “채널등록”으로 추가하세요.</div>'; return; }
      let html = "<table><thead><tr><th>채널</th><th>구독자</th><th>평균조회수</th><th>수집영상</th><th>마지막 스캔</th><th></th></tr></thead><tbody>";
      channels.forEach((c) => {
        html += `<tr>
          <td>${escapeHtml(c.title)}</td>
          <td>${fmtViews(c.subscribers)}</td>
          <td>${fmtViews(c.avg_views)}</td>
          <td>${c.recent_hits || 0}</td>
          <td>${c.last_scan_at ? fmtDate(c.last_scan_at) : "–"}</td>
          <td><button data-scan="${c.channel_id}">스캔</button>
              <button data-del="${c.channel_id}">삭제</button></td>
        </tr>`;
      });
      html += "</tbody></table>";
      wrap.innerHTML = html;
      wrap.querySelectorAll("[data-scan]").forEach((b) => b.addEventListener("click", () => scanChannel(b.dataset.scan)));
      wrap.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", () => delChannel(b.dataset.del)));
    } catch (e) { $("f-channels").innerHTML = "불러오기 실패: " + e.message; }
  }
  async function scanChannel(id) {
    try { await jsend("POST", "/channels/scan?channel_id=" + encodeURIComponent(id)); alert("스캔을 시작했습니다."); }
    catch (e) { alert("실패: " + e.message); }
  }
  async function delChannel(id) {
    if (!confirm("이 레퍼런스 채널을 삭제할까요?")) return;
    try { await jsend("DELETE", "/channels/" + id); loadChannels(); } catch (e) { alert("실패: " + e.message); }
  }

  // ---------- 오늘의 리포트 ----------
  async function loadReport() {
    const box = $("f-report");
    box.innerHTML = '<div class="f-empty">집계 중...</div>';
    try {
      const [rep, sched] = await Promise.all([jget("/report/today"), jget("/scheduler").catch(() => null)]);
      renderReport(rep);
      if (sched) {
        const en = sched.morning_enabled ? `아침 ${sched.morning_hour}시 자동수집 ON` : "아침 자동수집 OFF";
        $("f-report-sched").textContent = `${en} · 스캔 ${sched.scan_hours}h · 스케줄러 ${sched.running ? "동작" : "중지"}`;
      }
    } catch (e) { box.innerHTML = "불러오기 실패: " + e.message; }
  }

  function renderReport(r) {
    const box = $("f-report");
    const g = r.gainers || [];
    const nt = r.new_today || { count: 0, by_category: [] };
    const wc = r.watch_channels || { multi: [], single: [] };
    const cs = r.category_stats || [];
    const un = r.unentered || [];
    const st = r.structure || { duration_buckets: {}, caption: {} };
    const li = (rows, fn) => rows.length ? rows.map(fn).join("") : '<div class="f-empty">없음</div>';

    box.innerHTML = `
      <div class="f-report-grid">
        <div class="f-rblock">
          <h3>① 어제 대비 급등 (조회수 증가폭)</h3>
          ${li(g.slice(0, 10), (v) => `<div class="f-rrow"><span>${escapeHtml(v.title)}</span>
            <b>+${fmtViews(v.delta)}</b></div>`)}
        </div>
        <div class="f-rblock">
          <h3>② 오늘 신규 ${nt.count}편 · 카테고리별</h3>
          ${li(nt.by_category, (c) => `<div class="f-rrow"><span>${escapeHtml(c.cat)}</span><b>${c.n}</b></div>`)}
        </div>
        <div class="f-rblock">
          <h3>③ 요주의 채널 (작은 채널·크게 터짐)</h3>
          <div class="f-rsub">여러 편 터진 곳</div>
          ${li(wc.multi, (c) => `<div class="f-rrow"><span>${escapeHtml(c.channel_title)} (구독 ${fmtViews(c.subscribers)})</span><b>${c.hits}편·×${c.max_mult}</b></div>`)}
          <div class="f-rsub">한 편만 터진 곳</div>
          ${li(wc.single, (c) => `<div class="f-rrow"><span>${escapeHtml(c.channel_title)} (구독 ${fmtViews(c.subscribers)})</span><b>×${c.max_mult}</b></div>`)}
        </div>
        <div class="f-rblock">
          <h3>④ 카테고리별 통계 (조회수 중앙값)</h3>
          ${li(cs, (c) => `<div class="f-rrow"><span>${escapeHtml(c.category)} · ${c.count}편</span><b>${fmtViews(c.median_views)}</b></div>`)}
        </div>
        <div class="f-rblock">
          <h3>⑤ 일본 미진출 소재 (${un.length})</h3>
          ${li(un.slice(0, 12), (v) => `<div class="f-rrow"><span>${escapeHtml(v.title)}</span><b>${fmtViews(v.views)}</b></div>`)}
        </div>
        <div class="f-rblock">
          <h3>⑥ 영상 구조 통계</h3>
          <div class="f-rsub">길이 분포</div>
          ${Object.entries(st.duration_buckets || {}).map(([k, v]) => `<div class="f-rrow"><span>${k}</span><b>${v}</b></div>`).join("")}
          <div class="f-rsub">첫 화면 자막(캡션)</div>
          <div class="f-rrow"><span>있음 / 없음 / 미상</span><b>${st.caption.yes || 0} / ${st.caption.no || 0} / ${st.caption.unknown || 0}</b></div>
        </div>
      </div>`;
  }

  // ---------- HTML escape ----------
  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // ---------- 이벤트 바인딩 ----------
  function bind() {
    document.querySelectorAll(".apptab").forEach((b) =>
      b.addEventListener("click", () => switchApp(b.dataset.app)));
    $("f-settings-btn").addEventListener("click", () => {
      const s = $("f-settings"); s.hidden = !s.hidden;
    });
    $("f-save-settings").addEventListener("click", saveSettings);
    $("f-validate").addEventListener("click", validateKeys);
    $("f-estimate").addEventListener("click", estimate);
    $("f-search").addEventListener("click", startSearch);
    $("f-refresh").addEventListener("click", refreshGrid);
    $("f-more").addEventListener("click", () => {
      shown = Math.min(shown + PAGE, allVideos.length);
      renderGrid();
    });
    $("f-clear").addEventListener("click", async () => {
      if (!confirm("수집 목록을 비웁니다.\n(북마크·작업·완료로 표시한 영상은 남습니다)\n계속할까요?")) return;
      try {
        const r = await jsend("POST", "/videos/clear", {});
        alert(`${r.deleted || 0}개 비웠습니다.`);
        refreshGrid();
      } catch (e) { alert("비우기 실패: " + e.message); }
    });
    $("f-categorize").addEventListener("click", async () => {
      try { const r = await jsend("POST", "/categorize", { limit: 40 }); alert(r.message); }
      catch (e) { alert("실패: " + e.message); }
    });
    $("f-japan").addEventListener("click", async () => {
      if (!confirm("배수 상위 영상의 일본 미진출 여부를 판별합니다. YouTube 쿼터를 사용합니다. 계속할까요?")) return;
      try { const r = await jsend("POST", "/japan_check", {}); alert(r.message); refreshQuota(); }
      catch (e) { alert("실패: " + e.message); }
    });
    ["f-sort", "f-mult", "f-minviews", "f-cat-filter"].forEach((id) =>
      $(id).addEventListener("change", refreshGrid));
    ["f-t-unentered", "f-t-small", "f-t-hidewatched"].forEach((id) =>
      $(id).addEventListener("change", refreshGrid));
    $("f-scan-all").addEventListener("click", async () => {
      try { await jsend("POST", "/channels/scan"); alert("전체 레퍼런스 채널 스캔을 시작했습니다."); }
      catch (e) { alert("실패: " + e.message); }
    });
    $("f-report-load").addEventListener("click", loadReport);
    $("f-modal-close").addEventListener("click", closeModal);
    $("f-modal").addEventListener("click", (e) => { if (e.target === $("f-modal")) closeModal(); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
  else bind();
})();
