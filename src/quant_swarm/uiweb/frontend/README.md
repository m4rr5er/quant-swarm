# Quant$warm Web Terminal

TradingView 风格前端，fork 自 [outlinersclub-cpu/tradingview-gratis](https://github.com/outlinersclub-cpu/tradingview-gratis)
（原项目为 Binance 加密行情的 TradingView 复刻）。已将数据层整体替换为 Quant$warm 后端：

- `src/lib/qs/` — 数据层替换：`api.ts`（REST → FastAPI `/api/*`）、`feed.ts`（快照轮询，替代 Binance WS）、`snapshot-store.ts`（zustand 快照）、`types.ts`
- `src/components/chat/ChatPanel.tsx` — AI 助手坞站（对接 `/api/chat`）
- `src/components/dock/DockPanels.tsx` — 底部数据坞站（持仓/成交/决策/组件/风控/学习）
- 决策 BUY/SELL 标记绘制在 K 线上；watchlist = `configs` 自选 + 市场卡片标的
- `scripts/screenshot.mjs` — headless 截图（playwright），UI 迭代用

```bash
npm ci && npm run build   # → out/（FastAPI 直接托管）
node scripts/screenshot.mjs http://127.0.0.1:8388/ out.png 8000
```

原 `src/lib/binance/` 数据层已删除。
