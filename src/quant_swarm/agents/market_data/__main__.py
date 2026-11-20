"""``python -m quant_swarm.agents.market_data``"""

from quant_swarm.agents.market_data.agent import MarketDataAgent
from quant_swarm.core.runtime import launch

launch(lambda bus, s, c: MarketDataAgent(bus, s, c), "market_data")
