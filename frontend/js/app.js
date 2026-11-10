import { api, API_BASE_URL } from "./api.js";
import { fmtMinutes, renderLineChart, renderWeekdayChart } from "./charts.js";
import { initTasks, loadTasks } from "./tasks.js";

const $ = (sel) => document.querySelector(sel);
const WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"];

const state = {
  summary: null,
  statistics: null,
  data: [],             // 날짜 오름차순 + change 계산된 기록
  conversations: [],
  conversationId: null,
  editingId: null,
  kind: "all",          // 장부 필터: all | up | down
  range: "90",
  calMonth: null,       // "YYYY-MM"
  selectedDate: null,
  sending: false,
  insightDirty: true,
};

/* ================= 공통 유틸 ================= */
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
const renderRichText = (text) => escapeHtml(text).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
const signed = (min) => (min === null || min === undefined ? "-" : `${min > 0 ? "+" : ""}${fmtMinutes(min)}`);

function toast(message) {
  const t = $("#toast");
  t.textContent = message;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), 2600);
}
function isoOf(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
const todayISO = () => isoOf(new Date());
function weekdayOf(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return WEEKDAYS[(new Date(y, m - 1, d).getDay() + 6) % 7];
}
function prettyDate(iso, withYear = false) {
  const [y, m, d] = iso.split("-").map(Number);
  return `${withYear ? `${y}년 ` : ""}${m}월 ${d}일 (${weekdayOf(iso)})`;
}
function relativeTime(iso) {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "방금 전";
  if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}일 전`;
  return iso.slice(0, 10);
}
const kindOf = (r) => (r.change === null ? "first" : r.change > 0 ? "up" : r.change < 0 ? "down" : "flat");

/* ================= 테마 ================= */
function initTheme() {
  $("#theme-toggle").addEventListener("click", () => {
    const root = document.documentElement;
    const current = root.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    try { localStorage.setItem("tbm-theme", next); } catch (e) { /* noop */ }
    if (!$("#panel-insight").hidden) renderInsightCharts();
  });
}

/* ================= 탭 ================= */
function selectTab(id) {
  document.querySelectorAll(".tab").forEach((t) => {
    const on = t.id === id;
    t.setAttribute("aria-selected", String(on));
    $(`#${t.getAttribute("aria-controls")}`).hidden = !on;
  });
  if (id === "tab-insight") loadInsight();
  try { localStorage.setItem("tbm-tab", id); } catch (e) { /* noop */ }
}
function initTabs() {
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => selectTab(t.id)));
  let saved = location.hash ? `tab-${location.hash.slice(1)}` : null;
  if (!saved) {
    try { saved = localStorage.getItem("tbm-tab"); } catch (e) { /* noop */ }
  }
  if (saved && $(`#${saved}`)) selectTab(saved);
}

/* ================= 서버 깨우기 (Render 무료 티어 콜드스타트) ================= */
async function wakeServer() {
  const status = $("#server-status");
  const banner = $("#server-banner");
  const started = Date.now();
  const tick = () => {
    const sec = Math.round((Date.now() - started) / 1000);
    banner.textContent = `☕ 서버를 깨우는 중이에요 (${sec}초). 무료 서버는 한동안 접속이 없으면 잠들어서 첫 접속에 최대 1분 정도 걸려요.`;
  };
  const showTimer = setTimeout(() => { banner.hidden = false; tick(); }, 2500);
  const ticker = setInterval(tick, 1000);
  try {
    while (Date.now() - started < 100000) {
      try {
        await api.health(15000);
        status.className = "status-dot ok";
        status.title = "서버 연결됨";
        banner.hidden = true;
        return true;
      } catch (e) {
        await new Promise((r) => setTimeout(r, 2000));
      }
    }
    status.className = "status-dot bad";
    status.title = "서버 연결 실패";
    banner.hidden = false;
    banner.textContent = "⚠️ 서버에 연결하지 못했어요. 잠시 후 새로고침해 주세요.";
    return false;
  } finally {
    clearTimeout(showTimer);
    clearInterval(ticker);
  }
}

/* ================= 요약 (외상 장부 카드 + 갚기 좋은 날 카드) ================= */
async function loadSummary() {
  try {
    state.summary = await api.summary();
    renderOverview();
  } catch (e) {
    $("#ledger-card").innerHTML = `<p class="eyebrow">지금 장부에 달린 외상</p><p class="ledger-meta">${escapeHtml(e.message)}</p>`;
  }
}

