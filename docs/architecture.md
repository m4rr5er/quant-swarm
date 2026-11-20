# Quant$warm — MVP 技术方案设计（Phase 1）

| 项目 | 内容 |
|---|---|
| 状态 | 已批准，待实施 M0 |
| 日期 | 2026-11-20 |
| 适用范围 | Windows 桌面端优先；架构不绑定 OS，Linux/macOS 后续移植 |

> **前提假设**
> - 目标市场为 A 股（数据源 Tushare/AKShare）。
> - MVP 阶段交易执行**只接模拟盘（Paper Broker）**；真实券商接口（QMT/CTP 等）须在模拟盘长期验证后再接入。
> - LLM 不锁定厂商——所有 Agent 的模型均由用户自由配置（官方端点或任意第三方 OpenAI 兼容端点）。

---

## 0. 设计原则

1. **高内聚、低耦合、职责分离**：各 Agent 是独立进程，互不 import，只通过消息总线对话；单模块故障不影响整体链路。
2. **契约先行**：`InfoCard` / `Decision` / `OrderIntent` 等 Pydantic schema + subject 命名空间是唯一跨进程接口，先定契约再填实现。
3. **采集与决策分离**：信息采集 Agent 只产出标准化"信息卡片"，不做决策；AI 决策大脑是唯一决策出口。
4. **可替换性**：Provider / Broker / LLM / MessageBus 全部走"抽象基类 + 可插拔实现"，mock 与真实实现同构替换。

系统链路：

```
Scheduler ──ctrl.collect──▶ 采集Agent集群 ──InfoCard──▶ ┐
                          (行情/基本面/资金/事件)        │
风控&复盘Agent ──RiskEvent/veto──────────────────────────┼──▶ AI决策大脑 ──OrderIntent──▶ 执行Agent ──Fill──▶ DB/UI
                                                         └──────────────────────────────┘
                                                      (唯一决策出口)
```

---

## 1. 技术栈选型

### 1.1 桌面端框架：**PySide6（Qt for Python）**

| 候选 | 结论 | 理由 |
|---|---|---|
| **PySide6** | ✅ 选用 | Qt 官方 Python 绑定，LGPL 对开源仓库无授权负担；与后端同为 Python，schema/DB 层零成本复用；`QTableView`/`QSortFilterProxyModel` 适合卡片流、决策日志等数据密集界面；`QSystemTrayIcon` 支持常驻后台监控 |
| PyQt6 | ❌ | API 与 PySide6 几乎相同，但 GPL/商业双协议，开源项目用 PySide6 更干净 |
| Tauri | ❌ | 需 Rust + Web 前端双技术栈 + IPC 桥接，单人开发成本高 |
| Electron | ❌ | JS 技术栈与后端脱节，运行时重、内存占用大 |

配套：
- **qasync**：asyncio 事件循环并入 Qt 事件循环（消息总线客户端是 async，UI 订阅必需）
- **pyqtgraph**：MVP 的 K线/走势图；后续可换 `QWebEngineView` 内嵌 TradingView Lightweight Charts
- 打包（远期）：Nuitka 或 PyInstaller 出 Windows 单 exe

### 1.2 后端语言：**Python 3.12**

- akshare/tushare、pandas、LLM SDK、pydantic、APScheduler 同生态，无跨语言边界
- 依赖管理：**uv**（推荐）或 `python -m venv` + pip（pyproject.toml 两者兼容）
- 工具链：ruff（lint + format）、pytest + pytest-asyncio

### 1.3 Agent 通信机制：**NATS（Core + JetStream）**

