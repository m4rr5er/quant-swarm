# tv-mirror — TradingView 前端 1:1 本地镜像

把 `tradingview.com/chart` 的**真实前端**（HTML + 全部 webpack bundles + CSS + 字体）
镜像到本地运行。行情数据仍走 TV 官方 `data.tradingview.com` WebSocket（经代理），
所以镜像页是**活的**——真数据、真交互、菜单/面板/画线全可用。

## 结构

```
tv-mirror/
  serve.mjs              # HTTPS 镜像服务（Windows node，监听 :443）
  serve.py               # 旧版 HTTP 镜像（WSL :8610，备用）
  cert.pem / key.pem     # 自签名 *.tradingview.com 证书
  www.tradingview.com/   # 页面（wget -p 镜像 + 运行期缓存补齐）
  static.tradingview.com/# JS/CSS bundles 缓存
```

## 启动（Windows 侧）

```
node C:\projects\devin_projects\quant-swarm\tv-mirror\serve.mjs
```

浏览器打开 `https://localhost/chart/`（自签名证书，点"高级→继续访问"）。
缺资源时服务端会自动经 `127.0.0.1:7897` 代理回源并写入本地缓存。

## Playwright/自动化访问

`scripts/mshot.mjs`（仓库内）：浏览器参数
`--host-resolver-rules=MAP tradingview.com 127.0.0.1, MAP www.tradingview.com 127.0.0.1, MAP static.tradingview.com 127.0.0.1`
+ `--ignore-certificate-errors`，context 配
`proxy: {server: "http://172.24.192.1:7897", bypass: "...tradingview.com..."}`。
WS 数据直连真实 `data.tradingview.com`（经代理 CONNECT，Origin 校验通过）。

## 重新生成镜像

```
wget -E -H -k -p -e robots=off \
  --user-agent="Mozilla/5.0 ... Chrome/131" \
  https://www.tradingview.com/chart/?theme=dark
mv "www.tradingview.com/chart/index.html?theme=dark.html" \
   www.tradingview.com/chart/index.html
```

注意：镜像文件为 TradingView 专有资产，仅供本地原型参考，**不要提交/分发**。