function renderOverview() {
  const s = state.summary;
  if (!s || !s.count) {
    $("#ledger-card").innerHTML = '<p class="eyebrow">지금 장부에 달린 외상</p><p class="big">0<small>분</small></p><p class="ledger-meta">‘오늘 할 일’에 미룬 일을 맡겨 보세요.</p>';
    $("#repay-card").innerHTML = '<p class="eyebrow">갚기 좋은 날</p><p class="reason">장부가 쌓이면 몰래 사장이 골라줄게요.</p>';
    return;
  }
  const m = s.metrics;
  const t = s.trend;
  const credit = s.credit || {};
  const pay = s.payoff_forecast || {};
  const trendCls = t.label === "증가" ? "up" : t.label === "감소" ? "down" : "";
  const arrow = t.label === "증가" ? "▲" : t.label === "감소" ? "▼" : "–";

  $("#ledger-card").innerHTML = `
    <p class="eyebrow">지금 장부에 달린 외상 · ${m.current_date.slice(5).replace("-", "/")} 마감</p>
    <p class="big">${fmtMinutes(m.current)}</p>
    <div class="chips">
      <span class="chip-stat ${trendCls}">${arrow} 7일 추세 <b>${t.change_pct > 0 ? "+" : ""}${t.change_pct}%</b></span>
      <span class="chip-stat">손님 등급 <b>${escapeHtml(credit.grade || "-")}</b> · ${escapeHtml((credit.label || "").split(" — ")[0])}</span>
      <span class="chip-stat">${pay.estimated_date ? `다 갚는 날 <b>${pay.estimated_date.slice(5).replace("-", "/")}</b>` : escapeHtml(pay.status || "")}</span>
    </div>
    <p class="ledger-meta">${s.period.start} ~ ${s.period.end} · ${s.count}건 · 평균 ${fmtMinutes(m.average)} · 최대 ${fmtMinutes(m.max)} (${m.max_date})</p>`;

  const rec = s.recommendation || {};
  if (!rec.next_date) {
    $("#repay-card").innerHTML = `<p class="eyebrow">갚기 좋은 날</p><p class="reason">${escapeHtml(rec.reason || "데이터가 더 필요해요.")}</p>`;
    return;
  }
  const isToday = rec.next_date === todayISO();
  $("#repay-card").innerHTML = `
    <span class="stamp" aria-hidden="true">갚는<br/>날</span>
    <p class="eyebrow">${isToday ? "오늘이 갚기 좋은 날" : "다음 갚기 좋은 날"}</p>
    <p class="big">${prettyDate(rec.next_date)}</p>
    <p class="reason">${escapeHtml(rec.weekday)}요일엔 평균 <b>${fmtMinutes(-rec.average_change)}</b>씩 외상을 갚았어요. ${escapeHtml(rec.avoid_weekday)}요일엔 외상을 자주 다니 조심!</p>
    <div class="next-list" aria-label="이후 추천일">${(rec.next_dates || []).slice(1).map((d) => `<span>${d.slice(5).replace("-", "/")}</span>`).join("")}</div>`;
}

