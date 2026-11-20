# Quant$warm

[简体中文](README.zh-CN.md)

**AI-assisted investment decision & quantitative analysis desktop system for Windows**, built on a multi-agent architecture powered by LLMs.

> Status: 🚧 early design phase — see [`docs/architecture.md`](docs/architecture.md) for the full MVP technical design.

## How it works

```
                    ┌─────────────────────────────────────────────────┐
 Scheduler ───────▶ │  Info Agents (data collection only, no decisions) │
 (APScheduler)      │   1. Market data      2. Fundamentals & industry  │
                    │   3. Capital flow     4. Event / anomaly monitor  │
                    └───────────────┬─────────────────────────────────┘
                                    │  standardized InfoCards
   Risk & Review Agents ────────────┼──────────▶ ┌──────────────┐
   (monitor & veto only)            │            │  AI Decision │
                                    └──────────▶ │    Brain     │
                                                 │ (only place  │
                                                 │  that decides)│
                                                 └──────┬───────┘
                                                       │ OrderIntent
                                              ┌────────▼────────┐
                                              │ Execution Agent │──▶ Paper broker (MVP)
                                              └─────────────────┘
```

All agents are **independent processes** communicating through a message bus — a single module failure never breaks the chain.

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

## Disclaimer

This project is for research and educational purposes only. It does not constitute investment advice. Trading involves risk; any real order requires manual confirmation.

## License

[MIT](LICENSE)
