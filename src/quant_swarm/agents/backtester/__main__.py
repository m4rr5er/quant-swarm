"""python -m quant_swarm.agents.backtester — standalone process."""

from quant_swarm.agents.backtester.agent import BacktesterAgent
from quant_swarm.core.runtime import launch

launch(lambda b, s, c: BacktesterAgent(b, s, c), "backtester")
