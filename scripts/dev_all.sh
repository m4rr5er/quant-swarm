#!/usr/bin/env bash
# Dev smoke: nats-server + scheduler + agents + brain, all separate processes.
# Ctrl+C here only leaves the children running — kill them via the pkill line
# printed on exit, or close the terminals.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${PY:-$HOME/.venvs/quant-swarm/bin/python}"

./deploy/bin/nats-server -p 4222 &
PIDS=$!

"$PY" -m quant_swarm.scheduler &      PIDS="$PIDS $!"
"$PY" -m quant_swarm.agents.market_data & PIDS="$PIDS $!"
"$PY" -m quant_swarm.brain &          PIDS="$PIDS $!"
"$PY" -m quant_swarm.agents.execution &   PIDS="$PIDS $!"

echo "started pids: $PIDS"
echo "try:  qs trigger collect && qs trigger decide"
trap 'kill $PIDS 2>/dev/null || true' INT TERM
wait
