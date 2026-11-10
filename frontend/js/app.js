import { api, API_BASE_URL } from "./api.js";
import { fmtMinutes, renderLineChart, renderWeekdayChart } from "./charts.js";

const $ = (sel) => document.querySelector(sel);
const state = {
  summary: null,
  statistics: null,
  data: [],
  conversations: [],
  conversationId: null,
  editingId: null,
  range: "90",
  sending: false,
  insightDirty: true,
};

/* ================= 공통 유틸 ================= */
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
// AI 답변의 **굵게** 정도만 허용하는 아주 작은 마크다운 렌더러
function renderRichText(text) {
  return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
}
function toast(message) {
  const t = $("#toast");
  t.textContent = message;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), 2600);
}
function todayISO() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}
function relativeTime(iso) {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "방금 전";
  if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}일 전`;
  return iso.slice(0, 10);
}
function signed(min) {
  if (min === null || min === undefined) return "-";
  return `${min > 0 ? "+" : ""}${fmtMinutes(min)}`;
}

/* ================= 테마 ================= */
function initTheme() {
  $("#theme-toggle").addEventListener("click", () => {
    const root = document.documentElement;
    const current = root.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    try { localStorage.setItem("tbm-theme", next); } catch (e) { /* 저장 불가 환경 무시 */ }
    if (!$("#panel-insight").hidden) renderInsightCharts();
  });
}

/* ================= 탭 ================= */
function initTabs() {
  const tabs = [...document.querySelectorAll(".tab")];
  const select = (tab) => {
    tabs.forEach((t) => {
      const on = t === tab;
      t.setAttribute("aria-selected", String(on));
      $(`#${t.getAttribute("aria-controls")}`).hidden = !on;
    });
    if (tab.id === "tab-insight") loadInsight();
    try { localStorage.setItem("tbm-tab", tab.id); } catch (e) { /* noop */ }
  };
  tabs.forEach((t) => t.addEventListener("click", () => select(t)));
  // 우선순위: URL 해시(#chat/#data/#insight) → 마지막으로 본 탭
  let saved = location.hash ? `tab-${location.hash.slice(1)}` : null;
  if (!saved) {
    try { saved = localStorage.getItem("tbm-tab"); } catch (e) { /* noop */ }
  }
  const initial = tabs.find((t) => t.id === saved);
  if (initial) select(initial);
}

/* ================= 서버 깨우기 (Render 무료 티어 콜드스타트) ================= */
async function wakeServer() {
  const status = $("#server-status");
  const banner = $("#server-banner");
  const started = Date.now();
  const tick = () => {
    const sec = Math.round((Date.now() - started) / 1000);
    banner.textContent = `☕ 서버를 깨우는 중이에요 (${sec}초). 무료 서버는 한동안 접속이 없으면 잠들어서 첫 접속에 최대 1분 정도 걸릴 수 있어요.`;
  };
  const showTimer = setTimeout(() => { banner.hidden = false; tick(); }, 2500);
  const ticker = setInterval(tick, 1000);
  try {
    while (Date.now() - started < 100000) {
      try {
        await api.health(15000);
        status.textContent = "서버 연결됨";
        status.className = "pill pill-ok";
        return true;
      } catch (e) {
        await new Promise((r) => setTimeout(r, 2000));
      }
    }
    status.textContent = "서버 연결 실패";
    status.className = "pill pill-bad";
    banner.hidden = false;
    banner.textContent = "⚠️ 서버에 연결하지 못했어요. 잠시 후 새로고침해 주세요.";
    return false;
  } finally {
    clearTimeout(showTimer);
    clearInterval(ticker);
    if (status.classList.contains("pill-ok")) banner.hidden = true;
  }
}

/* ================= 요약 카드 ================= */
async function loadSummary() {
  try {
    state.summary = await api.summary();
    renderSummary();
  } catch (e) {
    $("#summary-cards").innerHTML = `<div class="card"><div class="label">요약</div><div class="sub">${escapeHtml(e.message)}</div></div>`;
  }
}

