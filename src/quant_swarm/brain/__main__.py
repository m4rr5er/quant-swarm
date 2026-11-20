"""``python -m quant_swarm.brain``"""

from quant_swarm.brain.service import BrainService
from quant_swarm.core.runtime import launch

launch(lambda bus, s, c: BrainService(bus, s, c), "brain")
