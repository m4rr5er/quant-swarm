/* Quant$warm SPA — snapshot polling + per-page renderers. */
"use strict";

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
let SNAP = null;
let PENDING = false;          // waiting for an expert reply
let filesCache = null;

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmtT = (ts) => ts ? new Date(ts).toLocaleTimeString("zh-CN", { hour12: false }) : "-";
const num = (n, d = 2) => (n === null || n === undefined) ? "" :
  Number(n).toLocaleString("zh-CN", { maximumFractionDigits: d });

/* ── minimal markdown (bold/headers/tables/code/lists) ─────────── */
function md(src) {
  const blocks = [];
  let h = esc(src).replace(/```(\w*)\n?([\s\S]*?)```/g, (_, _l, c) => {
    blocks.push(c.replace(/\n$/, ""));
    return `${blocks.length - 1}`;
  });
  // tables: consecutive |...| lines containing a --- separator
  h = h.replace(/((?:^\|[^\n]*\|\s*$\n?)+)/gm, (block) => {
    const rows = block.trim().split("\n").map((r) => r.trim());
    if (!rows.some((r) => /^\|[\s\-|:]+\|?$/.test(r))) return block;
    const cells = (r) => r.replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
    const body = rows.filter((r) => !/^\|[\s\-|:]+\|?$/.test(r));
    return "<table class='mdt'>" + body.map((r, i) =>
      "<tr>" + cells(r).map((c) => (i === 0 ? `<th>${c}</th>` : `<td>${c}</td>`)).join("") + "</tr>"
    ).join("") + "</table>";
  });
  h = h
    .replace(/^###### (.*)$/gm, "<h4>$1</h4>").replace(/^##### (.*)$/gm, "<h4>$1</h4>")
    .replace(/^#### (.*)$/gm, "<h4>$1</h4>").replace(/^### (.*)$/gm, "<h4>$1</h4>")
    .replace(/^## (.*)$/gm, "<h3>$1</h3>").replace(/^# (.*)$/gm, "<h3>$1</h3>")
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`\n]+)`/g, "<code class='ic'>$1</code>")
    .replace(/^&gt; (.*)$/gm, "<p class='dim'>$1</p>");
  // - lists and 1. lists
  h = h.replace(/((?:^[ \t]*[-*] [^\n]*\n?)+)/gm, (b) =>
    "<ul>" + b.trim().split("\n").map((l) => `<li>${l.replace(/^[ \t]*[-*] /, "")}</li>`).join("") + "</ul>");
  h = h.replace(/((?:^\d+[.、] [^\n]*\n?)+)/gm, (b) =>
    "<ol>" + b.trim().split("\n").map((l) => `<li>${l.replace(/^\d+[.、] /, "")}</li>`).join("") + "</ol>");
  h = h.replace(/\n{2,}/g, "<br><br>").replace(/\n/g, "<br>");
  return h.replace(/(\d+)/g, (_, i) =>
    `<pre class="code"><code>${blocks[+i]}</code></pre>`);
}

/* ── nav ── */
$$(".nav").forEach((b) => b.addEventListener("click", () => {
  $$(".nav").forEach((x) => x.classList.toggle("on", x === b));
  $$(".page").forEach((p) => p.classList.toggle("on", p.id === "page-" + b.dataset.page));
  if (b.dataset.page === "learning") loadFiles();
}));

/* ── chat ── */
const EXPERT_CLASS = { investor: "c-investor", quant: "c-quant", system: "dim" };
const AV_LETTER = { investor: "投", quant: "量", system: "S" };

function renderChat() {
  const list = $("#chat-list");
  const msgs = SNAP.chat || [];
  let html = msgs.map((m) => {
    const user = m.role === "user";
    const who = user ? "我" : (m.expert || "system");
    const av = user
      ? `<div class="avatar av-user">我</div>`
      : `<div class="avatar av-${m.expert || "system"}">${AV_LETTER[m.expert] || "AI"}</div>`;
    const refs = (m.refs || []).length
      ? `<div class="refs">refs: ${m.refs.map((r) => `<a href="#" class="cardref dim" data-id="${esc(r)}">${esc(r.slice(0, 14))}…</a>`).join(" ")}</div>`
      : "";
    return `<div class="msg ${user ? "user" : "expert"}">${av}
      <div><div class="meta"><span class="who ${user ? "c-user" : EXPERT_CLASS[m.expert] || "dim"}">${esc(who)}</span><span>${fmtT(m.ts)}</span></div>
      <div class="bubble">${md(m.content || "")}${refs}</div></div></div>`;
  }).join("");
  if (PENDING) {
    html += `<div class="msg expert"><div class="avatar av-system">AI</div>
      <div><div class="meta"><span class="who dim">expert</span></div>
      <div class="bubble"><span class="dots"><span></span><span></span><span></span></span></div></div></div>`;
  }
  const sc = $("#chat-scroll");
  const nearBottom = sc.scrollHeight - sc.scrollTop - sc.clientHeight < 120;
  list.innerHTML = html || `<div class="dim" style="text-align:center;padding:40px">开始对话 — 例如「现在持仓情况」「回测一下茅台的双均线」</div>`;
  if (nearBottom) sc.scrollTop = sc.scrollHeight;
}

async function sendChat() {
  const inp = $("#chat-input");
  const text = inp.value.trim();
  if (!text) return;
  inp.value = "";
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
$("#chat-input").addEventListener("keydown", (e) => { if (e.key === "Enter") sendChat(); });

/* ── tables ── */
function tbl(el, heads, rows, opts = {}) {
  el.innerHTML = "<thead><tr>" + heads.map((h) => `<th>${h}</th>`).join("") + "</tr></thead><tbody>" +
    rows.map((r) => `<tr${opts.click ? ' class="clickable"' : ""}>${r.join("")}</tr>`).join("") +
    "</tbody>";
  if (opts.click) el.querySelectorAll("tr.clickable").forEach((tr, i) =>
    tr.addEventListener("click", () => opts.click(i)));
}
const pill = (txt, cls) => `<span class="pill p-${cls}">${esc(txt)}</span>`;
const AGE_PILL = (sec) => sec < 20 ? pill("online", "green") : sec < 120 ? pill("stale", "amber") : pill("down", "red");

function render() {
  if (!SNAP) return;
  const s = SNAP;
  // status
  const now = Date.now() / 1000;
  const hbs = s.agents || [];
  const online = hbs.filter((a) => now - new Date(a.ts).getTime() / 1000 < 20).length;
  const st = $("#status");
  st.className = "status " + (online ? "ok" : "");
  st.innerHTML = `<i class="dot"></i>${online}/${hbs.length} agents online`;

  // agents
  tbl($("#tbl-agents"), ["组件", "状态", "心跳", "age", "指标"],
    [...hbs].sort((a, b) => a.agent.localeCompare(b.agent)).map((a) => {
      const age = Math.max(0, now - new Date(a.ts).getTime() / 1000);
      return [`<td>${esc(a.agent)}</td>`, `<td>${AGE_PILL(age)}</td>`,
        `<td class="mono dim">${fmtT(a.ts)}</td>`, `<td class="mono dim">${age.toFixed(0)}s</td>`,
        `<td class="mono dim">${esc(JSON.stringify(a.metrics || {}))}</td>`];
    }));

  // cards
  const cards = s.cards || [];
  tbl($("#tbl-cards"), ["时间", "类型", "标的", "组件", "来源"],
    cards.map((c) => [
      `<td class="mono dim">${fmtT(c.asof)}</td>`, `<td>${pill(c.kind, "blue")}</td>`,
      `<td>${esc((c.symbols || []).join(","))}</td>`, `<td class="dim">${esc(c.agent)}</td>`,
      `<td class="dim">${esc(c.source || "")}</td>`]),
    { click: (i) => openCard(cards[i]) });

  // decisions
  const decs = s.decisions || [];
  tbl($("#tbl-decisions"), ["时间", "标的", "动作", "数量", "目标仓位", "模型", "refs"],
    decs.map((d) => {
      const act = String(d.action || "").split(".").pop();
      const cls = act === "BUY" ? "green" : act === "SELL" ? "red" : "dim";
      const refs = (d.card_refs || []).map((r) =>
        `<a href="#" class="cardref" data-id="${esc(r)}">${esc(String(r).slice(0, 10))}</a>`).join(" ");
      return [`<td class="mono dim">${fmtT(d.ts)}</td>`, `<td>${esc(d.symbol)}</td>`,
        `<td>${pill(act, cls)}</td>`, `<td class="mono">${num(d.qty, 0)}</td>`,
        `<td class="mono">${d.target_weight != null ? (d.target_weight * 100).toFixed(0) + "%" : ""}</td>`,
        `<td class="dim">${esc((d.llm || {}).model || "policy")}</td>`,
        `<td class="mono">${refs}</td>`];
    }));

  // portfolio
  const acc = s.account;
  const last = lastCloses(cards);
  let equity = acc ? acc.equity : 0, unreal = 0;
  (s.positions || []).forEach((p) => {
    if (p.qty) unreal += p.qty * ((last[p.symbol] ?? p.avg_cost) - p.avg_cost);
  });
  $("#kpis").innerHTML = [
    ["现金", num(acc?.cash, 0), ""], ["总资产", num(equity, 0), ""],
    ["浮动盈亏", (unreal >= 0 ? "+" : "") + num(unreal, 0), unreal >= 0 ? "up" : "down"],
    ["更新时间", fmtT(acc?.updated_ts), ""],
  ].map(([k, v, c]) => `<div class="kpi"><div class="k">${k}</div><div class="v ${c}">${v}</div></div>`).join("");
  tbl($("#tbl-pos"), ["标的", "数量", "成本", "现价", "市值", "浮动盈亏"],
    (s.positions || []).filter((p) => p.qty).map((p) => {
      const px = last[p.symbol] ?? p.avg_cost, pnl = p.qty * (px - p.avg_cost);
      return [`<td>${esc(p.symbol)}</td>`, `<td class="mono">${num(p.qty, 0)}</td>`,
        `<td class="mono">${num(p.avg_cost)}</td>`, `<td class="mono">${num(px)}</td>`,
        `<td class="mono">${num(p.qty * px, 0)}</td>`,
        `<td class="mono" style="color:${pnl >= 0 ? "var(--green)" : "var(--red)"}">${pnl >= 0 ? "+" : ""}${num(pnl, 0)}</td>`];
    }));
  tbl($("#tbl-fills"), ["时间", "订单", "状态", "数量", "价格", "通道"],
    (s.fills || []).map((f) => [
      `<td class="mono dim">${fmtT(f.ts)}</td>`, `<td class="mono dim">${esc(String(f.order_id || "").slice(-8))}</td>`,
      `<td>${esc(String(f.status || "").split(".").pop())}</td>`, `<td class="mono">${num(f.filled_qty, 0)}</td>`,
      `<td class="mono">${num(f.avg_price)}</td>`, `<td class="dim">${esc(f.broker || "")}</td>`]));

  // risk
  tbl($("#tbl-risk"), ["时间", "等级", "代码", "标的", "veto", "内容"],
    (s.risk || []).map((e) => {
      const lv = String(e.level || "").split(".").pop();
      const cls = lv === "CRITICAL" ? "red" : lv === "WARN" ? "amber" : "dim";
      return [`<td class="mono dim">${fmtT(e.ts)}</td>`, `<td>${pill(lv, cls)}</td>`,
        `<td>${esc(e.code || "")}</td>`, `<td>${esc((e.symbols || []).join(","))}</td>`,
        `<td>${e.veto ? pill("veto", "red") : ""}</td>`, `<td class="dim">${esc(e.message || "")}</td>`];
    }));

  // learning reports
  $("#reports").innerHTML = (s.reports || []).map((r) =>
    `<div class="rep"><div class="h">${pill(r.kind, "blue")}<span>${fmtT(r.ts)}</span><span>${esc(r.agent || "system")}</span></div>
     <div>${esc(r.summary)}</div></div>`).join("") ||
    `<div class="dim">还没有学习报告 — qs trigger learn 跑一轮</div>`;

  renderChat();
  // pending clears once an expert message arrived
  if (PENDING && msgs().length) PENDING = false;
}

const msgs = () => (SNAP.chat || []).filter((m) => m.role === "expert");

function lastCloses(cards) {
  const out = {};
  for (const c of cards) {
    if (String(c.kind).split(".").pop() !== "market") continue;
    const closes = (c.payload || {}).closes || [];
    (c.symbols || []).forEach((sym) => { if (closes.length && !(sym in out)) out[sym] = closes[closes.length - 1]; });
  }
  return out;
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