function renderSummary() {
  const s = state.summary;
  const box = $("#summary-cards");
  if (!s || !s.count) {
    $("#summary-period").textContent = "";
    box.innerHTML = '<div class="card"><div class="label">데이터 없음</div><div class="sub">장부 관리 탭에서 첫 기록을 추가해 보세요.</div></div>';
    return;
  }
  const m = s.metrics;
  const t = s.trend;
  const rec = s.recommendation || {};
  const pay = s.payoff_forecast || {};
  const credit = s.credit || {};
  $("#summary-period").textContent = `${s.period.label} · ${s.count}건`;

  const trendClass = t.label === "증가" ? "trend-up" : t.label === "감소" ? "trend-down" : "";
  const arrow = t.label === "증가" ? "▲" : t.label === "감소" ? "▼" : "■";
  const payValue = pay.estimated_date
    ? `${pay.estimated_date.slice(5).replace("-", "/")}<small>${pay.days_left}일 후</small>`
    : `<span style="font-size:18px">${escapeHtml(pay.status || "-")}</span>`;

  box.innerHTML = `
    <div class="card hero">
      <div class="label">현재 시간 부채</div>
      <div class="value">${fmtMinutes(m.current)}</div>
      <div class="sub">${m.current_date} 마감 기준 · 평균 ${fmtMinutes(m.average)}</div>
    </div>
    <div class="card">
      <div class="label">최근 추세 (7일)</div>
      <div class="value ${trendClass}">${arrow} ${t.change_pct > 0 ? "+" : ""}${t.change_pct}%</div>
      <div class="sub">${escapeHtml(t.label)} · 직전 7일 평균 대비</div>
    </div>
    <div class="card">
      <div class="label">시간 신용등급</div>
      <div class="value"><span class="grade grade-${escapeHtml(credit.grade)}">${escapeHtml(credit.grade || "-")}</span></div>
      <div class="sub">${escapeHtml((credit.label || "").split(" — ")[0])} · 평균 대비 ${Math.round((credit.ratio_to_average || 0) * 100)}%</div>
    </div>
    <div class="card">
      <div class="label">추천 상환일</div>
      <div class="value">${escapeHtml(rec.weekday || "-")}<small>요일</small></div>
      <div class="sub">평균 ${signed(rec.average_change)} · ${escapeHtml(rec.avoid_weekday || "-")}요일 차입 주의</div>
    </div>
    <div class="card">
      <div class="label">완납 예상일</div>
      <div class="value">${payValue}</div>
      <div class="sub">${pay.daily_rate !== undefined ? `하루 평균 ${signed(pay.daily_rate)}` : escapeHtml(pay.status || "")}</div>
    </div>
    <div class="card">
      <div class="label">최대 부채</div>
      <div class="value">${fmtMinutes(m.max)}</div>
      <div class="sub">${m.max_date} · 최소 ${fmtMinutes(m.min)}</div>
    </div>`;
}

/* ================= 대화 기록 ================= */
async function loadConversations() {
  try {
    state.conversations = await api.listConversations();
  } catch (e) {
    state.conversations = [];
  }
  renderConversationList();
}

