import { chromium } from "playwright";
const b=await chromium.launch();
const ctx=await b.newContext({viewport:{width:1680,height:1000},proxy:{server:"http://172.24.192.1:7897",bypass:"127.0.0.1,localhost"}});
const p=await ctx.newPage();
// bridge TV data websockets
await p.routeWebSocket(/data\.tradingview\.com|pushstream\.tradingview\.com/,(ws)=>{
  const server=ws.connectToServer();
  ws.onMessage(m=>server.send(m));
  server.onMessage(m=>ws.send(m));
  server.onClose(()=>ws.close());
});
p.on("websocket",ws=>console.log("WS:",ws.url().slice(0,80)));
await p.goto("http://127.0.0.1:8610/www.tradingview.com/chart/",{waitUntil:"domcontentloaded"});
await p.waitForTimeout(20000);
await p.screenshot({path:"C:/projects/devin_projects/quant-swarm/design-system/terminal/shots/tv-mirror.png"});
await b.close();console.log("done");
