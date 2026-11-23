// HTTPS caching mirror on :443 — runs on Windows node (port <1024 ok there).
// Serves files from ./<host>/... ; on miss, fetches from real host via proxy + caches.
import https from "node:https";
import http from "node:http";
import { readFileSync, existsSync, statSync, mkdirSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { join, extname, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = dirname(fileURLToPath(import.meta.url));
const PROXY = "http://127.0.0.1:7897";
const CT = { ".js": "text/javascript", ".css": "text/css", ".html": "text/html", ".json": "application/json",
  ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf", ".svg": "image/svg+xml",
  ".png": "image/png", ".ico": "image/x-icon", ".wasm": "application/wasm", ".webmanifest": "application/manifest+json" };

const key = readFileSync(join(ROOT, "key.pem"));
const cert = readFileSync(join(ROOT, "cert.pem"));

function handle(req, res) {
  let host = req.headers.host?.split(":")[0] || "www.tradingview.com";
  if (host === "localhost" || host === "127.0.0.1") host = "www.tradingview.com";
  let upath = decodeURIComponent((req.url || "/").split("?")[0]);
  // wget -k rewrites cross-host asset URLs as relative "/<host>/..." — unwrap
  const seg = upath.split("/")[1] || "";
  if (seg.endsWith("tradingview.com")) { host = seg; upath = "/" + upath.split("/").slice(2).join("/"); }
  let rel = join(host, upath === "/" ? "index.html" : upath);
  let file = join(ROOT, rel);
  if (existsSync(file) && statSync(file).isDirectory()) file = join(file, "index.html");
  const send = (code, body, type) => {
    res.writeHead(code, { "Content-Type": type || CT[extname(file)] || "application/octet-stream",
      "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*" });
    res.end(body);
  };
  if (req.method === "OPTIONS") return send(200, "");
  if (existsSync(file) && statSync(file).isFile()) return send(200, readFileSync(file));
  if (!host.endsWith("tradingview.com")) return send(404, "not found");
  // fetch from origin via proxy (curl handles CONNECT)
  const qidx = (req.url || "").indexOf("?");
  const url = `https://${host}${upath}${qidx >= 0 ? req.url.slice(qidx) : ""}`;
  try {
    const body = req.method === "GET" || req.method === "HEAD" ? null : readBody(req);
    const finish = (bodyBuf) => {
      try {
        const args = ["-s", "--proxy", PROXY, "--max-time", "25",
          "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
          "-e", "https://www.tradingview.com/chart/",
          "-H", "accept: */*", "-H", "accept-language: en-US,en;q=0.9",
          "-X", req.method, "-o", "-", "-w", "\n%{http_code}"];
        if (bodyBuf) args.push("--data-binary", "@-", "-H", `content-type: ${req.headers["content-type"] || "application/octet-stream"}`);
        const out = execFileSync("curl", args.concat([url]), { input: bodyBuf || undefined, maxBuffer: 50 * 1024 * 1024 });
        const s = out.toString("latin1");
        const idx = s.lastIndexOf("\n");
        const code = +s.slice(idx + 1) || 502;
        const data = s.slice(0, idx);
        if (code === 200 && req.method === "GET") { mkdirSync(join(ROOT, host, dirname(upath)), { recursive: true }); writeFileSync(file, Buffer.from(data, "latin1")); }
        console.log(`[mirror] ${code} ${req.method} ${url.slice(0, 90)} (${data.length}b)`);
        send(code, Buffer.from(data, "latin1"), "application/octet-stream");
      } catch (e) { console.log(`[mirror] ERR ${url.slice(0, 80)}: ${String(e).slice(0, 100)}`); send(502, "upstream fail"); }
    };
    if (body === null) return finish(null);
    let bufs = []; req.on("data", (c) => bufs.push(c)); req.on("end", () => finish(Buffer.concat(bufs)));
  } catch (e) { send(502, "fail"); }
}
function readBody() { return null; }
process.on("uncaughtException", (e) => console.log("[mirror] uncaught:", String(e).slice(0, 200)));
process.on("unhandledRejection", (e) => console.log("[mirror] rejection:", String(e).slice(0, 200)));

https.createServer({ key, cert }, handle).listen(443, "127.0.0.1", () => console.log("https mirror :443 up"));
