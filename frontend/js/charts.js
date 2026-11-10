// 의존성 없는 SVG 차트 (꺾은선 + 양방향 막대)
const NS = "http://www.w3.org/2000/svg";
const tooltip = () => document.getElementById("tooltip");

function el(tag, attrs = {}, parent) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}

function niceMax(value) {
  if (value <= 0) return 60;
  const step = value > 600 ? 120 : 60; // 1~2시간 단위 눈금
  return Math.ceil((value * 1.08) / step) * step;
}

export function fmtMinutes(min) {
  if (min === null || min === undefined || Number.isNaN(min)) return "-";
  const sign = min < 0 ? "-" : "";
  const m = Math.round(Math.abs(min));
  const h = Math.floor(m / 60);
  const r = m % 60;
  if (h && r) return `${sign}${h}시간 ${r}분`;
  if (h) return `${sign}${h}시간`;
  return `${sign}${r}분`;
}

function showTooltip(html, clientX, clientY) {
  const tip = tooltip();
  tip.innerHTML = html;
  tip.hidden = false;
  const { width, height } = tip.getBoundingClientRect();
  let x = clientX + 14;
  let y = clientY - height - 12;
  if (x + width > window.innerWidth - 8) x = clientX - width - 14;
  if (y < 8) y = clientY + 16;
  tip.style.left = `${Math.max(8, x)}px`;
  tip.style.top = `${y}px`;
}
const hideTooltip = () => (tooltip().hidden = true);

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

/**
 * 시간 외상 꺾은선 차트: 일별 값 + 7일 이동평균 (단일 y축).
 * points: [{date, value, moving_average_7, change, memo?}]
 */
