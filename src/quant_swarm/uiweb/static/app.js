/* Quant$warm SPA — snapshot polling + per-page renderers. */
"use strict";

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
let SNAP = null;
let PENDING = false;          // waiting for an expert reply
let pendingBase = 0;          // expert msg count when the send happened
let filesCache = null;
let prevMsgCount = 0;         // chat rows already on screen (for entry animation)
const kpiPrev = {};           // last rendered KPI values (count-up source)

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmtT = (ts) => ts ? new Date(ts).toLocaleTimeString("zh-CN", { hour12: false }) : "-";
const num = (n, d = 2) => (n === null || n === undefined) ? "" :
  Number(n).toLocaleString("zh-CN", { maximumFractionDigits: d });

marked.setOptions({ gfm: true, breaks: true });
function md(src) {
  const html = DOMPurify.sanitize(marked.parse(src || ""));
  const tpl = document.createElement("template");
  tpl.innerHTML = html;
  tpl.content.querySelectorAll("table").forEach((t) =>
    t.classList.add("table", "table-sm", "table-bordered"));
  return tpl.innerHTML;
}

/* ── nav ── */
function showPage(name) {
  const b = $(`.nav[data-page="${name}"]`) || $(".nav");
  $$(".nav").forEach((x) => x.classList.toggle("on", x === b));
  $$(".page").forEach((p) => p.classList.toggle("on", p.id === "page-" + b.dataset.page));
  if (b.dataset.page === "learning") loadFiles();
}
$$(".nav").forEach((b) => b.addEventListener("click", () => {
  location.hash = b.dataset.page;
  showPage(b.dataset.page);
}));
if (location.hash) showPage(location.hash.slice(1));

/* ── chat ── */
const EXPERT_CLASS = { investor: "c-investor", quant: "c-quant", system: "dim" };
const AV_LETTER = { investor: "投", quant: "量", system: "S" };
const expertMsgs = () => (SNAP?.chat || []).filter((m) => m.role === "expert");

function renderChat() {
  const list = $("#chat-list");
  const msgs = SNAP.chat || [];
  const unchanged = msgs.length === prevMsgCount && !PENDING && !list.dataset.pending;
  if (unchanged && prevMsgCount > 0) return;
  let html = msgs.map((m, i) => {
    const user = m.role === "user";
    const isNew = i >= prevMsgCount;
    const who = user ? "我" : (m.expert || "system");
    const av = user
      ? `<div class="avatar av-user">我</div>`
      : `<div class="avatar av-${m.expert || "system"}">${AV_LETTER[m.expert] || "AI"}</div>`;
    const refs = (m.refs || []).length
      ? `<div class="refs">refs: ${m.refs.map((r) =>
          `<a href="#" class="badge bg-azure-lt cardref" data-id="${esc(r)}">${esc(String(r).slice(0, 14))}…</a>`).join(" ")}</div>`
      : "";
    return `<div class="msg ${user ? "user" : "expert"}${isNew ? " new" : ""}">${av}
      <div class="msg-col"><div class="meta"><span class="who ${user ? "c-user" : EXPERT_CLASS[m.expert] || "dim"}">${esc(who)}</span><span>${fmtT(m.ts)}</span></div>
      <div class="bubble">${md(m.content || "")}${refs}</div></div></div>`;
  }).join("");
  if (PENDING) {
    html += `<div class="msg expert"><div class="avatar av-system">AI</div>
      <div class="msg-col"><div class="meta"><span class="who dim">expert</span></div>
      <div class="bubble"><span class="dots"><i></i><i></i><i></i></span></div></div></div>`;
  }
  const sc = $("#chat-scroll");
  const nearBottom = sc.scrollHeight - sc.scrollTop - sc.clientHeight < 120;
  list.innerHTML = html ||
    `<div class="text-secondary text-center py-5">开始对话 — 例如「现在持仓情况」「回测一下茅台的双均线」</div>`;
  if (nearBottom) sc.scrollTop = sc.scrollHeight;
  list.dataset.pending = PENDING ? "1" : "";
  prevMsgCount = msgs.length;
}

