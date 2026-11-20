# ADR-0001: MVP Technology Stack

- Status: Accepted
- Date: 2026-11-20
- Context: Phase-1 MVP design for Quant$warm, a Windows-first, multi-agent, LLM-powered investment decision assistant.

## Decisions

| Area | Decision | Alternatives rejected |
|---|---|---|
| Desktop UI | **PySide6** | PyQt6 (GPL/commercial license friction), Tauri (extra Rust toolchain), Electron (heavyweight, JS mismatch) |
| Agent messaging | **NATS Core + JetStream** behind a `MessageBus` interface, with an in-process `LocalBus` for tests | gRPC (poor fan-out), Redis Streams (Windows install burden), RabbitMQ (Erlang dep), SQLite polling (no real-time push) |
| Database | **SQLite (WAL) + Alembic** | Postgres/TimescaleDB (premature for a single-machine desktop app); DuckDB+Parquet kept as the time-series upgrade path |
| Scheduler | **APScheduler** with SQLite job store | cron/Task Scheduler (no persistence, no retry semantics), Celery (requires a broker we already get from NATS) |
| LLM access | **OpenAI-compatible client + named profiles**, fully user-configurable per consumer | Hard-wiring a single vendor; LangGraph (overkill for the single-step decision synthesis in MVP) |
| Market data | **AKShare first**, Tushare adapter interface reserved | Paid data APIs at MVP stage |

## Consequences

- All agents run as independent OS processes; the only shared dependency is `core/` (schemas + bus subjects + infra).
- JetStream gives us replay for free, which the future backtest engine reuses.
- A `LocalBus` implementation keeps unit tests and CI free of external services.