/* ================= 캘린더 ================= */
function shiftMonth(ym, delta) {
  const [y, m] = ym.split("-").map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function renderCalendar() {
  if (!state.calMonth) {
    const last = state.data[state.data.length - 1];
    state.calMonth = (last ? last.date : todayISO()).slice(0, 7);
  }
  const ym = state.calMonth;
  const [y, m] = ym.split("-").map(Number);
  $("#cal-title").textContent = `${y}. ${String(m).padStart(2, "0")}`;

  const byDate = Object.fromEntries(state.data.map((r) => [r.date, r]));
  const recDates = new Set(state.summary?.recommendation?.next_dates || []);
  const today = todayISO();
  const monthRows = state.data.filter((r) => r.date.startsWith(ym));
  const maxAbs = Math.max(30, ...state.data.map((r) => Math.abs(r.change || 0)));

  const first = new Date(y, m - 1, 1);
  const lead = (first.getDay() + 6) % 7; // 월요일 시작
  const days = new Date(y, m, 0).getDate();
  const cells = [];
  for (let i = 0; i < lead; i++) cells.push('<div class="cal-cell empty" aria-hidden="true"></div>');
  for (let d = 1; d <= days; d++) {
    const iso = `${ym}-${String(d).padStart(2, "0")}`;
    const r = byDate[iso];
    const cls = ["cal-cell"];
    let style = "";
    let body = "";
    if (r) {
      const k = kindOf(r);
      if (k === "up" || k === "down") {
        cls.push(k === "up" ? "is-up" : "is-down");
        const tint = Math.round(12 + (Math.abs(r.change) / maxAbs) * 48);
        style = `--tint:${tint}%`;
      }
      body = `<span class="cal-value">${fmtMinutes(r.value).replace("시간 ", "h ").replace("시간", "h").replace("분", "m")}</span>
              <span class="cal-change">${r.change === null ? "" : r.change === 0 ? "±0" : `${r.change > 0 ? "+" : ""}${Math.round(r.change)}`}</span>`;
    } else {
      cls.push("no-data");
    }
    if (iso > today) cls.push("future");
    if (iso === today) cls.push("today");
    if (recDates.has(iso)) cls.push("repay");
    if (iso === state.selectedDate) cls.push("selected");
    const label = `${prettyDate(iso)}${r ? ` 외상 ${fmtMinutes(r.value)}` : " 기록 없음"}${recDates.has(iso) ? ", 갚기 좋은 날" : ""}`;
    cells.push(`<button type="button" class="${cls.join(" ")}" style="${style}" data-date="${iso}" aria-label="${label}">
        <span class="cal-day">${d}${recDates.has(iso) ? '<span class="cal-tag">갚는 날</span>' : ""}</span>${body}</button>`);
  }
  $("#cal-grid").innerHTML = cells.join("");

  const up = monthRows.filter((r) => kindOf(r) === "up");
  const down = monthRows.filter((r) => kindOf(r) === "down");
  const net = monthRows.length ? monthRows[monthRows.length - 1].value - (byDate[monthRows[0].date].value - (monthRows[0].change || 0)) : 0;
  $("#cal-month-stats").innerHTML = monthRows.length
    ? `외상 단 날 <b class="up">${up.length}</b> · 갚은 날 <b class="down">${down.length}</b> · 이번 달 외상 변화 <b class="${net > 0 ? "up" : net < 0 ? "down" : ""}">${signed(net)}</b>`
    : '<span class="muted">이 달에는 기록이 없어요</span>';

  renderDayDetail();
}

function renderDayDetail() {
  const box = $("#day-detail");
  const iso = state.selectedDate || state.data[state.data.length - 1]?.date || todayISO();
  const r = state.data.find((d) => d.date === iso);
  const rec = state.summary?.recommendation;
  const isRepay = (rec?.next_dates || []).includes(iso);
  const repayNote = isRepay
    ? `<p class="repay-note">🪙 <b>갚기 좋은 날</b> · ${escapeHtml(rec.weekday)}요일엔 평균 ${fmtMinutes(-rec.average_change)}씩 외상을 갚았어요. 미뤄둔 일 하나를 갚아 보세요.</p>`
    : "";

  if (!r) {
    const future = iso > todayISO();
    box.innerHTML = `
      <p class="eyebrow">${prettyDate(iso, true)}</p>
      <p class="big muted">${future ? "예정" : "기록 없음"}</p>
      ${repayNote}
      ${future ? '<p class="note">미래 날짜는 기록할 수 없어요.</p>' : `<button class="btn btn-primary btn-small" type="button" data-add="${iso}">이 날 기록 추가</button>`}`;
    return;
  }
  const k = kindOf(r);
  const changeText = k === "first" ? "첫 기록" : k === "flat" ? "변화 없음" : `${k === "up" ? "▲ 외상 달았어요" : "▼ 외상 갚았어요"} ${signed(r.change)}`;
  box.innerHTML = `
    <p class="eyebrow">${prettyDate(iso, true)}</p>
    <p class="big">${fmtMinutes(r.value)}</p>
    <p class="${k === "up" ? "up" : k === "down" ? "down" : "muted"}"><b>${changeText}</b></p>
    ${repayNote}
    <p class="memo">${escapeHtml(r.memo || "메모 없음")}</p>
    <button class="btn btn-small" type="button" data-edit-date="${r.id}">이 기록 수정</button>`;
}

function initCalendar() {
  $("#cal-prev").addEventListener("click", () => { state.calMonth = shiftMonth(state.calMonth, -1); renderCalendar(); });
  $("#cal-next").addEventListener("click", () => { state.calMonth = shiftMonth(state.calMonth, 1); renderCalendar(); });
  $("#cal-today").addEventListener("click", () => { state.calMonth = todayISO().slice(0, 7); state.selectedDate = todayISO(); renderCalendar(); });
  $("#cal-grid").addEventListener("click", (evt) => {
    const cell = evt.target.closest("[data-date]");
    if (!cell) return;
    state.selectedDate = cell.dataset.date;
    renderCalendar();
  });
  $("#day-detail").addEventListener("click", (evt) => {
    const edit = evt.target.closest("[data-edit-date]");
    const add = evt.target.closest("[data-add]");
    if (edit) { selectTab("tab-data"); startEdit(edit.dataset.editDate); }
    if (add) { selectTab("tab-data"); resetForm(); $("#f-date").value = add.dataset.add; $("#f-value").focus(); }
  });
}

/* ================= 대화 기록 ================= */
async function loadConversations() {
  try { state.conversations = await api.listConversations(); } catch (e) { state.conversations = []; }
  renderConversationList();
}

function renderConversationList() {
  const list = $("#conversation-list");
  if (!state.conversations.length) {
    list.innerHTML = '<li class="empty">아직 대화가 없어요.<br />질문하면 자동 저장돼요.</li>';
    return;
  }
  list.innerHTML = state.conversations
    .map((c) => `
      <li class="conv-item ${c.id === state.conversationId ? "active" : ""}" data-id="${escapeHtml(c.id)}" tabindex="0" role="button" aria-label="${escapeHtml(c.title)} 불러오기">
        <span class="conv-title">${escapeHtml(c.title)}</span>
        <button class="conv-del" type="button" data-del="${escapeHtml(c.id)}" aria-label="대화 삭제" title="삭제">✕</button>
        <span class="conv-meta">${relativeTime(c.updated_at)} · ${c.message_count}개</span>
      </li>`)
    .join("");
}

async function openConversation(id) {
  if (state.sending) return;
  const box = $("#messages");
  box.innerHTML = '<div class="welcome"><span class="dots"><i></i><i></i><i></i></span></div>';
  try {
    const conv = await api.getConversation(id);
    state.conversationId = conv.id;
    $("#chat-title").textContent = conv.title;
    box.innerHTML = "";
    conv.messages.forEach((msg) => appendMessage(msg.role, msg.content, msg.tools_used));
    renderConversationList();
    $("#quick-questions").hidden = true;
  } catch (e) {
    toast(e.message);
    newChat();
  }
}

function greeting() {
  const s = state.summary;
  const pick = (list) => list[Math.floor(Math.random() * list.length)];
  const opener = pick([
    "어서오렴~ 오늘은 미래의 시간을 얼마나 외상으로 달아줄까? 🕶️",
    "쉿, 여긴 미래의 시간을 외상으로 당겨 쓰는 땅굴 구멍가게야. 들어와~",
    "오, 단골 손님 왔네! 외상 장부 한번 같이 볼까?",
  ]);
  if (!s || !s.count) return `${opener}\n아직 장부가 텅 비었네. '오늘 할 일'에 미룬 일부터 맡겨보렴.`;
  const rec = s.recommendation || {};
  const debt = fmtMinutes(s.metrics.current);
  const trend = s.trend.label === "감소" ? "요즘 꼬박꼬박 갚고 있구먼, 기특해~" : s.trend.label === "증가" ? "요새 외상이 좀 불어났더라?" : "장부가 잔잔~하네.";
  const next = rec.next_date ? ` 다음 갚기 좋은 날은 ${prettyDate(rec.next_date)}이야.` : "";
  return `${opener}\n지금 외상 장부엔 ${debt}이 달려 있어. ${trend}${next}`;
}

function newChat() {
  state.conversationId = null;
  $("#chat-title").textContent = "새 대화";
  $("#quick-questions").hidden = false;
  $("#messages").innerHTML = `
    <div class="welcome">
      <img class="merchant-hero" src="assets/mollae.svg" alt="몰래 사장" />
      <p class="speech">${escapeHtml(greeting())}</p>
      <p class="small muted">몰래 사장은 내 장부 요약을 보고 답해요. 필요하면 날짜별 기록이나 지난 대화도 직접 뒤져봐요.</p>
    </div>`;
  renderConversationList();
}

function initConversations() {
  $("#new-chat").addEventListener("click", newChat);
  $("#conversation-list").addEventListener("click", async (evt) => {
    const del = evt.target.closest("[data-del]");
    if (del) {
      evt.stopPropagation();
      if (!confirm("이 대화를 삭제할까요?")) return;
      try {
        await api.deleteConversation(del.dataset.del);
        if (state.conversationId === del.dataset.del) newChat();
        await loadConversations();
        toast("대화를 삭제했어요");
      } catch (e) { toast(e.message); }
      return;
    }
    const item = evt.target.closest(".conv-item");
    if (item) openConversation(item.dataset.id);
  });
  $("#conversation-list").addEventListener("keydown", (evt) => {
    const item = evt.target.closest(".conv-item");
    if (item && (evt.key === "Enter" || evt.key === " ")) {
      evt.preventDefault();
      openConversation(item.dataset.id);
    }
  });
}

/* ================= 채팅 ================= */
const TOOL_LABELS = {
  get_data_summary: "장부 요약 다시 봄",
  get_statistics: "요일·월별 장부 봄",
  get_records: "그때 장부 펼쳐봄",
  list_conversations: "지난 상담 목록 봄",
  get_conversation: "지난 상담 다시 봄",
  list_tasks: "남은 외상 확인",
};

function appendMessage(role, content, tools = [], { error = false } = {}) {
  const box = $("#messages");
  box.querySelector(".welcome")?.remove();
  const div = document.createElement("div");
  div.className = `msg ${role}${error ? " error" : ""}`;
  let row = div;
  if (role === "assistant") {
    // 몰래 사장 아바타 + 말풍선
    row = document.createElement("div");
    row.className = "msg-row";
    row.innerHTML = '<img class="avatar" src="assets/mollae.svg" alt="몰래 사장" />';
    row.appendChild(div);
  }
  div.innerHTML = renderRichText(content);
  if (tools && tools.length) {
    const t = document.createElement("div");
    t.className = "tools";
    t.innerHTML = tools
      .map((tool) => {
        const name = typeof tool === "string" ? tool : tool.name;
        const args = typeof tool === "object" && tool.arguments && Object.keys(tool.arguments).length
          ? ` ${Object.values(tool.arguments).join(" ~ ")}` : "";
        return `<span class="tool-badge" title="몰래 사장이 들춰본 장부: ${escapeHtml(name)}">🔧 ${escapeHtml(TOOL_LABELS[name] || name)}${escapeHtml(args)}</span>`;
      })
      .join("");
    div.appendChild(t);
  }
  box.appendChild(row);
  box.scrollTop = box.scrollHeight;
}

function showTyping() {
  const box = $("#messages");
  const div = document.createElement("div");
  div.className = "msg-row";
  div.innerHTML = '<img class="avatar" src="assets/mollae.svg" alt="" /><div class="msg assistant"><span class="typing"><span class="dots"><i></i><i></i><i></i></span><span class="typing-text">몰래 사장이 장부를 뒤적이는 중…</span></span></div>';
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  const started = Date.now();
  const timer = setInterval(() => {
    const sec = Math.round((Date.now() - started) / 1000);
    div.querySelector(".typing-text").textContent = sec > 20 ? `땅굴이 좀 깊어서… 조금만 기다려~ ${sec}초` : `몰래 사장이 장부를 뒤적이는 중… ${sec}초`;
  }, 1000);
  return () => { clearInterval(timer); div.remove(); };
}

async function sendMessage(text) {
  const message = text.trim();
  if (!message || state.sending) return;
  state.sending = true;
  $("#chat-send").disabled = true;
  $("#chat-input").value = "";
  autoGrow();
  $("#quick-questions").hidden = true;
  appendMessage("user", message);
  const stopTyping = showTyping();
  try {
    const res = await api.chat(message, state.conversationId);
    stopTyping();
    appendMessage("assistant", res.reply, res.tool_calls);
    const isNew = !state.conversationId;
    state.conversationId = res.conversation_id;
    $("#chat-title").textContent = res.title;
    await loadConversations();
    if (isNew) toast("상담 내용은 장부에 몰래 적어뒀어 📒");
  } catch (e) {
    stopTyping();
    appendMessage("assistant", `⚠️ ${e.message}`, [], { error: true });
  } finally {
    state.sending = false;
    $("#chat-send").disabled = false;
    $("#chat-input").focus();
  }
}

function autoGrow() {
  const ta = $("#chat-input");
  ta.style.height = "auto";
  ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
}

function initChat() {
  $("#chat-form").addEventListener("submit", (evt) => { evt.preventDefault(); sendMessage($("#chat-input").value); });
  $("#chat-input").addEventListener("keydown", (evt) => {
    if (evt.key === "Enter" && !evt.shiftKey && !evt.isComposing) {
      evt.preventDefault();
      sendMessage($("#chat-input").value);
    }
  });
  $("#chat-input").addEventListener("input", autoGrow);
  $("#quick-questions").addEventListener("click", (evt) => {
    const chip = evt.target.closest(".chip");
    if (chip) sendMessage(chip.textContent);
  });
}

/* ================= 장부 ================= */
async function loadData() {
  try {
    const rows = await api.listData();
    state.data = rows.map((r, i) => ({ ...r, change: i ? r.value - rows[i - 1].value : null }));
    renderMonthFilter();
    renderDataTable();
    renderCalendar();
  } catch (e) {
    $("#data-tbody").innerHTML = `<tr><td colspan="5" class="empty">${escapeHtml(e.message)}</td></tr>`;
  }
}

function renderMonthFilter() {
  const select = $("#data-month");
  const current = select.value || "all";
  const months = [...new Set(state.data.map((d) => d.date.slice(0, 7)))].reverse();
  select.innerHTML = `<option value="all">전체 기간</option>${months.map((mo) => `<option value="${mo}">${mo}</option>`).join("")}`;
  select.value = months.includes(current) ? current : "all";
}

function filteredRows() {
  const month = $("#data-month").value || "all";
  const inMonth = state.data.filter((r) => month === "all" || r.date.startsWith(month));
  return { inMonth, rows: state.kind === "all" ? inMonth : inMonth.filter((r) => kindOf(r) === state.kind) };
}

function renderDataTable(flashId) {
  const { inMonth, rows } = filteredRows();
  const up = inMonth.filter((r) => kindOf(r) === "up");
  const down = inMonth.filter((r) => kindOf(r) === "down");
  document.querySelector('[data-count="all"]').textContent = inMonth.length;
  document.querySelector('[data-count="up"]').textContent = up.length;
  document.querySelector('[data-count="down"]').textContent = down.length;

  const sum = (list) => list.reduce((acc, r) => acc + Math.abs(r.change), 0);
  const summary = {
    all: `총 <b>${inMonth.length}</b>일 · 외상 단 날 <b class="up">${up.length}</b> · 갚은 날 <b class="down">${down.length}</b>`,
    up: `외상을 단 <b>${up.length}</b>일 동안 새로 단 외상 <b class="up">+${fmtMinutes(sum(up))}</b> · 하루 평균 ${up.length ? fmtMinutes(sum(up) / up.length) : "-"}`,
    down: `외상을 갚은 <b>${down.length}</b>일 동안 갚은 외상 <b class="down">${fmtMinutes(sum(down))}</b> · 하루 평균 ${down.length ? fmtMinutes(sum(down) / down.length) : "-"}`,
  };
  $("#kind-summary").innerHTML = summary[state.kind];

  const tbody = $("#data-tbody");
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty">해당하는 기록이 없어요.</td></tr>';
    return;
  }
  tbody.innerHTML = rows
    .slice()
    .reverse()
    .map((r) => {
      const k = kindOf(r);
      return `<tr data-id="${escapeHtml(r.id)}" class="${r.id === flashId ? "flash" : ""}">
        <td class="mono">${r.date.slice(2).replaceAll("-", ".")} <span class="muted">${weekdayOf(r.date)}</span></td>
        <td class="num">${fmtMinutes(r.value)}</td>
        <td class="num ${k === "up" ? "up" : k === "down" ? "down" : "muted"}">${r.change === null ? "-" : signed(r.change)}</td>
        <td class="memo">${escapeHtml(r.memo)}</td>
        <td class="actions-col">
          <button class="btn-link" type="button" data-edit="${escapeHtml(r.id)}">수정</button>
          <button class="btn-link danger" type="button" data-delete="${escapeHtml(r.id)}">삭제</button>
        </td>
      </tr>`;
    })
    .join("");
  if (flashId) tbody.querySelector(".flash")?.scrollIntoView({ block: "nearest" });
}

