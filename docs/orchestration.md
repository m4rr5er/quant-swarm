# Quant$warm — 两层多 Agent 编排与自学习设计（M5+）

> 状态：草案 v1（待评审）。本文为 `architecture.md` 的增补篇，规定"用户 ↔ 决策 AI ↔ AI 工作团队"的两层编排模型与全 agent 自学习机制。M0–M4 已交付的底层管道（bus/contracts/db/UI/加固）保持不变，本文只在其上加层。

## 1. 目标交互模型

```
                    你（唯一对话入口）
             ┌────────┴────────┐
             │   Router 分流    │   ← 自动判断任务归属；复合任务双专家会签
      ┌──────┴──────┐   ┌──────┴──────┐
      │ 投资决策专家 │   │  量化专家    │   ← 唯二的对话接口，专家级 persona
      │  investor   │   │   quant     │
      └──────┬──────┘   └──────┬──────┘
             │  下任务 + 验收    │        ← dispatch → review → compose
   ┌─────────┴─────────────────┴─────────┐
   │        AI 工作团队（对用户黑盒）       │
   │ market_data fundamentals capital    │
   │ event_monitor brain execution       │
   │ risk_review backtester(新) ...      │
   └─────────────────────────────────────┘
      底层：NATS(JetStream) + SQLite + PySide6 UI —— 已就绪
```

原则：

- **两点一线**：用户只面对两位专家。工作团队的存在、分工、重试、降级对用户透明。
- **专家下任务且验收**：专家不只是转发 worker 输出——先验收（数据新鲜度/覆盖度/置信度交叉验证），不合格就重派或明确降级说明，合格才组装结论。
- **现有组件不动**：M0–M4 的 7 个进程原样保留，成为 worker 层。`brain` 由"唯一决策出口"调整为量化专家手下的策略执行器。

## 2. 专家层（experts）

### 2.1 组件

| 组件 | llm_profile | 职责域 |
|---|---|---|
| `investor` | 强模型档案 | 买什么、何时买、仓位、风险敞口、组合观点 |
| `quant` | 强模型档案 | 策略、参数、回测、执行方式、信号质量 |

每个专家 = `ExpertBase`（新基类，含 persona 装配 + 工具面 + 验收循环 + 记忆读写）+ 一份 `persona/<name>.md`。

### 2.2 专家人格（nuwa-skill 式蒸馏）

`persona/investor.md` / `persona/quant.md` 是版本化的专家定义文件（git 跟踪，改动走 PR），内容四段：

1. **心智模型**：该角色如何看世界（如 investor：宏观→行业→个股三层过滤，先风险后收益）
2. **决策启发式**：何时 BUY/ADD/REDUCE/SELL/HOLD 的判断框架，权重上限纪律
3. **验收清单**：对 worker 产出的检查项（卡片新鲜度、指标一致性、异常值）
4. **表达风格**：给用户的报告格式与口吻（可随 USER.md 学习演化）

### 2.3 工具面（专家对 worker 的接口）

专家的工具全部映射到现有基础设施，不引入新通信机制：

| 工具 | 实现 |
|---|---|
| `dispatch_collect(agent)` | 发 `qs.ctrl.collect.<agent>`，等待卡片落库后返回摘要 |
| `trigger_decide` | 发 `qs.ctrl.decide` |
| `read_cards(symbols, kind, since)` | 查 info_cards 表（含 payload） |
| `read_portfolio` | positions + account + 最近 fills |
| `read_risk_events(since)` | 风控事件流 |
| `run_backtest(strategy, params)` | 派给 backtester worker（新组件，M5b） |
| `memory(action, entry)` | 读写自己的记忆文件（见 §4） |
| `session_search(query)` | FTS5 检索历史会话 |
| `ask_peer(question)` | 向另一位专家发 `qs.expert.<peer>`，用于会签 |

任务派发以 `trace_id` 贯穿：专家产出一份 `task_trace`，它派发的所有 ctrl 消息共享该 trace——最终报告可展示"这个结论用了哪些卡片/决策/成交"的完整溯源链（dashboard 已具备卡片详情能力）。

### 2.4 验收循环（acceptance）

`ExpertBase.act()` 主循环：

