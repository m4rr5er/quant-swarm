"""``python -m quant_swarm.scheduler``"""

from quant_swarm.core.runtime import launch
from quant_swarm.scheduler.service import SchedulerService

launch(lambda bus, s, c: SchedulerService(bus, s, c), "scheduler")