export function renderLineChart(container, points) {
  container.innerHTML = "";
  if (!points.length) {
    container.innerHTML = '<p class="empty">표시할 데이터가 없어요.</p>';
    return;
  }
  const width = Math.max(container.clientWidth, 280);
  const height = width < 520 ? 220 : 280;
  const m = { top: 12, right: width < 520 ? 12 : 64, bottom: 28, left: 44 };
  const iw = width - m.left - m.right;
  const ih = height - m.top - m.bottom;

  const maxY = niceMax(Math.max(...points.map((p) => Math.max(p.value, p.moving_average_7))));
  const x = (i) => m.left + (points.length === 1 ? iw / 2 : (i / (points.length - 1)) * iw);
  const y = (v) => m.top + ih - (v / maxY) * ih;

  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, height, role: "img", "aria-label": "외상 장부 흐름 꺾은선 차트" }, container);

  // 가로 눈금 (시간 단위)
  const axis = el("g", { class: "axis" }, svg);
  const ticks = 4;
  for (let t = 0; t <= ticks; t++) {
    const v = (maxY / ticks) * t;
    const yy = y(v);
    el("line", { x1: m.left, x2: m.left + iw, y1: yy, y2: yy, class: t === 0 ? "baseline" : "gridline" }, svg);
    const label = el("text", { x: m.left - 8, y: yy + 4, "text-anchor": "end" }, axis);
    label.textContent = v >= 60 ? `${Math.round(v / 60)}h` : `${Math.round(v)}m`;
  }

  // 월 경계 라벨
  let lastMonth = "";
  const minGap = 46;
  let lastX = -Infinity;
  points.forEach((p, i) => {
    const month = p.date.slice(0, 7);
    if (month !== lastMonth) {
      lastMonth = month;
      const xx = x(i);
      if (xx - lastX >= minGap) {
        const t = el("text", { x: xx, y: height - 8, "text-anchor": i === 0 ? "start" : "middle" }, axis);
        t.textContent = `${Number(p.date.slice(5, 7))}월`;
        lastX = xx;
      }
    }
  });

  const pathFor = (key) => points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`).join("");
  el("path", { d: pathFor("value"), fill: "none", stroke: "var(--series-1)", "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
  el("path", { d: pathFor("moving_average_7"), fill: "none", stroke: "var(--series-2)", "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round", "stroke-dasharray": "6 4" }, svg);

  // 끝점 직접 라벨 (넓은 화면)
  const last = points[points.length - 1];
  if (m.right > 40) {
    const lv = y(last.value);
    const la = y(last.moving_average_7);
    const apart = Math.abs(lv - la) < 14 ? (lv < la ? -7 : 7) : 0;
    el("text", { x: x(points.length - 1) + 8, y: lv + 4 - apart, class: "end-label" }, svg).textContent = "일별";
    el("text", { x: x(points.length - 1) + 8, y: la + 4 + apart, class: "end-label" }, svg).textContent = "7일 평균";
  }
  el("circle", { cx: x(points.length - 1), cy: y(last.value), r: 4, fill: "var(--series-1)", stroke: "var(--surface)", "stroke-width": 2 }, svg);

  // 호버 레이어: 크로스헤어 + 툴팁
  const cross = el("line", { y1: m.top, y2: m.top + ih, class: "crosshair", visibility: "hidden" }, svg);
  const dotV = el("circle", { r: 5, fill: "var(--series-1)", stroke: "var(--surface)", "stroke-width": 2, visibility: "hidden" }, svg);
  const dotA = el("circle", { r: 4, fill: "var(--series-2)", stroke: "var(--surface)", "stroke-width": 2, visibility: "hidden" }, svg);
  const hit = el("rect", { x: m.left, y: 0, width: iw, height: m.top + ih, class: "hit" }, svg);

  const onMove = (evt) => {
    const rect = svg.getBoundingClientRect();
    const px = ((evt.clientX - rect.left) / rect.width) * width;
    const i = Math.max(0, Math.min(points.length - 1, Math.round(((px - m.left) / iw) * (points.length - 1))));
    const p = points[i];
    const xx = x(i);
    for (const n of [cross, dotV, dotA]) n.setAttribute("visibility", "visible");
    cross.setAttribute("x1", xx);
    cross.setAttribute("x2", xx);
    dotV.setAttribute("cx", xx); dotV.setAttribute("cy", y(p.value));
    dotA.setAttribute("cx", xx); dotA.setAttribute("cy", y(p.moving_average_7));
    const change = p.change === null || p.change === undefined ? "" :
      `<div class="tt-row"><span>전일 대비</span><b class="mono">${p.change > 0 ? "+" : ""}${fmtMinutes(p.change)}</b></div>`;
    showTooltip(
      `<div class="tt-title">${p.date}</div>
       <div class="tt-row"><span><i class="swatch" style="background:var(--series-1)"></i>남은 외상</span><b class="mono">${fmtMinutes(p.value)}</b></div>
       <div class="tt-row"><span><i class="swatch" style="background:var(--series-2)"></i>7일 평균</span><b class="mono">${fmtMinutes(p.moving_average_7)}</b></div>
       ${change}
       ${p.memo ? `<div class="tt-memo">${escapeHtml(p.memo)}</div>` : ""}`,
      evt.clientX, evt.clientY,
    );
  };
  const onLeave = () => {
    for (const n of [cross, dotV, dotA]) n.setAttribute("visibility", "hidden");
    hideTooltip();
  };
  hit.addEventListener("pointermove", onMove);
  hit.addEventListener("pointerdown", onMove);
  hit.addEventListener("pointerleave", onLeave);
}

/**
 * 요일별 평균 증감 양방향 막대 (0 기준선, 위=외상 단 요일 / 아래=외상 갚은 요일).
 * items: [{weekday, average_change, average_debt, count}]
 */
export function renderWeekdayChart(container, items, recommended) {
  container.innerHTML = "";
  const rows = items.filter((d) => d.average_change !== null);
  if (!rows.length) {
    container.innerHTML = '<p class="empty">표시할 데이터가 없어요.</p>';
    return;
  }
  const width = Math.max(container.clientWidth, 260);
  const height = 240;
  const m = { top: 22, right: 8, bottom: 30, left: 8 };
  const iw = width - m.left - m.right;
  const ih = height - m.top - m.bottom;
  const maxAbs = Math.max(...rows.map((d) => Math.abs(d.average_change)), 10) * 1.1;
  const y = (v) => m.top + ih / 2 - (v / maxAbs) * (ih / 2);
  const band = iw / items.length;
  const barW = Math.min(36, band * 0.56);

  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, height, role: "img", "aria-label": "요일별 평균 증감 막대 차트" }, container);
  el("line", { x1: m.left, x2: m.left + iw, y1: y(0), y2: y(0), class: "baseline" }, svg);

  items.forEach((d, i) => {
    const cx = m.left + band * i + band / 2;
    const axisLabel = el("text", { x: cx, y: height - 8, "text-anchor": "middle", class: "bar-label" }, svg);
    axisLabel.textContent = d.weekday + (d.weekday === recommended ? " ★" : "");
    if (d.average_change === null) return;

    const v = d.average_change;
    const y0 = y(0);
    const y1 = y(v);
    const h = Math.max(Math.abs(y1 - y0), 1);
    const top = Math.min(y0, y1);
    const r = Math.min(4, h / 2, barW / 2);
    // 데이터 끝만 둥글게 (기준선 쪽은 각지게)
    const up = v >= 0;
    const x0 = cx - barW / 2;
    const path = up
      ? `M${x0},${y0} V${top + r} Q${x0},${top} ${x0 + r},${top} H${x0 + barW - r} Q${x0 + barW},${top} ${x0 + barW},${top + r} V${y0} Z`
      : `M${x0},${y0} V${top + h - r} Q${x0},${top + h} ${x0 + r},${top + h} H${x0 + barW - r} Q${x0 + barW},${top + h} ${x0 + barW},${top + h - r} V${y0} Z`;
    el("path", { d: path, fill: up ? "var(--diverge-pos)" : "var(--diverge-neg)" }, svg);

    const lbl = el("text", { x: cx, y: up ? top - 6 : top + h + 14, "text-anchor": "middle", class: "bar-label" }, svg);
    lbl.textContent = `${v > 0 ? "+" : ""}${Math.round(v)}`;

    const hit = el("rect", { x: cx - band / 2, y: m.top - 16, width: band, height: ih + 16, class: "hit" }, svg);
    const show = (evt) =>
      showTooltip(
        `<div class="tt-title">${d.weekday}요일${d.weekday === recommended ? " · 갚기 좋은 날" : ""}</div>
         <div class="tt-row"><span>평균 외상 변화</span><b class="mono">${v > 0 ? "+" : ""}${fmtMinutes(v)}</b></div>
         <div class="tt-row"><span>평균 외상</span><b class="mono">${fmtMinutes(d.average_debt)}</b></div>
         <div class="tt-row"><span>기록 수</span><b class="mono">${d.count}일</b></div>`,
        evt.clientX, evt.clientY,
      );
    hit.addEventListener("pointermove", show);
    hit.addEventListener("pointerdown", show);
    hit.addEventListener("pointerleave", hideTooltip);
  });
}
