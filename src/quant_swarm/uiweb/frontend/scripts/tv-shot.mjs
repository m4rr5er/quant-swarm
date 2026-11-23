// Screenshot tradingview.com/chart (dark) + extract design tokens from the live DOM.
import { chromium } from "playwright";

const browser = await chromium.launch({ args: ["--disable-gpu"] });
const ctx = await browser.newContext({
  viewport: { width: 1920, height: 1080 },
  locale: "zh-CN",
  colorScheme: "dark",
});
const page = await ctx.newPage();
try {
  await page.goto("https://www.tradingview.com/chart/?theme=dark", {
    waitUntil: "domcontentloaded", timeout: 45000,
  });
  await page.waitForTimeout(12000);
  await page.screenshot({ path: "C:\\Windows\\Temp\\tv-dark.png" });
  // extract real design tokens
  const css = await page.evaluate(() => {
    const rs = getComputedStyle(document.documentElement);
    const names = rs.cssText ? [] : [];
    const out = {};
    for (let i = 0; i < document.styleSheets.length; i++) {}
    // grab CSS vars actually set on :root / body
    const vars = [];
    const probe = document.createElement("div");
    document.body.appendChild(probe);
    const candidates = [
      "--color-tv-blue-500", "--color-bg-primary", "--color-bg-secondary",
      "--color-text-primary", "--color-text-secondary", "--color-border",
      "--shadows-border", "--theme-border-color",
    ];
    for (const c of candidates) out[c] = getComputedStyle(probe).getPropertyValue(c).trim();
    probe.remove();
    const bodyBg = getComputedStyle(document.body).backgroundColor;
    const font = getComputedStyle(document.body).fontFamily;
    return { vars: out, bodyBg, font };
  });
  console.log("tokens:", JSON.stringify(css, null, 1));
  console.log("saved tv-dark.png");
} catch (e) {
  console.log("ERR", e.message);
  await page.screenshot({ path: "C:\\Windows\\Temp\\tv-dark-err.png" }).catch(() => {});
}
await browser.close();