function setFormMessage(text, kind = "") {
  const msg = $("#data-form-msg");
  msg.textContent = text;
  msg.className = `form-msg ${kind}`;
}

function resetForm() {
  state.editingId = null;
  $("#data-form").classList.remove("editing");
  $("#data-form-title").textContent = "새 기록";
  $("#data-submit").textContent = "추가";
  $("#data-cancel").hidden = true;
  $("#f-date").value = todayISO();
  $("#f-value").value = "";
  $("#f-memo").value = "";
  $("#f-value-hint").textContent = "";
}

function startEdit(id) {
  const row = state.data.find((d) => d.id === id);
  if (!row) return;
  state.editingId = id;
  $("#data-form").classList.add("editing");
  $("#data-form-title").textContent = `${prettyDate(row.date)} 수정`;
  $("#data-submit").textContent = "수정 저장";
  $("#data-cancel").hidden = false;
  $("#f-date").value = row.date;
  $("#f-value").value = row.value;
  $("#f-memo").value = row.memo;
  $("#f-value-hint").textContent = `= ${fmtMinutes(row.value)}`;
  setFormMessage("");
  $("#f-value").focus();
}

async function afterDataChange(flashId) {
  state.insightDirty = true;
  await Promise.all([loadData(), loadSummary()]);
  renderCalendar();
  renderDataTable(flashId);
  if (!$("#panel-insight").hidden) loadInsight();
}