async function sendChat() {
  const inp = $("#chat-input");
  const text = inp.value.trim();
  if (!text) return;
  inp.value = "";
  inp.style.height = "auto";
  pendingBase = expertMsgs().length;
  PENDING = true;
  renderChat();
  await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  refresh();
}
$("#chat-send").addEventListener("click", sendChat);
const chatInput = $("#chat-input");
chatInput.addEventListener("input", () => {
  chatInput.style.height = "auto";
  chatInput.style.height = Math.min(chatInput.scrollHeight, 132) + "px";
});
chatInput.addEventListener("keydown", (e) => {
  if (e.key !== "Enter" || e.shiftKey || e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.isComposing || e.keyCode === 229) return;   // CJK IME composition Enter confirms text, not send
  e.preventDefault();
  if (!e.repeat) sendChat();
});

/* ── tables ── */
function tbl(el, heads, rows, opts = {}) {
  el.innerHTML = "<thead><tr>" + heads.map((h) => `<th>${h}</th>`).join("") + "</tr></thead><tbody>" +
    rows.map((r) => `<tr${opts.click ? ' class="clickable"' : ""}>${r.join("")}</tr>`).join("") +
    "</tbody>";
  if (opts.click) el.querySelectorAll("tr.clickable").forEach((tr, i) =>
    tr.addEventListener("click", () => opts.click(i)));
}
const pill = (txt, cls) => `<span class="badge bg-${cls}-lt">${esc(txt)}</span>`;
const AGE_PILL = (sec) => sec < 20 ? pill("online", "green") : sec < 120 ? pill("stale", "yellow") : pill("down", "red");

