// Extract real dropdown menus from live tradingview.com/chart (dark).
// Clicks each toolbar control, captures the popup menu DOM items.
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const browser = await chromium.launch({ args: ["--disable-gpu"] });
const ctx = await browser.newContext({
  viewport: { width: 1920, height: 1080 }, locale: "zh-CN", colorScheme: "dark",
});
const page = await ctx.newPage();
await page.goto("https://www.tradingview.com/chart/?theme=dark", { waitUntil: "domcontentloaded", timeout: 45000 });
await page.waitForTimeout(14000);

// enumerate topbar buttons
const labels = await page.evaluate(() =>
  [...document.querySelectorAll("header button, [class*='toolbar'] button")]
    .map((b, i) => ({ i, label: (b.getAttribute("aria-label") || b.textContent || "").trim().slice(0, 40) }))
    .filter((x) => x.label)
);
console.log("buttons:", JSON.stringify(labels));

const grabMenu = async () =>
  page.evaluate(() => {
    const sels = ["[data-name='menu-inner']", "[class*='menuWrap']", "[role='menu']", "[class*='dropdown'] [role='listbox']", "[data-qa-id*='menu']"];
    for (const s of sels) {
      const m = document.querySelector(s);
      if (m && m.getBoundingClientRect().height > 20) {
        return {
          sel: s,
          items: [...m.querySelectorAll("[role='menuitem'],[role='option'],button,[class*='item-'],tr,li")].slice(0, 60).map((it) => ({
            t: (it.textContent || "").replace(/\s+/g, " ").trim().slice(0, 60),
            svg: (it.querySelector("svg") || {}).outerHTML?.slice(0, 600) || null,
          })).filter((x) => x.t || x.svg),
        };
      }
    }
    return null;
  });

const out = {};
for (const { i, label } of labels) {
  try {
    const btn = page.locator("header button, [class*='toolbar'] button").nth(i);
    await btn.click({ timeout: 3000 });
    await page.waitForTimeout(900);
    const menu = await grabMenu();
    if (menu && menu.items.length) out[label] = menu.items;
    await page.keyboard.press("Escape");
    await page.waitForTimeout(400);
  } catch {}
}
writeFileSync("C:\\Windows\\Temp\\tv-menus.json", JSON.stringify(out, null, 1));
console.log("menus captured:", Object.keys(out).join(" | "));
await browser.close();