function initLedger() {
  $("#f-date").max = todayISO();
  resetForm();
  $("#f-value").addEventListener("input", (e) => {
    $("#f-value-hint").textContent = e.target.value === "" ? "" : `= ${fmtMinutes(Number(e.target.value))}`;
  });
  $("#data-cancel").addEventListener("click", () => { resetForm(); setFormMessage(""); });

  $("#data-form").addEventListener("submit", async (evt) => {
    evt.preventDefault();
    const date = $("#f-date").value;
    const valueRaw = $("#f-value").value;
    const value = Number(valueRaw);
    const memo = $("#f-memo").value.trim();
    // 1차 검증 (최종 검증은 서버 Pydantic)
    if (!date) return setFormMessage("날짜를 선택하세요.", "err");
    if (date > todayISO()) return setFormMessage("미래 날짜는 기록할 수 없어요.", "err");
    if (valueRaw === "" || Number.isNaN(value) || value < 0) return setFormMessage("외상은 0 이상의 숫자(분)로 입력하세요.", "err");
    if (value > 10080) return setFormMessage("하루 기록은 최대 10080분(7일)까지예요.", "err");

    const submit = $("#data-submit");
    submit.disabled = true;
    try {
      const saved = state.editingId
        ? await api.updateData(state.editingId, { date, value, memo })
        : await api.createData({ date, value, memo });
      const verb = state.editingId ? "수정" : "추가";
      resetForm();
      setFormMessage(`✓ ${prettyDate(saved.date)} 기록을 ${verb}했어요.`, "ok");
      state.selectedDate = saved.date;
      state.calMonth = saved.date.slice(0, 7);
      await afterDataChange(saved.id);
    } catch (e) {
      setFormMessage(e.message, "err");
    } finally {
      submit.disabled = false;
    }
  });

  $("#data-tbody").addEventListener("click", async (evt) => {
    const edit = evt.target.closest("[data-edit]");
    if (edit) return startEdit(edit.dataset.edit);
    const del = evt.target.closest("[data-delete]");
    if (!del) return;
    const row = state.data.find((d) => d.id === del.dataset.delete);
    if (!confirm(`${row ? prettyDate(row.date) : ""} 기록을 삭제할까요?`)) return;
    try {
      await api.deleteData(del.dataset.delete);
      if (state.editingId === del.dataset.delete) resetForm();
      setFormMessage(`✓ ${row ? prettyDate(row.date) : ""} 기록을 삭제했어요.`, "ok");
      await afterDataChange();
    } catch (e) { setFormMessage(e.message, "err"); }
  });

  $("#kind-tabs").addEventListener("click", (evt) => {
    const btn = evt.target.closest("[data-kind]");
    if (!btn) return;
    state.kind = btn.dataset.kind;
    document.querySelectorAll("#kind-tabs button").forEach((b) => {
      b.classList.toggle("active", b === btn);
      b.setAttribute("aria-selected", String(b === btn));
    });
    renderDataTable();
  });
  $("#data-month").addEventListener("change", () => renderDataTable());
  $("#export-csv").addEventListener("click", exportCSV);
  $("#export-json").addEventListener("click", exportJSON);
}