```
1. 理解任务 → 拆成 worker 派发计划（可能多轮）
2. dispatch → 收集产出（卡片/决策/回测结果）
3. 验收（persona 清单驱动）：
   - 新鲜度：卡片 asof 是否在 TTL 内、行情是否当日
   - 覆盖度：任务要求的 symbol/字段是否齐全
   - 一致性：多个数据源是否矛盾（如收盘价 vs 资金流日期错位）
   - 置信度：卡片 confidence、LLM confidence 是否低于阈值
4. 不合格 → 重派（带不同参数/换 provider/扩 symbol），最多 N 轮，仍不行 → 在报告里明确降级说明
5. 合格 → 组装结论 → 写会话 → （必要时）记忆固化
```

这与 Harness² 的 task-level recursion 同构：propose（派发计划）→ probe（收集产出）→ compose（验收+合成），只不过 probe 的目标是真实数据而非评估集。

## 3. Router 与会签

`RouterService`（轻量进程，也可并入 chat 网关）：

```
user msg --> router --> classify(msg)
              ├─ domain=investment -> investor 单独处理
              ├─ domain=quant      -> quant 单独处理
              └─ compound          -> 双专家会签：
                      investor.analyze(task) ─┐
                      quant.analyze(task)    ─┴─> synthesize(两份意见) -> 一份结论给你
```

- 分类器：规则关键词先行（回测/参数/策略→quant；买入/仓位/持有→investor），不确定时走一个便宜 LLM 档案兜底。分类结果记会话，供 USER.md 学习用户提问习惯。
- **会签协议**：复合任务两位专家各自独立产出意见（互不污染上下文），由发起方（router 指定主责专家，或第三位轻量 synthesizer 提示词）合并为单一结论——保留双方分歧点在报告中显式标注，不强行统一。

## 4. 自学习层（全 agent，hermes 三件套 + 进化器）

### 4.1 记忆文件（有界、自管理）

```
memory/
  USER.md                  # 你的画像：风险偏好、习惯板块、报告风格偏好、反馈模式（~1.5k字）
  experts/
    investor.md            # investor 的工作笔记：你的组合观点历史、常用判断框架
    quant.md               # quant 的工作笔记：策略偏好、踩过的坑
  agents/
    market_data.md         # worker 操作性知识：某接口的数据习性、字段坑、重试经验
    fundamentals.md ...
```

- 每个记忆文件**有字符上限**（hermes 模式）：写不下时 agent 自己合并/删减条目——防止无限膨胀稀释注意力。
- 记忆在**会话开始**时注入该组件的 system prompt（专家）或运行参数构造（worker）；会话中的写入即时落盘但下次会话才进 prompt（保住前缀缓存）。
- `USER.md` 全局共享：两位专家都能读，写入经 Learner 仲裁避免双写冲突（见 4.3）。

### 4.2 会话沉淀与召回

新增表：`sessions` / `messages`（会话与逐条消息，含 role、expert、trace_id）+ FTS5 虚表 `messages_fts`。

- 每次对话完整落库；`session_search(query)` 工具给专家跨会话召回能力。
- dashboard 会话历史可直接浏览；trace_id 把"这句话 → 那次派发 → 那些卡片/成交"串起来。

### 4.3 Learner（进化器，关键组件）

借鉴 Raven 的 **Evolver 与运行体分离**（"develops the agents rather than running inside them"）：学习闭环不做在每个 agent 内部硬编码，而是一个独立的 `learner` 进程定时/事件驱动地跑反思：

```
触发：定时（每日复盘）| 会话结束 | 显著事件（veto、连续错误、用户纠正）
工作：
  1. 扫描近期：会话记录、worker 心跳/错误指标、DLQ、决策-成交一致性
  2. 提炼事实与偏好 → 写 USER.md / memory/experts/* / memory/agents/*
     （USER.md 冲突由 learner 单一入口合并，避免双写腐烂）
  3. 发现可复用流程 → 起草 skill 改进提案（见 4.4）
  4. 产出"学习报告"卡片（InfoCard kind=review 或直接写学习报告表）→ dashboard 可见
```

