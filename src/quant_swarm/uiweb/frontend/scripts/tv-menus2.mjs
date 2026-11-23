// Capture TV dropdown menus by diffing visible overlays before/after click.
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const browser = await chromium.launch({ args: ["--disable-gpu"] });
const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, locale: "zh-CN", colorScheme: "dark" });
const page = await ctx.newPage();
await page.goto("https://www.tradingview.com/chart/?theme=dark", { waitUntil: "domcontentloaded", timeout: 45000 });
await page.waitForTimeout(14000);

const snap = () => page.evaluate(() => {
  const seen = new Set();
  const items = [];
  for (const el of document.querySelectorAll("body *")) {
    const r = el.getBoundingClientRect();
    if (r.width < 40 || r.height < 30 || r.top < 0) continue;
    const cs = getComputedStyle(el);
    const z = parseInt(cs.zIndex) || 0;
    if (z < 90 && cs.position !== "fixed" && cs.position !== "absolute") continue;
    if (cs.position === "static") continue;
    // leaf-ish overlay: direct text or item rows
    const rows = [...el.querySelectorAll("[class*='item'],[role='menuitem'],[role='option'],button,li,tr")].slice(0, 80)
      .map((it) => ({ t: (it.textContent || "").replace(/\s+/g, " ").trim().slice(0, 70), svg: (it.querySelector("svg") || {}).outerHTML?.slice(0, 700) || null }))
      .filter((x) => x.t || x.svg);
    if (!rows.length) continue;
    const key = `${Math.round(r.left)},${Math.round(r.top)},${Math.round(r.width)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    items.push({ r: { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) }, cls: el.className?.toString().slice(0, 60), rows });
  }
  return items;
});

const before = await snap();
const out = {};
const targets = { "1 day": "timeframe", "Candles": "charttype", "Layout setup": "layout", "Manage layouts": "layouts", "Settings": "settings", "Create alert": "alert", "AAPL": "symsearch" };
for (const [label, key] of Object.entries(targets)) {
  try {
    await page.locator(`button[aria-label="${label}"]`).first().click({ timeout: 3000 });
    await page.waitForTimeout(1200);
    const after = await snap();
    const beforeKeys = new Set(before.map((o) => `${o.r.x},${o.r.y},${o.r.w}`));
    out[key] = after.filter((o) => !beforeKeys.has(`${o.r.x},${o.r.y},${o.r.w}`)).sort((a, b) => b.rows.length - a.rows.length).slice(0, 2);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(500);
  } catch (e) { console.log(key, "click fail"); }
}
writeFileSync("C:\\Windows\\Temp\\tv-menus2.json", JSON.stringify(out, null, 1));
for (const [k, v] of Object.entries(out)) {
  console.log("==", k, v.map((o) => o.rows.length + " rows").join(","));
}
await browser.close();
