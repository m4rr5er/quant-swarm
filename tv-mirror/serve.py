#!/usr/bin/env python3
"""Caching mirror server: serve local files; on 404 fetch from origin via proxy and cache."""
import http.server, os, urllib.request, sys, io

ROOT = os.path.dirname(os.path.abspath(__file__))
PROXY = "http://172.24.192.1:7897"

class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isfile(path):
            return super().send_head()
        # derive origin: top dir is host name
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        q = self.path.split("?", 1)
        urlp = q[0].lstrip("/")
        url = ("https://" + urlp if "." in urlp.split("/")[0] else "https://www.tradingview.com/" + urlp) + ("?" + q[1] if len(q) > 1 else "")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=30).read()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
            print(f"[mirror] fetched {rel} ({len(data)//1024}KB)", flush=True)
            self.send_response(200)
            ext = path.rsplit(".", 1)[-1].lower()
            ctype = {"js": "text/javascript", "css": "text/css", "woff2": "font/woff2",
                     "woff": "font/woff", "ttf": "font/ttf", "svg": "image/svg+xml",
                     "png": "image/png", "json": "application/json", "html": "text/html",
                     "ico": "image/x-icon", "wasm": "application/wasm"}.get(ext, "application/octet-stream")
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return io.BytesIO(data)
        except Exception as e:
            print(f"[mirror] miss {rel}: {e}", flush=True)
            return super().send_head()

    def do_POST(self):
        q = self.path.split("?", 1)
        urlp = q[0].lstrip("/")
        url = ("https://" + urlp if "." in urlp.split("/")[0] else "https://www.tradingview.com/" + urlp) + ("?" + q[1] if len(q) > 1 else "")
        body = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        try:
            req = urllib.request.Request(url, data=body, method="POST",
                headers={"User-Agent": "Mozilla/5.0", "Content-Type": self.headers.get("Content-Type", "application/json")})
            r = urllib.request.urlopen(req, timeout=30)
            data = r.read()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data))); self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_response(502); self.end_headers()
            print(f"[mirror] POST miss {url}: {e}", flush=True)

http.server.ThreadingHTTPServer(("127.0.0.1", 8610), H).serve_forever()
