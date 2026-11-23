import { chromium } from "playwright";
const b = await chromium.launch({
  args: [
    "--ignore-certificate-errors",
    "--host-resolver-rules=MAP tradingview.com 127.0.0.1, MAP www.tradingview.com 127.0.0.1, MAP static.tradingview.com 127.0.0.1",
  ],
});
const p = await (await b.newContext({
  viewport: { width: 1680, height: 1000 },
  proxy: { server: "http://172.24.192.1:7897", bypass: "www.tradingview.com,static.tradingview.com,tradingview.com,localhost,127.0.0.1" },
})).newPage();
const fails = [];
p.on("response", (r) => { if (r.status() >= 400 && !r.url().includes("favicon")) fails.push(r.status() + " " + r.url().slice(0, 100)); });
await p.goto("https://localhost/chart/?theme=dark", { waitUntil: "domcontentloaded", timeout: 45000 });
await p.waitForTimeout(25000);
await p.screenshot({ path: "C:/projects/devin_projects/quant-swarm/design-system/terminal/shots/tv-mirror.png" });
console.log("fails:", fails.slice(0, 10));
await b.close(); console.log("done");
