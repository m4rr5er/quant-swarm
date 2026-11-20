# Quant$warm

[English](README.md)

**基于大模型 + 多智能体架构的 AI 投资辅助决策与量化分析 Windows 桌面系统**。

> 状态：双层编排已上线——你只和两个专家级决策 AI（investor / quant）对话，由它们指挥并验收 worker 流水线。完整设计见 [`docs/orchestration.md`](docs/orchestration.md)

## 工作链路

```
        你 ──────▶ Chat 页 / Telegram 网关
                          │ qs.chat.in
                    ┌─────▼──────┐
                    │   Router   │  关键词分流（复合任务双专家会签）
                    └─────┬──────┘
              ┌───────────┴────────────┐
              ▼                        ▼
        ┌───────────┐           ┌───────────┐
        │ investor  │           │   quant   │  专家人格 + 有界记忆
        │  决策专家  │           │  决策专家  │  工具循环 = 派发 + 验收
        └─────┬─────┘           └─────┬─────┘
              └───────────┬───────────┘
                          │ 工具：派发/读卡片、持仓/回测
        ┌─────────────────▼──────────────────────────────┐
        │              worker 流水线（对你黑盒）            │
        │  market_data · fundamentals · capital_flow ·    │
        │  event_monitor · brain · backtester · execution │
        └────────────────────────────────────────────────┘
                          │ 运行痕迹、死信、产出
                    ┌─────▼──────┐
                    │  learner   │  观察→反思→写记忆+技能提案
                    │            │  qs promote 人工晋升
                    └────────────┘
```

所有 Agent 均为**独立进程**，通过消息总线（NATS + JetStream）通信——单个模块故障不影响整体链路，重启自动补投积压消息。

## 快速上手

```bash
# 一次性安装
python -m venv ~/.venvs/quant-swarm && ~/.venvs/quant-swarm/bin/pip install -e .
cp .env.example .env          # 配 LLM_API_KEY_DEFAULT（要 TG 再加 QS_TG_TOKEN）
qs init-db && alembic upgrade head

# 日常：一条脚本拉起 nats + 全部组件
scripts/dev_all.sh            # 需要 ./deploy/bin/nats-server（scripts/fetch_nats.*）
qs run ui                     # 仪表盘——Chat 页就是你的对话台

# 无界面玩法
qs trigger chat "茅台现在能加仓吗"
qs trigger learn              # 手动跑一轮学习
qs promote quant              # 晋升一条技能提案
```

**Telegram**：`@BotFather` → `/newbot` → token 写进 `.env` 的 `QS_TG_TOKEN` → `configs/agents.yaml` 里 `im_telegram.enabled: true`——`dev_all.sh` 会自动带上它。

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
- **M5a** 决策 AI 层：双专家 + 分流器 + 会话 + 有界记忆
- **M5b** 会签协议 + 回测 worker + 工具循环加固
- **M5c** learner（观察→反思→写记忆+技能提案）+ Telegram 网关 + 学习页

## 免责声明

本项目仅供研究与学习使用，不构成任何投资建议。交易有风险，真实下单必须经过人工确认。

## 许可证

[MIT](LICENSE)
