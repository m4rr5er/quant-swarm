#!/usr/bin/env bash
# Dev smoke: nats-server (JetStream) + all enabled components, separate processes.
# Ctrl+C here only leaves the children running — kill them via the pkill line
# printed on exit, or close the terminals.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${PY:-$HOME/.venvs/quant-swarm/bin/python}"
export QS_BUS="${QS_BUS:-nats_js}"   # JetStream durability on by default

./deploy/bin/nats-server -p 4222 -js &
PIDS=$!

"$PY" -m quant_swarm.scheduler &          PIDS="$PIDS $!"
"$PY" -m quant_swarm.agents.market_data & PIDS="$PIDS $!"
"$PY" -m quant_swarm.agents.fundamentals &    PIDS="$PIDS $!"
"$PY" -m quant_swarm.agents.capital_flow &    PIDS="$PIDS $!"
"$PY" -m quant_swarm.agents.event_monitor &   PIDS="$PIDS $!"
"$PY" -m quant_swarm.brain &              PIDS="$PIDS $!"
"$PY" -m quant_swarm.agents.execution &   PIDS="$PIDS $!"
"$PY" -m quant_swarm.chat &               PIDS="$PIDS $!"
"$PY" -m quant_swarm.experts investor &   PIDS="$PIDS $!"
"$PY" -m quant_swarm.experts quant &      PIDS="$PIDS $!"

echo "started pids: $PIDS (QS_BUS=$QS_BUS)"
echo "try:  qs trigger collect --agent market_data && qs trigger decide && qs run ui"
trap 'kill $PIDS 2>/dev/null || true' INT TERM
wait
