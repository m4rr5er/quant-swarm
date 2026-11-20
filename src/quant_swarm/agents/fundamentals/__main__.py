"""``python -m quant_swarm.agents.fundamentals``"""

from quant_swarm.agents.fundamentals.agent import FundamentalsAgent
from quant_swarm.core.runtime import launch

launch(lambda bus, s, c: FundamentalsAgent(bus, s, c), "fundamentals")
