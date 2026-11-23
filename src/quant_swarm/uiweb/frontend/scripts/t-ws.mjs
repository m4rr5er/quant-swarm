import { chromium } from "playwright";
const b=await chromium.launch();
const p=await (await b.newContext({proxy:{server:"http://172.24.192.1:7897",bypass:"127.0.0.1,localhost"}})).newPage();
p.on("websocket",ws=>{console.log("WS open:",ws.url());ws.on("close",()=>console.log("WS close:",ws.url()))});
p.on("requestfailed",r=>{if(!r.url().includes("8610"))console.log("FAIL:",r.url().slice(0,90),r.failure()?.errorText)});
await p.goto("http://127.0.0.1:8610/www.tradingview.com/chart/",{waitUntil:"domcontentloaded"});
await p.waitForTimeout(20000);
await b.close();console.log("done");
