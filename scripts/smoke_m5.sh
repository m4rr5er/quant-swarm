#!/usr/bin/env bash
# M5a smoke: chat router + two expert processes against nats_js.
set -u
cd "$(dirname "$0")/.."
PY="${PY:-$HOME/.venvs/quant-swarm/bin/python}"
export QS_BUS="${QS_BUS:-nats_js}"

setsid "$PY" -m quant_swarm.chat > logs/chat.log 2>&1 < /dev/null &
setsid "$PY" -m quant_swarm.experts investor > logs/investor.log 2>&1 < /dev/null &
setsid "$PY" -m quant_swarm.experts quant > logs/quant.log 2>&1 < /dev/null &
sleep 4
tail -n 3 logs/chat.log logs/investor.log logs/quant.log