/* ================= 내보내기 ================= */
function download(filename, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function exportCSV() {
  const { rows } = filteredRows();
  if (!rows.length) return toast("내보낼 기록이 없어요");
  const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const lines = ["date,value_minutes,change_minutes,memo"].concat(rows.map((r) => [r.date, r.value, r.change ?? "", esc(r.memo)].join(",")));
  download(`time-debt-${todayISO()}.csv`, "﻿" + lines.join("\n"), "text/csv;charset=utf-8"); // BOM: 엑셀 한글
  toast(`CSV ${rows.length}건을 내려받았어요`);
}
function exportJSON() {
  const { rows } = filteredRows();
  if (!rows.length) return toast("내보낼 기록이 없어요");
  const payload = {
    exported_at: new Date().toISOString(),
    unit: "minutes",
    filter: { month: $("#data-month").value, kind: state.kind },
    summary: state.summary,
    records: rows.map(({ date, value, change, memo }) => ({ date, value, change, memo })),
  };
  download(`time-debt-${todayISO()}.json`, JSON.stringify(payload, null, 2), "application/json");
  toast(`JSON ${rows.length}건을 내려받았어요`);
}

/* ================= 인사이트 ================= */
async function loadInsight() {
  if (!state.insightDirty && state.statistics) return renderInsightCharts();
  $("#line-chart").innerHTML = '<p class="empty">불러오는 중…</p>';
  try {
    state.statistics = await api.statistics();
    state.insightDirty = false;
    renderInsightCharts();
  } catch (e) {
    $("#line-chart").innerHTML = `<p class="empty">${escapeHtml(e.message)}</p>`;
  }
}

function renderInsightCharts() {
  const st = state.statistics;
  if (!st) return;
  const memoByDate = Object.fromEntries(state.data.map((d) => [d.date, d.memo]));
  const series = st.series.map((p) => ({ ...p, memo: memoByDate[p.date] }));
  const sliced = state.range === "all" ? series : series.slice(-Number(state.range));
  $("#line-legend").innerHTML = `
    <span class="legend-item"><i class="swatch" style="background:var(--series-1)"></i>그날 남은 외상</span>
    <span class="legend-item"><i class="swatch" style="background:repeating-linear-gradient(90deg,var(--series-2) 0 6px,transparent 6px 9px)"></i>7일 이동평균</span>`;
  renderLineChart($("#line-chart"), sliced);
  renderWeekdayChart($("#weekday-chart"), st.weekday, state.summary?.recommendation?.weekday);
  $("#monthly-tbody").innerHTML = st.monthly
    .slice()
    .reverse()
    .map((mo) => `<tr>
        <td class="mono">${mo.month}</td>
        <td class="num">${fmtMinutes(mo.average)}</td>
        <td class="num">${fmtMinutes(mo.max)}</td>
        <td class="num ${mo.net_change > 0 ? "up" : mo.net_change < 0 ? "down" : ""}">${signed(mo.net_change)}</td>
      </tr>`)
    .join("");
}

function initInsight() {
  $("#range-tabs").addEventListener("click", (evt) => {
    const btn = evt.target.closest("[data-range]");
    if (!btn) return;
    document.querySelectorAll("#range-tabs button").forEach((b) => b.classList.toggle("active", b === btn));
    state.range = btn.dataset.range;
    renderInsightCharts();
  });
  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (!$("#panel-insight").hidden) renderInsightCharts(); }, 150);
  });
}

/* ================= 시작 ================= */
async function main() {
  $("#docs-link").href = `${API_BASE_URL}/docs`;
  initTheme();
  initCalendar();
  initChat();
  initConversations();
  initLedger();
  initInsight();
  initTasks({
    toast,
    today: todayISO,
    // 할 일이 바뀌면 오늘 외상이 자동 재계산되므로 요약·장부·캘린더를 새로고침
    onDebtChange: async () => {
      state.insightDirty = true;
      await Promise.all([loadSummary(), loadData()]);
      renderCalendar();
    },
  });
  newChat();
  initTabs();

  if (!(await wakeServer())) return;
  await Promise.all([loadSummary(), loadConversations(), loadData(), loadTasks()]);
  renderCalendar(); // 요약(추천일) 도착 후 다시 그림
  if (!state.conversationId && $("#messages .welcome")) newChat(); // 장부 데이터를 반영한 인사
  if (!$("#panel-insight").hidden) loadInsight();
}

main();
