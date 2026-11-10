// '오늘 할 일' 패널: AI 예상 시간 → 선택 → 추가, 완료 체크(실제 시간) → 남은 일 합계가 오늘의 부채
import { api } from "./api.js";
import { fmtMinutes } from "./charts.js";

const $ = (sel) => document.querySelector(sel);
const escapeHtml = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const state = {
  open: [],
  done: [],
  estimate: null,     // {title, options, recommended, reason, history_used}
  chosen: null,       // 선택한 분
  completingId: null, // 실제 시간 입력 중인 업무
  busy: false,
};
let ctx = { onDebtChange: async () => {}, toast: () => {}, today: () => "" };

/* ---------- 데이터 ---------- */
async function load() {
  try {
    const [open, done] = await Promise.all([api.listTasks("open"), api.listTasks("done", 50)]);
    state.open = open;
    state.done = done;
  } catch (e) {
    $("#open-tasks").innerHTML = `<li class="empty">${escapeHtml(e.message)}</li>`;
    return;
  }
  render();
}

async function mutate(promise, message) {
  if (state.busy) return;
  state.busy = true;
  try {
    const res = await promise;
    if (message) ctx.toast(message);
    await load();
    renderDebt(res.today_debt?.value);
    await ctx.onDebtChange();
  } catch (e) {
    ctx.toast(e.message);
  } finally {
    state.busy = false;
  }
}

/* ---------- 렌더 ---------- */
function render() {
  const today = ctx.today();
  const doneToday = state.done.filter((t) => t.done_date === today);
  $("#open-count").textContent = `${state.open.length}개`;
  $("#done-count").textContent = `${doneToday.length}개`;

  $("#open-tasks").innerHTML = state.open.length
    ? state.open.map(openItem).join("")
    : '<li class="empty">외상 제로! 몰래 사장이 살짝 섭섭해해요 🎉</li>';
  $("#done-tasks").innerHTML = doneToday.length
    ? doneToday.map(doneItem).join("")
    : '<li class="empty">아직 오늘 끝낸 일이 없어요.</li>';

  renderDebt();
  renderAccuracy();
}

function openItem(t) {
  const completing = state.completingId === t.id;
  const age = t.created_date < ctx.today() ? `<span class="task-age" title="${t.created_date}부터 밀린 일">밀린 지 ${daysBetween(t.created_date, ctx.today())}일</span>` : "";
  return `<li class="task ${completing ? "completing" : ""}" data-id="${escapeHtml(t.id)}">
    <label class="check"><input type="checkbox" data-check="${escapeHtml(t.id)}" ${completing ? "checked" : ""} aria-label="${escapeHtml(t.title)} 완료" /><span></span></label>
    <span class="task-title">${escapeHtml(t.title)} ${age}</span>
    <button class="task-est" type="button" data-est="${escapeHtml(t.id)}" title="예상 시간 수정">${fmtMinutes(t.estimated_minutes)}</button>
    <button class="btn-link danger" type="button" data-remove="${escapeHtml(t.id)}" aria-label="삭제" title="삭제">✕</button>
    ${completing ? `
      <form class="complete-row" data-complete="${escapeHtml(t.id)}">
        <span>실제로 걸린 시간</span>
        <input type="number" min="0" max="1440" step="5" value="${t.estimated_minutes}" aria-label="실제 걸린 시간(분)" required />
        <span>분</span>
        <button class="btn btn-primary btn-small" type="submit">완료</button>
        <button class="btn-link" type="button" data-cancel-complete>취소</button>
      </form>` : ""}
  </li>`;
}

function doneItem(t) {
  const diff = (t.actual_minutes ?? 0) - t.estimated_minutes;
  const diffText = diff === 0 ? "예상대로" : `${diff > 0 ? "+" : ""}${fmtMinutes(diff)}`;
  return `<li class="task done-item" data-id="${escapeHtml(t.id)}">
    <span class="check checked" aria-hidden="true"><span></span></span>
    <span class="task-title">${escapeHtml(t.title)}</span>
    <span class="task-actual">예상 ${fmtMinutes(t.estimated_minutes)} → 실제 ${fmtMinutes(t.actual_minutes ?? 0)} <b class="${diff > 0 ? "up" : diff < 0 ? "down" : ""}">${diffText}</b></span>
    <button class="btn-link" type="button" data-reopen="${escapeHtml(t.id)}">되돌리기</button>
  </li>`;
}