function renderConversationList() {
  const list = $("#conversation-list");
  if (!state.conversations.length) {
    list.innerHTML = '<li class="empty">아직 저장된 대화가 없어요.<br />질문하면 자동으로 저장돼요.</li>';
    return;
  }
  list.innerHTML = state.conversations
    .map(
      (c) => `
      <li class="conv-item ${c.id === state.conversationId ? "active" : ""}" data-id="${escapeHtml(c.id)}" tabindex="0" role="button" aria-label="${escapeHtml(c.title)} 불러오기">
        <span class="conv-title">${escapeHtml(c.title)}</span>
        <button class="conv-del" type="button" data-del="${escapeHtml(c.id)}" aria-label="대화 삭제" title="삭제">✕</button>
        <span class="conv-meta">${relativeTime(c.updated_at)} · 메시지 ${c.message_count}개</span>
      </li>`,
    )
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

function newChat() {
  state.conversationId = null;
  $("#chat-title").textContent = "새 대화";
  $("#quick-questions").hidden = false;
  $("#messages").innerHTML = `
    <div class="welcome">
      <p><b>시간 암시장 상담 창구</b>에 오신 걸 환영해요.</p>
      <p class="small">위 요약 카드의 데이터가 AI에게 그대로 전달돼요.<br/>필요하면 AI가 날짜별 기록·요일별 통계·이전 대화를 직접 조회해서 답해요.</p>
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
  get_data_summary: "요약 재조회",
  get_statistics: "통계 조회",
  get_records: "기간 기록 조회",
  list_conversations: "대화 목록 조회",
  get_conversation: "이전 대화 조회",
};

function appendMessage(role, content, tools = [], { error = false } = {}) {
  const box = $("#messages");
  box.querySelector(".welcome")?.remove();
  const div = document.createElement("div");
  div.className = `msg ${role}${error ? " error" : ""}`;
  div.innerHTML = renderRichText(content);
  if (tools && tools.length) {
    const t = document.createElement("div");
    t.className = "tools";
    t.innerHTML = tools
      .map((tool) => {
        const name = typeof tool === "string" ? tool : tool.name;
        const args = typeof tool === "object" && tool.arguments && Object.keys(tool.arguments).length
          ? ` ${Object.values(tool.arguments).join(" ~ ")}` : "";
        return `<span class="tool-badge" title="AI가 호출한 도구: ${escapeHtml(name)}">🔧 ${escapeHtml(TOOL_LABELS[name] || name)}${escapeHtml(args)}</span>`;
      })
      .join("");
    div.appendChild(t);
  }
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  return div;
}

function showTyping() {
  const box = $("#messages");
  const div = document.createElement("div");
  div.className = "msg assistant";
  div.innerHTML = '<span class="typing"><span class="dots"><i></i><i></i><i></i></span><span class="typing-text">AI가 장부를 분석하는 중…</span></span>';
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  const started = Date.now();
  const timer = setInterval(() => {
    const sec = Math.round((Date.now() - started) / 1000);
    const text = sec > 20 ? `조금만 더 기다려 주세요… ${sec}초` : `AI가 장부를 분석하는 중… ${sec}초`;
    div.querySelector(".typing-text").textContent = text;
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
    if (res.summary) { state.summary = res.summary; renderSummary(); }
    await loadConversations();
    if (isNew) toast("대화가 자동 저장됐어요");
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
  $("#chat-form").addEventListener("submit", (evt) => {
    evt.preventDefault();
    sendMessage($("#chat-input").value);
  });
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

/* ================= 장부(데이터) 관리 ================= */
async function loadData() {
  try {
    state.data = await api.listData();
    renderMonthFilter();
    renderDataTable();
  } catch (e) {
    $("#data-tbody").innerHTML = `<tr><td colspan="5" class="empty">${escapeHtml(e.message)}</td></tr>`;
  }
}

function withChanges(rows) {
  return rows.map((r, i) => ({ ...r, change: i ? r.value - rows[i - 1].value : null }));
}

function renderMonthFilter() {
  const select = $("#data-month");
  const current = select.value || "all";
  const months = [...new Set(state.data.map((d) => d.date.slice(0, 7)))].reverse();
  select.innerHTML = `<option value="all">전체 기간</option>${months.map((mo) => `<option value="${mo}">${mo}</option>`).join("")}`;
  select.value = months.includes(current) ? current : "all";
}

function renderDataTable(flashId) {
  const month = $("#data-month").value || "all";
  const rows = withChanges(state.data)
    .filter((r) => month === "all" || r.date.startsWith(month))
    .reverse();
  $("#data-count").textContent = `${rows.length}건${month === "all" ? "" : ` / 전체 ${state.data.length}건`}`;
  const tbody = $("#data-tbody");
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty">기록이 없어요.</td></tr>';
    return;
  }
  tbody.innerHTML = rows
    .map((r) => {
      const deltaClass = r.change > 0 ? "delta-up" : r.change < 0 ? "delta-down" : "";
      return `<tr data-id="${escapeHtml(r.id)}" class="${r.id === flashId ? "flash" : ""}">
        <td class="mono">${r.date}</td>
        <td class="num">${fmtMinutes(r.value)}</td>
        <td class="num ${deltaClass}">${r.change === null ? "-" : signed(r.change)}</td>
        <td class="memo">${escapeHtml(r.memo)}</td>
        <td class="actions-col"><div class="row">
          <button class="btn btn-small" type="button" data-edit="${escapeHtml(r.id)}">수정</button>
          <button class="btn btn-small btn-danger" type="button" data-delete="${escapeHtml(r.id)}">삭제</button>
        </div></td>
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
  $("#data-form-title").textContent = "새 기록 추가";
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
  $("#data-form-title").textContent = `${row.date} 기록 수정`;
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
  renderDataTable(flashId);
  if (!$("#panel-insight").hidden) loadInsight();
}

function initDataForm() {
  $("#f-date").max = todayISO();
  resetForm();
  $("#f-value").addEventListener("input", (e) => {
    const v = Number(e.target.value);
    $("#f-value-hint").textContent = e.target.value === "" ? "" : `= ${fmtMinutes(v)}`;
  });
  $("#data-cancel").addEventListener("click", () => { resetForm(); setFormMessage(""); });

  $("#data-form").addEventListener("submit", async (evt) => {
    evt.preventDefault();
    const date = $("#f-date").value;
    const valueRaw = $("#f-value").value;
    const value = Number(valueRaw);
    const memo = $("#f-memo").value.trim();
    // 클라이언트 1차 검증 (서버 Pydantic이 최종 검증)
    if (!date) return setFormMessage("날짜를 선택하세요.", "err");
    if (date > todayISO()) return setFormMessage("미래 날짜는 기록할 수 없어요.", "err");
    if (valueRaw === "" || Number.isNaN(value) || value < 0) return setFormMessage("시간 부채는 0 이상의 숫자(분)로 입력하세요.", "err");
    if (value > 10080) return setFormMessage("하루 기록은 최대 10080분(7일)까지예요.", "err");

    const submit = $("#data-submit");
    submit.disabled = true;
    try {
      if (state.editingId) {
        const updated = await api.updateData(state.editingId, { date, value, memo });
        resetForm();
        setFormMessage(`✓ ${updated.date} 기록을 수정했어요.`, "ok");
        await afterDataChange(updated.id);
      } else {
        const created = await api.createData({ date, value, memo });
        resetForm();
        setFormMessage(`✓ ${created.date} 기록을 추가했어요.`, "ok");
        await afterDataChange(created.id);
      }
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
    if (del) {
      const row = state.data.find((d) => d.id === del.dataset.delete);
      if (!confirm(`${row?.date ?? ""} 기록을 삭제할까요?`)) return;
      try {
        await api.deleteData(del.dataset.delete);
        if (state.editingId === del.dataset.delete) resetForm();
        setFormMessage(`✓ ${row?.date ?? ""} 기록을 삭제했어요.`, "ok");
        await afterDataChange();
      } catch (e) { setFormMessage(e.message, "err"); }
    }
  });
  $("#data-month").addEventListener("change", () => renderDataTable());
  $("#export-csv").addEventListener("click", exportCSV);
  $("#export-json").addEventListener("click", exportJSON);
}

/* ================= 내보내기 ================= */
function download(filename, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function exportRows() {
  const month = $("#data-month").value || "all";
  return withChanges(state.data).filter((r) => month === "all" || r.date.startsWith(month));
}
function exportCSV() {
  const rows = exportRows();
  if (!rows.length) return toast("내보낼 기록이 없어요");
  const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const lines = [["date", "value_minutes", "change_minutes", "memo"].join(",")]
    .concat(rows.map((r) => [r.date, r.value, r.change ?? "", esc(r.memo)].join(",")));
  // BOM: 엑셀에서 한글이 깨지지 않도록
  download(`time-debt-${todayISO()}.csv`, "﻿" + lines.join("\n"), "text/csv;charset=utf-8");
  toast(`CSV ${rows.length}건을 내려받았어요`);
}
function exportJSON() {
  const rows = exportRows();
  if (!rows.length) return toast("내보낼 기록이 없어요");
  const payload = {
    exported_at: new Date().toISOString(),
    unit: "minutes",
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
    <span class="legend-item"><i class="swatch" style="background:var(--series-1)"></i>일별 마감 부채</span>
    <span class="legend-item"><i class="swatch" style="background:repeating-linear-gradient(90deg,var(--series-2) 0 6px,transparent 6px 9px)"></i>7일 이동평균</span>`;
  renderLineChart($("#line-chart"), sliced);
  renderWeekdayChart($("#weekday-chart"), st.weekday, state.summary?.recommendation?.weekday);

  $("#stat-stdev").textContent = st.stdev ?? "-";
  $("#monthly-tbody").innerHTML = st.monthly
    .slice()
    .reverse()
    .map((mo) => `<tr>
        <td class="mono">${mo.month}</td>
        <td class="num">${mo.count}</td>
        <td class="num">${fmtMinutes(mo.average)}</td>
        <td class="num">${fmtMinutes(mo.max)}</td>
        <td class="num">${fmtMinutes(mo.min)}</td>
        <td class="num ${mo.net_change > 0 ? "delta-up" : mo.net_change < 0 ? "delta-down" : ""}">${signed(mo.net_change)}</td>
      </tr>`)
    .join("");
}

function initInsight() {
  document.querySelectorAll(".segmented button").forEach((btn) =>
    btn.addEventListener("click", () => {
      document.querySelectorAll(".segmented button").forEach((b) => b.classList.toggle("active", b === btn));
      state.range = btn.dataset.range;
      renderInsightCharts();
    }),
  );
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
  initChat();
  initConversations();
  initDataForm();
  initInsight();
  newChat();
  initTabs();

  const ok = await wakeServer();
  if (!ok) return;
  await Promise.all([loadSummary(), loadConversations(), loadData()]);
  if (!$("#panel-insight").hidden) loadInsight();
}

main();