function render() {
  if (!SNAP) return;
  const s = SNAP;
  const now = Date.now() / 1000;
  const hbs = s.agents || [];
  const online = hbs.filter((a) => now - new Date(a.ts).getTime() / 1000 < 20).length;
  const st = $("#status");
  st.className = "badge " + (online ? "ok" : "");
  st.innerHTML = `<i class="status-dot status-dot-animated"></i>${online}/${hbs.length} agents online`;

  tbl($("#tbl-agents"), ["组件", "状态", "心跳", "age", "指标"],
    [...hbs].sort((a, b) => a.agent.localeCompare(b.agent)).map((a) => {
      const age = Math.max(0, now - new Date(a.ts).getTime() / 1000);
      return [`<td>${esc(a.agent)}</td>`, `<td>${AGE_PILL(age)}</td>`,
        `<td class="mono dim">${fmtT(a.ts)}</td>`, `<td class="mono dim">${age.toFixed(0)}s</td>`,
        `<td class="mono dim">${esc(JSON.stringify(a.metrics || {}))}</td>`];
    }));

  const cards = s.cards || [];
  tbl($("#tbl-cards"), ["时间", "类型", "标的", "组件", "来源"],
    cards.map((c) => [
      `<td class="mono dim">${fmtT(c.asof)}</td>`, `<td>${pill(c.kind, "azure")}</td>`,
      `<td>${esc((c.symbols || []).join(","))}</td>`, `<td class="dim">${esc(c.agent)}</td>`,
      `<td class="dim">${esc(c.source || "")}</td>`]),
    { click: (i) => openCard(cards[i]) });

  const decs = s.decisions || [];
  tbl($("#tbl-decisions"), ["时间", "标的", "动作", "数量", "目标仓位", "模型", "refs"],
    decs.map((d) => {
      const act = String(d.action || "").split(".").pop();
      const cls = act === "BUY" ? "green" : act === "SELL" ? "red" : "secondary";
      const refs = (d.card_refs || []).map((r) =>
        `<a href="#" class="badge bg-azure-lt cardref" data-id="${esc(r)}">${esc(String(r).slice(0, 10))}</a>`).join(" ");
      return [`<td class="mono dim">${fmtT(d.ts)}</td>`, `<td>${esc(d.symbol)}</td>`,
        `<td>${pill(act, cls)}</td>`, `<td class="mono">${num(d.qty, 0)}</td>`,
        `<td class="mono">${d.target_weight != null ? (d.target_weight * 100).toFixed(0) + "%" : ""}</td>`,
        `<td class="dim">${esc((d.llm || {}).model || "policy")}</td>`,
        `<td class="mono">${refs}</td>`];
    }));

  const acc = s.account;
  const last = lastCloses(cards);
  let equity = acc ? acc.equity : 0, unreal = 0;
  (s.positions || []).forEach((p) => {
    if (p.qty) unreal += p.qty * ((last[p.symbol] ?? p.avg_cost) - p.avg_cost);
  });
  const kpis = [
    ["现金", acc?.cash, ""], ["总资产", equity, ""],
    ["浮动盈亏", unreal, unreal >= 0 ? "text-green" : "text-red", true],
    ["更新时间", fmtT(acc?.updated_ts), ""],
  ];
  $("#kpis").innerHTML = kpis.map(([k, v, c, sign], i) => {
    const shown = typeof v === "number" ? ((sign && v >= 0 ? "+" : "") + num(v, 0)) : v;
    return `<div class="col-sm-6 col-lg-3"><div class="card"><div class="card-body">
     <div class="subheader">${k}</div><div class="h1 mb-0 ${c}" data-kpi="${k}" data-v="${typeof v === "number" ? v : ""}">${shown ?? "-"}</div></div></div></div>`;
  }).join("");
  animateKpis();
  tbl($("#tbl-pos"), ["标的", "数量", "成本", "现价", "走势", "市值", "浮动盈亏"],
    (s.positions || []).filter((p) => p.qty).map((p) => {
      const px = last[p.symbol] ?? p.avg_cost, pnl = p.qty * (px - p.avg_cost);
      return [`<td>${esc(p.symbol)}</td>`, `<td class="mono">${num(p.qty, 0)}</td>`,
        `<td class="mono">${num(p.avg_cost)}</td>`, `<td class="mono">${num(px)}</td>`,
        `<td><canvas class="spark" data-sym="${esc(p.symbol)}"></canvas></td>`,
        `<td class="mono">${num(p.qty * px, 0)}</td>`,
        `<td class="mono ${pnl >= 0 ? "text-green" : "text-red"}">${pnl >= 0 ? "+" : ""}${num(pnl, 0)}</td>`];
    }));
  drawSparks(cards);
  tbl($("#tbl-fills"), ["时间", "订单", "状态", "数量", "价格", "通道"],
    (s.fills || []).map((f) => [
      `<td class="mono dim">${fmtT(f.ts)}</td>`, `<td class="mono dim">${esc(String(f.order_id || "").slice(-8))}</td>`,
      `<td>${esc(String(f.status || "").split(".").pop())}</td>`, `<td class="mono">${num(f.filled_qty, 0)}</td>`,
      `<td class="mono">${num(f.avg_price)}</td>`, `<td class="dim">${esc(f.broker || "")}</td>`]));

  tbl($("#tbl-risk"), ["时间", "等级", "代码", "标的", "veto", "内容"],
    (s.risk || []).map((e) => {
      const lv = String(e.level || "").split(".").pop();
      const cls = lv === "CRITICAL" ? "red" : lv === "WARN" ? "yellow" : "secondary";
      return [`<td class="mono dim">${fmtT(e.ts)}</td>`, `<td>${pill(lv, cls)}</td>`,
        `<td>${esc(e.code || "")}</td>`, `<td>${esc((e.symbols || []).join(","))}</td>`,
        `<td>${e.veto ? pill("veto", "red") : ""}</td>`, `<td class="dim">${esc(e.message || "")}</td>`];
    }));

  $("#reports").innerHTML = (s.reports || []).map((r) =>
    `<div class="card rep"><div class="card-body p-3">
       <div class="h">${pill(r.kind, "azure")}<span>${fmtT(r.ts)}</span><span>${esc(r.agent || "system")}</span></div>
       <div>${esc(r.summary)}</div></div></div>`).join("") ||
    `<div class="text-secondary">还没有学习报告 — qs trigger learn 跑一轮</div>`;

  renderChat();
  if (PENDING && expertMsgs().length > pendingBase) PENDING = false;
}

