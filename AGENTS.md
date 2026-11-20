# Agent Notes — Quant$warm

## Environment quirks (WSL2 + Windows host)

- The dev environment is **WSL2 Ubuntu 24.04**; the repo lives on the Windows
  filesystem at `C:\projects\devin_projects\quant-swarm`
  (`/mnt/c/projects/devin_projects/quant-swarm` inside WSL).
- `github.com` is blocked directly; `api.github.com` is reachable. Route git/gh
  through the Clash proxy on the Windows host:
  ```bash
  HOST_IP=$(ip route show default | awk '{print $3}')
  export https_proxy="http://$HOST_IP:7897" http_proxy="http://$HOST_IP:7897"
  ```
  (WSL NAT gateway IP — NOT `127.0.0.1`. Clash must have "Allow LAN" enabled.)
- `gh` (GitHub CLI) is installed at `~/.local/bin/gh` in WSL and is
  authenticated as `m4rr5er` (also registered as the credential helper for
  `https://github.com`).

## Git conventions

- **Commit author**: repo-local `user.name=m4rr5er`,
  `user.email=148053332+m4rr5er@users.noreply.github.com` (GitHub noreply).
  The global identity (work account) must NOT be used for this repo.
- `core.fileMode=false` is set locally (files live on DrvFs).
- **Commit messages**: English only, Conventional Commits style
  (`feat:`, `docs:`, `chore:`, ...).
- **Branching**: every plan/milestone gets its own branch — never commit
  feature work straight onto `main`. Open a PR for review.
  e.g. `docs/mvp-architecture`, `feat/m0-scaffolding`, `feat/m1-vertical-slice`.

## Verification

- Dev env lives in WSL: `~/.venvs/quant-swarm` (uv-managed venv, project
  installed editable with `[dev]` extras; `uv` at `~/.local/bin/uv`).
- Lint (whole repo, incl. alembic): `~/.venvs/quant-swarm/bin/ruff check .`
- Tests: `~/.venvs/quant-swarm/bin/python -m pytest -q`
- CLI smoke: `~/.venvs/quant-swarm/bin/qs info` / `qs init-db`
- Migrations: `alembic upgrade head` (sync driver; app runtime uses aiosqlite).
- **M1 live smoke** (real NATS, separate processes):
  `deploy/bin/nats-server -p 4222` (fetch via `scripts/fetch_nats.sh|ps1`),
  then `python -m quant_swarm.scheduler | .agents.market_data | .brain |
  .agents.execution` in four processes, and fire the loop with
  `qs trigger collect` + `qs trigger decide`. Results land in
  `data/quantswarm.db` and `logs/<agent>.log`.
- **JetStream mode**: `nats-server -js` + `QS_BUS=nats_js` — every AgentBase
  subscription becomes a durable consumer (`<agent>-<subject>`); publishes
  carry Nats-Msg-Id for stream dedup. `scripts/dev_all.sh` runs this by default.
- UI tests run offscreen: `QT_QPA_PLATFORM=offscreen pytest -q`.
  The dashboard itself (`qs run ui`) renders on Windows via WSLg.
