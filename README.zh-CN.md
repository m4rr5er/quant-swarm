# Quant$warm

[English](README.md)

**基于大模型 + 多智能体架构的 AI 投资辅助决策与量化分析 Windows 桌面系统**。

> 状态：🚧 早期设计阶段 —— 完整 MVP 技术方案见 [`docs/architecture.md`](docs/architecture.md)

## 工作链路

```
                    ┌──────────────────────────────────────────┐
 统一调度器 ───────▶ │ 信息采集 Agent 集群（只拿数据，不做决策）      │
 (APScheduler)      │  1.行情数据  2.基本面&行业                  │
                    │  3.资金面    4.异常事件监控                 │
                    └───────────────┬──────────────────────────┘
                                    │ 标准化"信息卡片"
   风控&复盘Agent ──────────────────┼───────▶ ┌────────────┐
   （只监控、可否决）                 │         │ AI 决策大脑 │（唯一决策出口）
                                    └───────▶ └─────┬──────┘
                                                    │ OrderIntent
                                              ┌─────▼──────┐
                                              │ 交易执行Agent │──▶ 模拟撮合(MVP)
                                              └────────────┘
```

所有 Agent 均为**独立进程**，通过消息总线通信——单个模块故障不影响整体链路。

## 技术栈

| 层 | 选型 |
|---|---|
| 桌面 UI | PySide6 + qasync + pyqtgraph |
| 语言 | Python 3.12 |
| Agent 通信 | NATS（Core + JetStream），外包 `MessageBus` 抽象 |
| 数据库 | SQLite(WAL) + Alembic → 升级路径 DuckDB/Parquet |
| 调度 | APScheduler |
| LLM | OpenAI 兼容客户端，**命名档案全自由配置**，官方/第三方端点皆可 |
| 数据源 | AKShare 优先，Tushare 预留，Provider 可插拔 |

## 设计原则

- **契约先行**：`InfoCard`/`Decision`/`OrderIntent` schema + subject 命名空间是唯一跨进程接口
- **职责分离**：采集 Agent 只产卡片；决策大脑是唯一决策出口；执行 Agent 只负责下单
- **万物可插拔**：Provider / Broker / LLM / Bus 全部抽象可替换（mock ↔ 真实）
- **安全闸口**：MVP 仅模拟盘；任何真实下单前有 `require_manual_confirm` 人工确认

## 路线图

- **M0** 脚手架与内核契约（schema、bus、SQLite、CLI）
- **M1** ⭐ 垂直切片——全 Mock 跑通 调度器→Agent→决策→模拟执行
- **M2** 接入真实数据（AKShare）+ 真 LLM 决策 + 风控护栏
- **M3** PySide6 仪表盘（心跳、卡片流、决策日志、持仓）
- **M4** 加固：JetStream 持久化、幂等、死信、veto、自动重启

## 免责声明

本项目仅供研究与学习使用，不构成任何投资建议。交易有风险，真实下单必须经过人工确认。

## 许可证

[MIT](LICENSE)