function renderDebt(value) {
  const total = value ?? state.open.reduce((acc, t) => acc + t.estimated_minutes, 0);
  $("#today-debt").textContent = fmtMinutes(total);
  $("#today-debt-sub").textContent = state.open.length
    ? `남은 일 ${state.open.length}개의 예상 시간을 더했어요`
    : "남은 일이 없어요";
  const bar = $("#debt-bar");
  bar.innerHTML = state.open
    .map((t) => `<i style="flex:${t.estimated_minutes}" title="${escapeHtml(t.title)} · ${fmtMinutes(t.estimated_minutes)}"></i>`)
    .join("");
  bar.hidden = !state.open.length;
}

function renderAccuracy() {
  const box = $("#accuracy-box");
  const rows = state.done.filter((t) => t.actual_minutes !== null && t.actual_minutes !== undefined && t.estimated_minutes > 0);
  if (rows.length < 3) {
    box.innerHTML = '<p class="eyebrow">내 예측 습관</p><p class="small muted">완료 기록이 3개 이상 쌓이면 내가 시간을 얼마나 정확히 예측하는지 알려드려요.</p>';
    return;
  }
  const est = rows.reduce((a, t) => a + t.estimated_minutes, 0);
  const act = rows.reduce((a, t) => a + t.actual_minutes, 0);
  const pct = Math.round((act / est - 1) * 100);
  const msg = Math.abs(pct) < 5
    ? "예상과 실제가 거의 같아요. 정확한 편이에요!"
    : pct > 0
      ? `실제로는 예상보다 평균 <b class="up">${pct}%</b> 더 걸려요.`
      : `실제로는 예상보다 평균 <b class="down">${-pct}%</b> 덜 걸려요.`;
  box.innerHTML = `
    <p class="eyebrow">내 예측 습관</p>
    <p class="accuracy-msg">${msg}</p>
    <p class="small muted">최근 완료 ${rows.length}건 기준 · AI가 이 경향을 반영해서 예상 시간을 제안해요</p>`;
}

function daysBetween(a, b) {
  return Math.round((new Date(b) - new Date(a)) / 86400000);
}

/* ---------- AI 예상 ---------- */
function renderEstimate({ loading = false, error = "" } = {}) {
  const box = $("#estimate-box");
  box.hidden = false;
  const title = escapeHtml(state.estimate?.title ?? $("#task-title").value.trim());
  if (loading) {
    box.innerHTML = `<p class="typing"><span class="dots"><i></i><i></i><i></i></span> 몰래 사장이 ‘${title}’ 외상값을 셈해보는 중…</p>`;
    return;
  }
  const est = state.estimate;
  const options = est
    ? est.options
        .map((o) => `<button type="button" class="opt ${state.chosen === o.minutes ? "active" : ""}" data-minutes="${o.minutes}">
            <span class="opt-label">${escapeHtml(o.label)}</span><span class="opt-value">${fmtMinutes(o.minutes)}</span></button>`)
        .join("")
    : "";
  box.innerHTML = `
    <p class="estimate-title"><b>${title}</b> 예상 소요 시간</p>
    ${error ? `<p class="form-msg err">${escapeHtml(error)}</p>` : ""}
    ${est ? `<p class="merchant-say"><img src="assets/mollae.svg" alt="몰래 사장" /><span>${escapeHtml(est.reason)}${est.history_used ? `<em> · 손님 완료 기록 ${est.history_used}건 참고</em>` : ""}</span></p>` : ""}
    <div class="opts">${options}
      <label class="opt opt-custom ${est && !est.options.some((o) => o.minutes === state.chosen) ? "active" : ""}">
        <span class="opt-label">직접 입력</span>
        <span class="opt-value"><input type="number" id="custom-minutes" min="1" max="1440" step="5" value="${state.chosen ?? ""}" placeholder="분" aria-label="직접 입력(분)" />분</span>
      </label>
    </div>
    <div class="row">
      <button type="button" class="btn btn-primary" id="add-task">부채에 추가${state.chosen ? ` · ${fmtMinutes(state.chosen)}` : ""}</button>
      <button type="button" class="btn-link" id="cancel-estimate">취소</button>
    </div>`;
}

async function requestEstimate(title) {
  state.estimate = { title, options: [], recommended: null, reason: "", history_used: 0 };
  state.chosen = null;
  renderEstimate({ loading: true });
  $("#task-estimate").disabled = true;
  try {
    state.estimate = await api.estimateTask(title);
    state.chosen = state.estimate.recommended;
    renderEstimate();
  } catch (e) {
    state.estimate = null;
    state.chosen = null;
    renderEstimate({ error: `${e.message} 아래에 직접 입력할 수 있어요.` });
  } finally {
    $("#task-estimate").disabled = false;
  }
}

