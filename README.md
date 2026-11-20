# Quant$warm

[简体中文](README.zh-CN.md)

**AI-assisted investment decision & quantitative analysis desktop system for Windows**, built on a multi-agent architecture powered by LLMs.

> Status: two-tier orchestration live — you talk to two expert decision-AIs (investor & quant), they command and verify the worker pipeline. See [`docs/orchestration.md`](docs/orchestration.md) for the design.

## How it works

```
        you ──────▶ Chat tab / Telegram gateway
                          │ qs.chat.in
                    ┌─────▼──────┐
                    │   Router   │  keyword classify (+co-sign on compound tasks)
                    └─────┬──────┘
              ┌───────────┴────────────┐
              ▼                        ▼
        ┌───────────┐           ┌───────────┐
        │ investor  │           │   quant   │   expert personas, bounded memory,
        │  expert   │           │  expert   │   tool loop = dispatch + verify
        └─────┬─────┘           └─────┬─────┘
              └───────────┬───────────┘
                          │ tools: dispatch / read cards,portfolio / backtest
        ┌─────────────────▼──────────────────────────────┐
        │              worker pipeline (black box)        │
        │  market_data · fundamentals · capital_flow ·    │
        │  event_monitor · brain · backtester · execution │
        └────────────────────────────────────────────────┘
                          │ traces, dead letters, outcomes
                    ┌─────▼──────┐
                    │  learner   │  observe → reflect → memory ops
                    │            │  + skill proposals → qs promote
                    └────────────┘
```

All agents are **independent processes** communicating through a message bus (NATS + JetStream) — a single module failure never breaks the chain, and restarts replay what was missed.

## Quick start

```bash
# one-time setup
python -m venv ~/.venvs/quant-swarm && ~/.venvs/quant-swarm/bin/pip install -e .
cp .env.example .env          # set LLM_API_KEY_DEFAULT (+ QS_TG_TOKEN for telegram)
qs init-db && alembic upgrade head

# daily: one script brings up nats + all components
scripts/dev_all.sh            # needs ./deploy/bin/nats-server (scripts/fetch_nats.*)
qs run ui                     # dashboard — Chat tab is your console

# or headless
qs trigger chat "茅台现在能加仓吗"
qs trigger learn              # force one learner cycle
qs promote quant              # promote a learner skill proposal
```

**Telegram**: `@BotFather` → `/newbot` → put the token in `.env` as `QS_TG_TOKEN` → set `im_telegram.enabled: true` in `configs/agents.yaml` — `dev_all.sh` picks it up automatically.

## Tech stack

| Layer | Choice |
|---|---|
| Desktop UI | PySide6 + qasync + pyqtgraph |
| Language | Python 3.12 |
| Agent messaging | NATS (Core + JetStream) behind a `MessageBus` abstraction |
| Database | SQLite (WAL) + Alembic → upgrade path: DuckDB/Parquet |
| Scheduler | APScheduler |
| LLM | OpenAI-compatible client, **fully user-configurable named profiles** — any provider or custom endpoint |
| Data sources | AKShare first, Tushare-ready, provider-pluggable |

## Design principles

- **Contract-first**: `InfoCard` / `Decision` / `OrderIntent` pydantic schemas + subject namespaces are the only cross-process interface
- **Separation of duties**: collection agents only produce standardized cards; the decision brain is the single decision outlet; the execution agent only places orders
- **Pluggable everything**: providers, brokers, LLMs, and the bus are all abstract + swappable (mock ↔ real)
- **Safety**: paper trading only in MVP; a `require_manual_confirm` gate sits in front of any real order

## Roadmap

- **M0** scaffolding & core contracts (schemas, bus, SQLite, CLI)
- **M1** ⭐ vertical slice — full mock loop: scheduler → agent → brain → paper execution
- **M2** real inputs (AKShare) + real LLM decisions + risk guardrails
- **M3** PySide6 dashboard (agent status, card feed, decision log, positions)
- **M4** hardening: JetStream persistence, idempotency, DLQ, vetoes, auto-restart
- **M5a** decision-AI layer: two experts + router + chat + bounded memory
- **M5b** co-sign protocol + backtester worker + tool-loop hardening
- **M5c** learner (observe→reflect→memory ops→skill proposals) + Telegram gateway + learning tab

## Disclaimer

This project is for research and educational purposes only. It does not constitute investment advice. Trading involves risk; any real order requires manual confirmation.

## License

[MIT](LICENSE)
