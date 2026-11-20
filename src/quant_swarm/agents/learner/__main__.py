"""python -m quant_swarm.agents.learner — standalone process."""

from quant_swarm.agents.learner.agent import LearnerService
from quant_swarm.core.runtime import launch

launch(lambda b, s, c: LearnerService(b, s, c), "learner")
