// Headless screenshot of the dashboard for UI iteration.
// Usage: node scripts/screenshot.mjs [url] [out.png] [waitMs]
import { chromium } from "playwright";

const url = process.argv[2] || "http://127.0.0.1:8388/";
const out = process.argv[3] || "C:\\Windows\\Temp\\qs-shot.png";
const waitMs = Number(process.argv[4] || 6000);

const browser = await chromium.launch({
  args: ["--no-proxy-server", "--disable-gpu"],
});
const page = await browser.newPage({ viewport: { width: 1680, height: 1000 } });
page.on("console", (m) => {
  if (m.type() === "error") console.log("[console.error]", m.text());
});
page.on("pageerror", (e) => console.log("[pageerror]", e.message));
page.on("response", (r) => {
  if (r.status() >= 400) console.log("[http]", r.status(), r.url().slice(0, 110));
});
page.on("requestfailed", (r) =>
  console.log("[reqfail]", r.url().slice(0, 90), r.failure()?.errorText),
);
const resp = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
console.log("[goto]", resp?.status(), resp?.url());
await page.waitForTimeout(waitMs);
await page.screenshot({ path: out });
await browser.close();
console.log("saved:", out);
