"""``python -m quant_swarm.agents.execution``"""

from quant_swarm.agents.execution.agent import ExecutionAgent
from quant_swarm.core.runtime import launch

launch(lambda bus, s, c: ExecutionAgent(bus, s, c), "execution")
