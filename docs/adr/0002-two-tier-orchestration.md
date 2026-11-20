# ADR-0002: 两层多 Agent 编排与全 agent 自学习

## 状态

Proposed — 2026-11-20，与 `docs/orchestration.md` 配套。

## 背景

M0–M4 交付的是扁平 pub/sub 数据流：采集 → 卡片 → brain 决策 → 执行。无对话入口、无"指挥/验收"语义、无学习机制。用户要求：

1. 两点一线：用户只对接两个专家级决策 AI（投资、量化），专家指挥并验收 worker 团队
2. 全 agent 自学习（参考 hermes-agent 的记忆闭环、Harness² 的递归 harness 进化、nuwa-skill 的 persona 蒸馏、Raven 的 host+专家团队编排）

## 决策

- **双层编排**：新增 `investor`/`quant` 两个对话式专家组件（ExpertBase + 版本化 persona 文件），现有 M0–M4 组件原样降级为 worker 层；专家工具面全部映射到现有 bus/db，不引入新通信机制
- **Router 自动分流**，复合任务双专家会签（各自独立产出后合成，保留分歧标注）
- **验收闭环**：专家派发→验收（新鲜度/覆盖度/一致性/置信度）→不合格重派→组装结论；trace_id 贯穿可溯源
- **自学习三件套**：有界记忆文件（USER.md + experts/* + agents/*）、sessions/messages+FTS5 会话召回、skills/*.md 版本化进化
- **独立 Learner（Evolver）进程**统一做记忆固化、USER.md 仲裁、skill 提案+probe 晋升——学习闭环不内嵌进各 agent（借鉴 Raven "Evolver 与运行体分离"）
- **不引入外部编排框架**（LangGraph/CrewAI）；worker 不内嵌 LLM 反思
- 入口：dashboard Chat tab（M5a）→ IM 网关 Telegram（M5b）

## 备选方案及弃因

- 现有 brain 直接升级为对话专家：brain 的职责太窄（卡片→决策），与其让它膨胀为全能入口，不如新增专家层让它回归"策略执行器"——职责单一原则不变
- 每个 worker 自带 LLM 自反思：成本高、不可控；统一 learner 代笔更便宜且可审计
- 外部编排框架：引入框架会与 NATS 编排层重复，且把核心智能外包给黑盒

## 影响

- 新增：ExpertBase/RouterService/learner/im_gateway 进程；persona/memory/skills 目录；ChatMessage/ExpertTask/ReviewReport schema；sessions/messages/memories/skills/learning_reports 表
- 不变：全部 worker 契约、风控 veto、JetStream 管道
- 风险：专家验收质量依赖 persona 与 prompt 工程 → 以版本化 persona + skill 进化循环对冲；双写记忆腐烂 → learner 单入口仲裁
