// Extract real icons + computed metrics from live tradingview.com/chart (dark).
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const browser = await chromium.launch({ args: ["--disable-gpu"] });
const ctx = await browser.newContext({
  viewport: { width: 1920, height: 1080 }, locale: "zh-CN", colorScheme: "dark",
});
const page = await ctx.newPage();
await page.goto("https://www.tradingview.com/chart/?theme=dark", { waitUntil: "domcontentloaded", timeout: 45000 });
await page.waitForTimeout(12000);

const data = await page.evaluate(() => {
  const out = { icons: {}, metrics: {}, colors: {} };
  const pick = (el) => el ? { html: el.outerHTML.slice(0, 2000), r: el.getBoundingClientRect() } : null;

  // toolbar buttons — grab their inner svg
  const tb = document.querySelector("#header-toolbar-symbol-search")?.closest("[class*='toolbar']") || document.querySelector("header");
  const tbtns = tb ? [...tb.querySelectorAll("button")].slice(0, 16) : [];
  out.toolbarButtons = tbtns.map((b) => ({
    label: b.getAttribute("aria-label") || b.textContent.trim().slice(0, 20),
    svg: (b.querySelector("svg") || {}).outerHTML?.slice(0, 800) || null,
  }));
  const r0 = tb?.getBoundingClientRect();
  out.metrics.topbar = r0 ? { h: r0.height } : null;

  // left drawing toolbar
  const rail = document.querySelector("[data-name='drawing-toolbar'], [class*='drawingToolbar'], [class*='drawing-toolbar']");
  out.railButtons = rail ? [...rail.querySelectorAll("button,div[role='button']")].slice(0, 20).map((b) => ({
    label: b.getAttribute("aria-label") || b.getAttribute("data-tooltip") || "",
    svg: (b.querySelector("svg") || {}).outerHTML?.slice(0, 800) || null,
  })) : [];

  // right icon rail
  const rrail = document.querySelector("[data-name='right-toolbar'], [class*='rightPanel'], [class*='widgetbar']");
  out.rrailButtons = rrail ? [...rrail.querySelectorAll("button")].slice(0, 14).map((b) => ({
    label: b.getAttribute("aria-label") || "",
    svg: (b.querySelector("svg") || {}).outerHTML?.slice(0, 800) || null,
  })) : [];
  const rr = rrail?.getBoundingClientRect();
  out.metrics.rrail = rr ? { w: rr.width } : null;

  // watchlist rows
  const rows = [...document.querySelectorAll("[class*='symbol'], [class*='watchlist'] [class*='item'], [class*='item-']")].slice(0, 3);
  out.watchRow = rows[0] ? { r: rows[0].getBoundingClientRect(), css: getComputedStyle(rows[0]).cssText.slice(0, 300) } : null;

  // colors from real elements
  const cs = (sel, props) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const c = getComputedStyle(el);
    return Object.fromEntries(props.map((p) => [p, c[p]]));
  };
  out.colors.body = getComputedStyle(document.body).backgroundColor;
  out.colors.chart = cs(".chart-container, [class*='chartContainer'], .layout__area--center", ["backgroundColor"]);
  out.colors.panel = cs("[class*='rightPanel'], [class*='widgetbar']", ["backgroundColor"]);
  out.colors.topbar = cs("header, [class*='toolbar']", ["backgroundColor"]);
  out.colors.text = getComputedStyle(document.body).color;
  out.colors.fs = getComputedStyle(document.body).fontSize;
  // symbol info line
  const sl = [...document.querySelectorAll("*")].find((e) => /Apple Inc|NASDAQ/.test(e.textContent) && e.children.length < 12 && e.getBoundingClientRect().height < 50 && e.getBoundingClientRect().y < 100);
  out.metrics.symline = sl ? { h: sl.getBoundingClientRect().height, fontSize: getComputedStyle(sl).fontSize } : null;
  // all css custom props on :root that look like colors
  const rs = getComputedStyle(document.documentElement);
  const colorVars = {};
  for (let i = 0; i < rs.length; i++) {
    const n = rs[i];
    if (n.startsWith("--")) {
      const v = rs.getPropertyValue(n).trim();
      if (/^#|^rgb/.test(v)) colorVars[n] = v;
    }
  }
  out.colorVars = colorVars;
  return out;
});
writeFileSync("C:\\Windows\\Temp\\tv-extract.json", JSON.stringify(data, null, 1));
console.log("icons:", Object.keys(data));
console.log("toolbar btns:", data.toolbarButtons?.length, "rail:", data.railButtons?.length, "rrail:", data.rrailButtons?.length);
await browser.close();