| 候选 | 结论 | 理由 |
|---|---|---|
| **NATS** | ✅ 选用 | 单个 `nats-server.exe`（约 20MB、零配置）；原生 pub/sub + request/reply + queue group；JetStream 提供持久化/重放/去重 → 重启不丢数据、消息可回放（白送回测能力）；`nats-py` 客户端成熟 |
| gRPC | ❌ | 点对点 RPC 强，但"卡片广播给 N 个订阅者"的 fan-out 很别扭 |
| Redis Streams | ⚠️ 备选 | 语义够用，但 Windows 上要 Memurai 或 Docker/WSL，桌面分发不友好 |
| RabbitMQ | ❌ | Erlang 依赖，对桌面工具过重 |
| SQLite 轮询队列 | ⚠️ 兜底 | 零依赖但延迟高、无实时推送，仅作降级方案 |

**关键设计：`MessageBus` 抽象 + 两个实现**
- `NatsBus`：真实运行时（各 Agent 独立进程）
- `LocalBus`：进程内 asyncio 队列实现，供单元测试 / 一体化 demo / CI 使用

**Subject 规划（主题即接口）：**

```
qs.ctrl.collect.<agent>      # 调度器 → 触发采集
qs.ctrl.decide               # 调度器 → 触发决策
qs.cards.market.<symbol>     # Agent1 行情信息卡片
qs.cards.fundamental         # Agent2 基本面卡片
qs.cards.capital             # Agent3 资金面卡片
qs.alerts.events             # Agent4 异常事件/风险预警
qs.decisions                 # 决策大脑 → 交易决策
qs.orders                    # → 执行 Agent 的下单意图
qs.fills                     # 执行 Agent → 成交流水
qs.risk.veto                 # 风控 Agent → 否决信号
qs.heartbeat.<agent>         # 全员心跳
```

**统一契约（Pydantic，带 `schema_version` 保证可演进）：**

- `Envelope{msg_id, trace_id, ts, schema_version, payload}` — trace_id 贯穿"采集→决策→下单→成交"全链路
- `InfoCard{card_id, agent, kind, symbols, asof, ttl_sec, confidence, source, payload}` — 四个采集 Agent 的唯一输出格式；payload 内部各 Agent 自定义、外部字段统一
- `Decision{decision_id, ts, symbol, action(BUY/SELL/ADD/REDUCE/HOLD), target_weight|qty, horizon, rationale, card_refs[]}` — `card_refs` 让决策可溯源回具体信息卡片
- `OrderIntent / FillReport / RiskEvent / Heartbeat` 同模式

### 1.4 数据库：**SQLite（WAL 模式）+ Alembic 迁移**

- 单机桌面工具：零配置、单文件、天然可靠；WAL 支持多进程并发读
- 存：信息卡片、决策、订单、成交、持仓、agent 状态、job 执行记录
- SQLAlchemy 2.0 + aiosqlite（降低后续换 Postgres 成本）
- K线等行情时序：MVP 也放 SQLite（观察名单几十只股票、日线级，数据量小）
- **升级路径：DuckDB + Parquet**（列存，适合回测分析）；远期再考虑 TimescaleDB

### 1.5 LLM 接入层：**多档案、全可配置、不锁厂商**

- 统一 `LLMClient` 抽象，默认实现走 **OpenAI 兼容协议**（openai SDK + `base_url`），覆盖 DeepSeek / 通义千问(DashScope 兼容) / GLM / 月之暗面 / OpenAI / Ollama / 任意第三方网关
- **命名档案制**：`configs/settings.yaml` 定义 `llm.profiles.<名字> = {base_url, api_key_env, model, temperature, ...}`，用户可增删任意多个
- **按消费方引用**：决策大脑、Agent2 的 NLP 情绪评分等各自声明 `llm_profile: <名字>`——不同环节可用不同模型（卡片生成走便宜模型、最终决策走强模型）
- 结构化输出统一 `response_format`/tool_calls → Pydantic 校验；tenacity 重试；记录 token/成本
- `policy.py` 兜底：LLM 不可用时降级到规则决策，保证链路不断
- MVP 不上 LangGraph——决策本质是单步综合；非 OpenAI 协议的特殊厂商经 `LLMClient` 插件点扩展