function closeEstimate() {
  state.estimate = null;
  state.chosen = null;
  $("#estimate-box").hidden = true;
  $("#task-title").value = "";
}

async function addTask() {
  const title = state.estimate?.title || $("#task-title").value.trim();
  const minutes = Number(state.chosen);
  if (!title) return ctx.toast("할 일을 입력하세요");
  if (!minutes || minutes < 1 || minutes > 1440) return ctx.toast("예상 시간을 1~1440분 사이로 정해주세요");
  const aiEstimate = state.estimate?.options?.length
    ? { options: state.estimate.options, recommended: state.estimate.recommended, reason: state.estimate.reason }
    : null;
  closeEstimate();
  await mutate(api.createTask({ title, estimated_minutes: minutes, ai_estimate: aiEstimate }), `‘${title}’ ${fmtMinutes(minutes)} 외상 장부에 올렸어~`);
  $("#task-title").focus();
}

/* ---------- 이벤트 ---------- */
export function initTasks(context) {
  ctx = { ...ctx, ...context };

  $("#task-form").addEventListener("submit", (evt) => {
    evt.preventDefault();
    const title = $("#task-title").value.trim();
    if (title) requestEstimate(title);
  });

  $("#estimate-box").addEventListener("click", (evt) => {
    const opt = evt.target.closest("button.opt");
    if (opt) {
      state.chosen = Number(opt.dataset.minutes);
      renderEstimate();
      return;
    }
    if (evt.target.closest("#add-task")) addTask();
    if (evt.target.closest("#cancel-estimate")) closeEstimate();
  });
  $("#estimate-box").addEventListener("input", (evt) => {
    if (evt.target.id !== "custom-minutes") return;
    state.chosen = Number(evt.target.value) || null;
    document.querySelectorAll("#estimate-box .opt").forEach((o) => o.classList.toggle("active", o.classList.contains("opt-custom")));
    const add = $("#add-task");
    add.textContent = `부채에 추가${state.chosen ? ` · ${fmtMinutes(state.chosen)}` : ""}`;
  });
  $("#estimate-box").addEventListener("keydown", (evt) => {
    if (evt.target.id === "custom-minutes" && evt.key === "Enter") { evt.preventDefault(); addTask(); }
  });

  $("#open-tasks").addEventListener("change", (evt) => {
    const check = evt.target.closest("[data-check]");
    if (!check) return;
    state.completingId = check.checked ? check.dataset.check : null;
    render();
    $(".complete-row input")?.select();
  });
  $("#open-tasks").addEventListener("click", async (evt) => {
    if (evt.target.closest("[data-cancel-complete]")) { state.completingId = null; render(); return; }
    const remove = evt.target.closest("[data-remove]");
    if (remove) {
      const t = state.open.find((x) => x.id === remove.dataset.remove);
      if (confirm(`‘${t?.title}’을(를) 목록에서 지울까요? (완료가 아니라 삭제예요)`)) {
        await mutate(api.deleteTask(remove.dataset.remove), "삭제했어요");
      }
      return;
    }
    const est = evt.target.closest("[data-est]");
    if (est) {
      const t = state.open.find((x) => x.id === est.dataset.est);
      const input = prompt(`‘${t.title}’ 예상 시간(분)`, t.estimated_minutes);
      const minutes = Number(input);
      if (input !== null && minutes >= 1 && minutes <= 1440) {
        await mutate(api.updateTask(t.id, { estimated_minutes: minutes }), "예상 시간을 바꿨어요");
      }
    }
  });
  $("#open-tasks").addEventListener("submit", async (evt) => {
    const form = evt.target.closest("[data-complete]");
    if (!form) return;
    evt.preventDefault();
    const minutes = Number(form.querySelector("input").value);
    if (Number.isNaN(minutes) || minutes < 0 || minutes > 1440) return ctx.toast("실제 시간을 0~1440분으로 입력하세요");
    const t = state.open.find((x) => x.id === form.dataset.complete);
    state.completingId = null;
    await mutate(api.completeTask(form.dataset.complete, minutes), `‘${t?.title}’ 상환 완료! 외상 ${fmtMinutes(t?.estimated_minutes ?? 0)} 탕감~ 🪙`);
  });
  $("#done-tasks").addEventListener("click", async (evt) => {
    const reopen = evt.target.closest("[data-reopen]");
    if (reopen) await mutate(api.reopenTask(reopen.dataset.reopen), "다시 남은 일로 옮겼어요");
  });
}

export const loadTasks = load;
