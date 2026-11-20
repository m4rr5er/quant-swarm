/* Quant$warm terminal — TradingView-style chart + right dock.
   Loaded BEFORE app.js: only declares functions; helpers ($, esc, pill,
   fmtT, SNAP) resolve at call time after app.js defines them. */
"use strict";

let TV = null;                // {chart, candle, vol, ma5, ma20}
let CUR_SYM = null;

function initTerminal() {
  if (!TV) {
    const el = document.querySelector("#tvchart");
    const chart = LightweightCharts.createChart(el, {
      layout: {
        background: { color: "#010410" }, textColor: "#94A3B8",
        fontFamily: "Inter,Segoe UI,Microsoft YaHei UI,sans-serif", fontSize: 11,
      },
      grid: {
        vertLines: { color: "rgba(51,65,85,.22)" },
        horzLines: { color: "rgba(51,65,85,.22)" },
      },
      rightPriceScale: { borderColor: "rgba(51,65,85,.5)" },
      timeScale: { borderColor: "rgba(51,65,85,.5)", timeVisible: false },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
      width: el.clientWidth, height: el.clientHeight,
    });
    TV = {
      chart,
      /* A股约定：红涨绿跌 */
      candle: chart.addCandlestickSeries({
        upColor: "#EF4444", downColor: "#22C55E",
        wickUpColor: "#EF4444", wickDownColor: "#22C55E", borderVisible: false,
      }),
      vol: chart.addHistogramSeries({
        priceFormat: { type: "volume" }, priceScaleId: "",
      }),
      ma5: chart.addLineSeries({
        color: "#F59E0B", lineWidth: 1,
        lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
      }),
      ma20: chart.addLineSeries({
        color: "#A78BFA", lineWidth: 1,
        lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
      }),
    };
    chart.priceScale("").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    new ResizeObserver(() =>
      chart.applyOptions({ width: el.clientWidth, height: el.clientHeight })
    ).observe(el);
    document.querySelectorAll(".stab").forEach((b) => b.addEventListener("click", () => {
      document.querySelectorAll(".stab").forEach((x) => x.classList.toggle("on", x === b));
      document.querySelectorAll(".spanel").forEach((p) =>
        p.classList.toggle("on", p.id === "stab-" + b.dataset.stab));
    }));
  }
  renderSide();
}

async function loadSymbol(sym) {
  if (!TV) return;
  CUR_SYM = sym;
  renderSide();
  const d = await (await fetch("/api/market/" + encodeURIComponent(sym))).json();
  if (CUR_SYM !== sym) return;               // user switched while loading
  const p = d.payload || {}, bars = p.bars || [];
  if (!bars.length) {
    document.querySelector("#chart-empty").textContent =
      "暂无该标的行情 — qs trigger collect 采集一轮";
    document.querySelector("#chart-empty").style.display = "flex";
    return;
  }
  document.querySelector("#chart-empty").style.display = "none";
  TV.candle.setData(bars.map((b) => ({
    time: b.date, open: b.open, high: b.high, low: b.low, close: b.close,
  })));
  TV.vol.setData(bars.map((b) => ({
    time: b.date, value: b.volume,
    color: b.close >= b.open ? "rgba(239,68,68,.42)" : "rgba(34,197,94,.42)",
  })));
  const closes = (p.closes && p.closes.length >= bars.length)
    ? p.closes : bars.map((b) => b.close);
  const off = closes.length - bars.length;
  const ma = (n) => bars.map((b, i) => {
    const j = i + off;
    if (j < n - 1) return null;
    const s = closes.slice(j - n + 1, j + 1);
    return s.length === n
      ? { time: b.date, value: s.reduce((a, v) => a + v, 0) / n }
      : null;
  }).filter(Boolean);
  TV.ma5.setData(ma(5));
  TV.ma20.setData(ma(20));
  const dates = new Set(bars.map((b) => b.date));
  const marks = (SNAP?.decisions || [])
    .filter((d) => d.symbol === sym)
    .map((d) => {
      const act = String(d.action || "").split(".").pop();
      return act === "BUY"
        ? { time: String(d.ts).slice(0, 10), position: "belowBar", color: "#22C55E", shape: "arrowUp", text: "B" }
        : { time: String(d.ts).slice(0, 10), position: "aboveBar", color: "#EF4444", shape: "arrowDown", text: "S" };
    })
    .filter((m) => dates.has(m.time))
    .sort((a, b) => (a.time < b.time ? -1 : 1));
  TV.candle.setMarkers(marks);
  TV.chart.timeScale().fitContent();
  const last = bars[bars.length - 1], prev = bars[bars.length - 2] || last;
  const chg = prev.close ? ((last.close - prev.close) / prev.close) * 100 : 0;
  const up = chg >= 0;
  const qPx = document.querySelector("#q-px"), qChg = document.querySelector("#q-chg");
  qPx.textContent = last.close.toFixed(2);
  qPx.className = "q-px " + (up ? "q-up" : "q-down");
  qChg.textContent = (up ? "+" : "") + chg.toFixed(2) + "%";
  qChg.className = up ? "q-up" : "q-down";
  document.querySelector("#q-asof").textContent =
    (d.source || "") + " · " + String(d.asof || "").slice(0, 10);
}