function lastCloses(cards) {
  const out = {};
  for (const c of cards) {
    if (String(c.kind).split(".").pop() !== "market") continue;
    const closes = (c.payload || {}).closes || [];
    (c.symbols || []).forEach((sym) => { if (closes.length && !(sym in out)) out[sym] = closes[closes.length - 1]; });
  }
  return out;
}

/* ── animated KPI count-up + TradingView-style sparklines ── */
function animateKpis() {
  const DUR = 550;
  $$("[data-kpi]").forEach((el) => {
    const to = parseFloat(el.dataset.v);
    if (isNaN(to)) return;
    const from = kpiPrev[el.dataset.kpi] ?? 0;
    kpiPrev[el.dataset.kpi] = to;
    if (from === to) return;
    const t0 = performance.now();
    const signed = el.textContent.trim().startsWith("+") || from === to;
    const tick = (t) => {
      const p = Math.min(1, (t - t0) / DUR), e = 1 - Math.pow(1 - p, 3);
      const v = from + (to - from) * e;
      el.textContent = (v >= 0 && el.dataset.kpi === "浮动盈亏" ? "+" : "") + num(v, 0);
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

function drawSparks(cards) {
  $$(".spark").forEach((cv) => {
    const sym = cv.dataset.sym;
    let series = null;
    for (const c of cards) {
      if (String(c.kind).split(".").pop() !== "market") continue;
      if (!(c.symbols || []).includes(sym)) continue;
      const cl = (c.payload || {}).closes;
      if (cl && cl.length > 1) { series = cl; break; }
    }
    if (!series) return;
    const dpr = window.devicePixelRatio || 1, w = 76, h = 24;
    cv.width = w * dpr; cv.height = h * dpr;
    const x = cv.getContext("2d");
    x.scale(dpr, dpr);
    const min = Math.min(...series), max = Math.max(...series), rg = (max - min) || 1;
    const up = series[series.length - 1] >= series[0];
    const col = up ? "#22C55E" : "#EF4444";
    x.beginPath();
    series.forEach((v, i) => {
      const px = 2 + (i / (series.length - 1)) * (w - 4);
      const py = h - 3 - ((v - min) / rg) * (h - 6);
      i ? x.lineTo(px, py) : x.moveTo(px, py);
    });
    x.strokeStyle = col; x.lineWidth = 1.4; x.lineJoin = "round"; x.stroke();
    x.lineTo(w - 2, h); x.lineTo(2, h); x.closePath();
    x.fillStyle = up ? "rgba(34,197,94,.10)" : "rgba(239,68,68,.10)";
    x.fill();
  });
}

/* ── card modal / files ── */
async function openCard(c) {
  const d = await (await fetch("/api/card/" + encodeURIComponent(c.card_id))).json();
  $("#modal-body").textContent = JSON.stringify(d, null, 2);
  $("#modal").classList.remove("hidden");
}
document.addEventListener("click", (e) => {
  const a = e.target.closest(".cardref");
  if (a) { e.preventDefault(); openCard({ card_id: a.dataset.id }); }
});
$("#modal-close").addEventListener("click", () => $("#modal").classList.add("hidden"));
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") $("#modal").classList.add("hidden"); });

async function loadFiles() {
  filesCache = await (await fetch("/api/files")).json();
  $("#file-list").innerHTML = Object.keys(filesCache).sort()
    .map((n) => `<div class="f" data-n="${esc(n)}">${esc(n)}</div>`).join("");
  $$("#file-list .f").forEach((f) => f.addEventListener("click", () => {
    $$("#file-list .f").forEach((x) => x.classList.toggle("on", x === f));
    $("#file-view").textContent = filesCache[f.dataset.n] || "(空)";
  }));
}

/* ── loop ── */
async function refresh() {
  try {
    SNAP = await (await fetch("/api/snapshot")).json();
    render();
  } catch (e) { /* server restarting */ }
}
setInterval(refresh, 2500);
setInterval(() => { $("#clock").textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false }); }, 1000);
refresh();