### 1.6 其他关键组件

| 组件 | 选型 | 理由 |
|---|---|---|
| 调度 | **APScheduler**（AsyncIOScheduler + SQLAlchemyJobStore→SQLite） | Python 定时任务事实标准；任务持久化重启不丢；cron/interval/date 齐全；重试+死信自实现 |
| 数据源 | **AKShare 优先**（免费无 token），Tushare Pro 留适配接口 | Provider 抽象层让 mock/akshare/tushare 可替换 |
| 配置 | pydantic-settings + `.env`（密钥）+ `configs/settings.yaml`（名单/调度/阈值/LLM 档案） | 密钥与配置分离；远期密钥迁 Windows DPAPI |
| 日志 | **loguru** | 每 Agent 独立滚动文件 `logs/<agent>.log`；trace_id 串联 |

---

## 2. 项目目录结构

```
quant-swarm/
├── pyproject.toml              # 依赖 + ruff + pytest 配置（uv/pip 通用）
├── README.md  LICENSE  .gitignore  .env.example
├── configs/
│   ├── settings.yaml           # 观察名单、调度周期、风控阈值、llm.profiles
│   └── agents.yaml             # 各 Agent 开关与参数（含 llm_profile 引用）
├── docs/
│   ├── architecture.md         # 本文件
│   └── adr/                    # 架构决策记录
├── deploy/
│   └── nats-server.conf        # JetStream 配置
├── scripts/
│   ├── dev_all.ps1             # Windows 一键起 nats+全Agent+UI
│   └── seed_mock.py
├── src/quant_swarm/
│   ├── core/                   # 【共享内核：契约与基础设施，无业务】
│   │   ├── bus/{base.py, nats_bus.py, local_bus.py}
│   │   ├── schemas/{envelope.py, cards.py, decision.py, order.py, risk.py}
│   │   ├── subjects.py
│   │   ├── config.py  logging.py  ids.py  timeutils.py  llm.py
│   │   └── db/{engine.py, models.py, repo.py}
│   ├── scheduler/
│   │   ├── service.py  jobs.py  retry.py  __main__.py
│   ├── agents/
│   │   ├── base.py             # AgentBase：生命周期/心跳/订阅ctrl
│   │   ├── market_data/        # Agent1
│   │   │   ├── agent.py  indicators.py  __main__.py
│   │   │   └── providers/{base.py, mock.py, akshare.py, tushare.py}
│   │   ├── fundamentals/       # Agent2
│   │   ├── capital_flow/       # Agent3
│   │   ├── event_monitor/      # Agent4
│   │   ├── risk_review/        # 风控&复盘
│   │   └── execution/          # 执行 Agent
│   │       ├── agent.py  ledger.py  __main__.py
│   │       └── broker/{base.py, paper.py}   # PaperBroker 模拟撮合
│   ├── brain/
│   │   ├── service.py          # 订阅cards/alerts → 输出Decision
│   │   ├── llm/{client.py, profiles.py}     # OpenAI兼容 + 多档案
│   │   ├── prompts/decision_v1.md
│   │   ├── policy.py           # 规则兜底/护栏
│   │   └── __main__.py
│   ├── ui/
│   │   ├── app.py              # PySide6 + qasync
│   │   ├── views/  widgets/
│   │   └── __main__.py
│   └── cli.py                  # qs run scheduler|agent <名>|brain|ui|all
└── tests/
    ├── contract/               # schema 序列化/兼容性测试
    ├── unit/
    └── e2e/test_flow_localbus.py   # LocalBus 全链路测试
```

**目录设计原则：**
- `core/` 是唯一跨进程公共依赖——Agent 进程间只允许通过"schema + subject"对话，绝不 import 彼此代码
- 每个 Agent 有独立 `__main__.py`，可 `python -m quant_swarm.agents.market_data` 单独拉起
- Provider / Broker / LLM 一律"抽象基类 + 实现可插拔"

---

