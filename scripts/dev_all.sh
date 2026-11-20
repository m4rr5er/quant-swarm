#!/usr/bin/env bash
# Dev run: nats-server (JetStream, persisted) + the full two-tier stack.
#
#   you -> Chat tab / Telegram -> router -> investor+quant -> workers
#
# Ctrl+C here only leaves the children running — kill them via the pkill
# line printed on exit, or close the terminals.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${PY:-$HOME/.venvs/quant-swarm/bin/python}"
export QS_BUS="${QS_BUS:-nats_js}"   # JetStream durability on by default
STORE="${NATS_STORE:-/tmp/nats-js-store}"
LOGS="$ROOT/logs"; mkdir -p "$LOGS" "$STORE"

./deploy/bin/nats-server -p 4222 -js -sd "$STORE" > "$LOGS/nats.log" 2>&1 &
PIDS=$!

# wait for the bus before launching subscribers (durable binding fails
# against a half-up server)
for _ in $(seq 1 30); do
  (echo > /dev/tcp/127.0.0.1/4222) 2>/dev/null && break
  sleep 0.5
done

start() {  # start <logname> <module> [args...]
  local name="$1"; shift
  "$PY" -m "$@" > "$LOGS/$name.log" 2>&1 &
  PIDS="$PIDS $!"
  echo "  $name (pid $!)"
}

echo "starting components (QS_BUS=$QS_BUS):"
start scheduler     quant_swarm.scheduler
start market_data   quant_swarm.agents.market_data
start fundamentals  quant_swarm.agents.fundamentals
start capital_flow  quant_swarm.agents.capital_flow
start event_monitor quant_swarm.agents.event_monitor
start brain         quant_swarm.brain
start execution     quant_swarm.agents.execution
start backtester    quant_swarm.agents.backtester
start chat          quant_swarm.chat
start investor      quant_swarm.experts investor
start quant         quant_swarm.experts quant
start learner       quant_swarm.agents.learner

# telegram gateway only when a token is configured
if [ -n "${QS_TG_TOKEN:-}" ] || grep -qs '^QS_TG_TOKEN=.' .env 2>/dev/null; then
  start im_telegram quant_swarm.im
else
  echo "  im_telegram skipped (no QS_TG_TOKEN)"
fi

cat <<'HINTS'

── quick start ────────────────────────────────────────────────
  qs run ui                                  dashboard + Chat tab
  qs trigger chat "帮我回测茅台的双均线策略"    headless chat
  qs trigger collect                         market data now
  qs trigger decide                          brain pass now
  qs trigger learn                           one learner cycle now
  qs promote <agent>                         promote a skill proposal
  logs: tail -f logs/<component>.log
  stop: pkill -f 'quant_swarm|nats-server'
───────────────────────────────────────────────────────────────
HINTS

echo "pids: $PIDS"
trap 'kill $PIDS 2>/dev/null || true' INT TERM
wait
