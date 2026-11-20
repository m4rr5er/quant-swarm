"""``python -m quant_swarm.agents.capital_flow``"""

from quant_swarm.agents.capital_flow.agent import CapitalFlowAgent
from quant_swarm.core.runtime import launch

launch(lambda bus, s, c: CapitalFlowAgent(bus, s, c), "capital_flow")