## 3. MVP 开发路线图

核心策略：**契约先行**。先定死 schema 和 subject，用 Mock 数据打通链路，再逐个替换真实实现。每个里程碑独立可演示。

### M0 — 脚手架与内核
- pyproject、ruff/pytest 配置
- `core/` 全部 schema + `MessageBus` 抽象 + `LocalBus` 实现
- SQLite models + Alembic 初始迁移、loguru、pydantic-settings、LLM 多档案客户端
- CLI 骨架

### M1 — 垂直切片：全 Mock 跑通整条链路 ⭐关键里程碑
- nats-server 本地运行；`MockMarketProvider` 生成确定性 K 线（种子随机游走，测试可复现）
- 调度器触发 `qs.ctrl.collect.market` → market_data Agent 产出 `InfoCard` → 落库
- brain 订阅卡片，先用规则版决策（MA 金叉买/死叉卖）输出 `Decision`；LLM 路径留接口
- execution Agent 收 `OrderIntent` → `PaperBroker` 模拟成交 → `FillReport` + 持仓账本落 SQLite
- 验证：`e2e/test_flow_localbus.py`（LocalBus 全链路）+ 多进程 NATS 实跑
- **产出：数据流闭环，之后所有工作都是"把 mock 换成真的"**

### M2 — 换真实输入
- AKShare 接入：日线行情 + MA/MACD/RSI 指标
- Agent2/3/4 最小真实版：基本面快照、北向/资金流、涨幅异动规则预警（NLP 情绪评分后置，走可配置 LLM 档案）
- brain 换真 LLM：结构化输出 `Decision`（含 rationale + card_refs），`policy.py` 硬性护栏（仓位上限、黑名单）
- 执行仍是 PaperBroker

### M3 — PySide6 桌面仪表盘
- qasync + NATS 订阅；页面：Agent 心跳状态表、信息卡片流、决策日志（理由+溯源）、持仓盈亏、手动"立即运行"、日志查看、LLM 档案配置页
- UI 只依赖 core schema

### M4 — 加固
- JetStream 持久化（重启不丢、可回放）、消息幂等去重、死信队列
- risk_review Agent：持仓限额、事件联动 veto
- Agent 崩溃自动重启（supervisor）、补采逻辑
- Windows 打包初探

### M5+（超出本阶段，仅记录方向）
- 回测引擎（复用 LocalBus/JetStream 回放历史卡片）
- 真实券商适配（QMT/CTP，须模拟盘长期验证后）
- 多策略并行、Linux/macOS 移植

---

## 4. 风险与合规

- **人工确认闸口**：AI 决策为辅助参考，真实下单需人工确认（execution Agent 内置 `require_manual_confirm` 开关）
- Windows 下 NATS 部署：随仓库放 `nats-server.exe` 或脚本引导下载
- AKShare 接口稳定性 / Tushare 积分门槛 → Provider 层隔离，单个数据源挂掉不拖垮链路
- LLM 密钥安全：`.env` 不入库；用户配置第三方端点时 UI 需明示数据流向
- **免责声明**：本项目仅供研究与学习，不构成任何投资建议

---

## 5. 参考项目（仅借鉴架构思路，非复用代码）

| 项目 | 借鉴点 |
|---|---|
| [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | 多 Agent 角色分工（分析/研究/交易/风控）与辩论式决策 |
| [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | 多风格 Agent 信号合成 + 风险管理 Agent 的简洁分层 |
| [microsoft/qlib](https://github.com/microsoft/qlib) | 量化数据层与实验工作流设计 |
| [vnpy/vnpy](https://github.com/vnpy/vnpy) | 事件驱动引擎 + Gateway 适配层（执行侧参考） |
| [freqtrade/freqtrade](https://github.com/freqtrade/freqtrade) | 策略引擎、调度与回测边界划分 |
| [AI4Finance-Foundation/FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) | 金融 Agent 的任务编排与报告生成 |