worker（非 LLM 进程）的"学习"由 learner 代笔：它观察 worker 的运行痕迹，把可复用的操作性知识写进 `memory/agents/<name>.md`；worker 在下次启动/下一轮任务时读取（作为参数构造或说明文档）。

### 4.4 技能进化（Harness² 精简版）

```
skills/<agent>/<skill>.md    # 版本化技能文件（git 跟踪）
```

循环（learner 驱动）：

1. **Propose**：根据近期表现起草 skill/persona/param 改进提案（LLM 起草 + diff 形式）
2. **Probe**：在用例集上跑对照（近期 N 条真实任务的回放 + 一小组断言：如"茅台加仓问题应引用资金流卡片"）。低风险改进（文案/阈值微调）可直接 A/B，高风险（persona/策略逻辑）需用户确认
3. **Compose/Promote**：达标 → 晋升为新版本（git commit + skills 表记录 eval 分）；不达标 → 归档提案留档

`skills` 表：name, agent, version, status(candidate/active/retired), eval_score, proposal_trace。

## 5. 交互入口

### 5.1 Dashboard Chat tab（首选落点）

PySide6 新增 Chat 页：消息流 + 专家徽标（哪条是 investor/quant/会签合成）+ 可展开溯源（消息附带的 task_trace → 卡片/决策/成交链接）。输入即发 `qs.chat.in`。

### 5.2 IM 网关（第二期）

`im_gateway` 独立进程：`IM <-> qs.chat.*` 双向桥。Telegram 首选（bot API 简单、可走 clash 代理；企业微信/钉钉留接口位）。会话与 dashboard 共用一个 session 存储——手机上继续电脑上的对话。

## 6. 消息与契约增量

```
qs.chat.in            ChatMessage{user->router}      # 用户输入
qs.chat.out.<chan>    ChatMessage{expert->user}      # chan: dashboard | telegram
qs.expert.<name>      ExpertTask{sender, task, trace}# 专家间会签/委派
qs.dlq.*              （已有）
新 schema：ChatMessage / ExpertTask / ReviewReport（learner 学习报告）
新表：sessions / messages(+FTS5) / memories(entries 持久化) / skills / learning_reports
```

worker 侧契约不变——它们仍然只懂卡片与 ctrl；所有"编排智能"集中在专家层，符合单层升级、不动管道的原则。

## 7. 里程碑拆分

- **M5a 对话底座**：ChatMessage/ExpertTask schema、sessions/messages+FTS5 表、RouterService（规则版）、ExpertBase（persona 注入 + 工具面 + 验收循环）、investor+quant 两个 persona v1、dashboard Chat tab、memory 文件机制（读写+有界+注入）
- **M5b 会签 + 回测**：会签协议与合成、backtester worker（向量化回放，吃 mock/akshare 数据）、IM 网关（Telegram）
- **M5c 学习闭环**：learner 进程（记忆固化+USER.md 仲裁+skill 提案）、技能进化 probe 循环、dashboard 学习页（记忆/技能/报告可视化）

每步结束都保持系统可运行：M5a 落地后就能在聊天页里下任务拿到两位专家的真实回答（验收循环+记忆已生效）。

## 8. 与参考项目的对应

| 借鉴 | 落到 Quant$warm |
|---|---|
| Raven：Host Agent + 专家团队 + DAG 编排 | 专家派发计划内部就是小型 DAG（并行采集→汇总）；worker 表=Raven worker table |
| Harness²：task-level Propose-Probe-Compose | 专家验收循环；harnessing-level recursion → learner 的技能进化 |
| nuwa-skill：蒸馏思维为 skill/persona | persona/*.md 四段式专家定义 + skills/*.md 可进化技能 |
| hermes-agent：MEMORY/USER.md 有界记忆 + session FTS + 学习闭环 | §4 全量对应；冻结快照注入模式照搬 |

## 9. 不做的事（本设计明确排除）

- 不引入 LangGraph/CrewAI 等外部编排框架——bus 已是编排层，专家逻辑留在自家代码里可控可测
- worker 不内嵌 LLM 反思（成本与复杂度）——由 learner 统一代笔
- 真实下单通道仍由 require_manual_confirm 闸死；专家输出止于建议+纸面执行
