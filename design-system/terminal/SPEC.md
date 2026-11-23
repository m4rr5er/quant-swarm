# Quant$warm Terminal — 设计规格 v2（TradingView 1:1 复刻）

> 图表为中心、AI 嵌入的多智能体量化终端。原型：`src/quant_swarm/uiweb/prototype/index.html`
> 参照基准：**tradingview.com/chart 真实截图**（tv-dark.png，桌面版即它的 CEF 壳）。
> token 实测自真实页面：bg `#131313`、panel `#1e1e1e`、text `#dbdbdb/#b8b8b8`、muted `#8c8c8c`、
> 涨 `#089981` / 跌 `#f23645`（TV 色值，注意：与我们旧 A 股红涨绿跌相反，TV 是绿涨红跌）、
> 蓝 `#2962ff`、紫 `#9c6dff`（overnight）、字 `-apple-system,Trebuchet MS,Roboto,Ubuntu`。

## 1. 布局（对照 TV 实测）

```
顶栏 38px: ≡ | 标的▾ | 00 | + | 1D▾ | K线样式 | 指标 | 警报 | 回放 | ↩↪
          ‖ 布局 | 保存▾ | 头像 | ? 🔔 📷 | [交易面板] [模拟盘]
标的行 34px: ● 名称 · 1D · SH · A股 | 🌙盘前 | ≈akshare | O H L C ±% | [卖出]|[买入]
┌───┬──────────────────────────────────────────┬────────────┬────┐
│50px│  主图区 (K线+MA+VOL+RSI子pane)             │ 330px 面板  │44px│
│工具│  · OHLC legend  · watermark  · 画线/测量    │ 自选/AI/决策│图标│
│轨  │                                          │ + 标的详情卡│轨 │
└───┴──────────────────────────────────────────┴────────────┴────┘
底坞 0-230px(▴开合/拖高调): 持仓|成交|组件|风控|学习    [现金·总资产·当日]
底栏 30px: logo | 1D 5D 1M 3M 6M YTD 1Y 5Y 全部 ⚙ ‖ 时钟UTC | 复权 | 数据坞站▴
```

## 2. 与 TV 的差异点（我们的 AI 化改造）

- 右侧图标轨第 2、3 位 = **AI 助手 / 决策流**（TV 里是 alerts/chats 位置）
- 「交易面板」「模拟盘」按钮替代 TV 的 Trade/Upgrade
- 底坞是我们的数据面板（TV 是筛选器/Pine 编辑器位）
- 决策标记 BUY/SELL 箭头直接画在 K 线上，点击弹详情

## 3. 交互（沿用 v1 验收清单）

⌘K 搜标的（↑↓/Enter/Esc）、十字光标 OHLC 联动、画线（水平线/趋势线/测量）、
右坞 260–520px 拖宽、底坞开合+拖高、聊天 Enter 发送（IME 保护）+三点+markdown、
自选行点击切图、决策条目点击跳标的。

## 验收

- [ ] 和真实 TV 并排对比，布局/间距/色值肉眼一致
- [ ] 右图标轨切面板、底坞开合顺畅
- [ ] 画线/测量/标记/搜索/聊天全链路可用


> 图表为中心、AI 嵌入的多智能体量化终端。原型：`src/quant_swarm/uiweb/prototype/index.html`
> 参照系：TradingView（布局/图表交互）、Linear（面板/徽标语义）、Telegram Desktop（对话密度）、Notion（命令面板）。