function renderSide() {
  const wl = [...(SNAP?.watchlist || [])];
  const lastBy = {};
  (SNAP?.cards || []).forEach((c) => {
    if (String(c.kind).split(".").pop() !== "market") return;
    (c.symbols || []).forEach((s) => {
      if (!(s in lastBy)) lastBy[s] = c;
      if (!wl.includes(s)) wl.push(s);
    });
  });
  const chips = document.querySelector("#sym-chips");
  if (chips) {
    chips.innerHTML = wl.map((s) =>
      `<button class="sym-chip ${s === CUR_SYM ? "on" : ""}" data-sym="${esc(s)}">${esc(s)}</button>`).join("");
    chips.querySelectorAll(".sym-chip").forEach((b) =>
      b.addEventListener("click", () => loadSymbol(b.dataset.sym)));
  }
  const wt = document.querySelector("#tbl-watch");
  if (wt) {
    wt.innerHTML =
      "<thead><tr><th>标的</th><th>现价</th><th>涨跌</th></tr></thead><tbody>" +
      wl.map((s) => {
        const cl = ((lastBy[s] || {}).payload || {}).closes || [];
        const last = cl[cl.length - 1], prev = cl[cl.length - 2] ?? last;
        const chg = prev ? ((last - prev) / prev) * 100 : 0;
        const up = chg >= 0;
        return `<tr class="${s === CUR_SYM ? "on" : ""}" data-sym="${esc(s)}">
          <td class="mono">${esc(s)}</td>
          <td class="mono">${last != null ? last.toFixed(2) : "-"}</td>
          <td class="mono ${up ? "q-up" : "q-down"}">${cl.length > 1 ? (up ? "+" : "") + chg.toFixed(2) + "%" : "-"}</td></tr>`;
      }).join("") + "</tbody>";
    wt.querySelectorAll("tr[data-sym]").forEach((r) =>
      r.addEventListener("click", () => loadSymbol(r.dataset.sym)));
  }
  const td = document.querySelector("#term-decs");
  if (td) {
    td.innerHTML = (SNAP?.decisions || []).slice(0, 30).map((d) => {
      const act = String(d.action || "").split(".").pop();
      const cls = act === "BUY" ? "green" : act === "SELL" ? "red" : "secondary";
      return `<div class="tdec">${pill(act, cls)}<span>${esc(d.symbol)}</span><span class="dim">${fmtT(d.ts)}</span></div>`;
    }).join("") || `<div class="dim" style="padding:12px">暂无决策</div>`;
  }
  if (TV && !CUR_SYM && wl.length) loadSymbol(wl[0]);
}
