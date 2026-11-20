"""``python -m quant_swarm.agents.event_monitor``"""

from quant_swarm.agents.event_monitor.agent import EventMonitorAgent
from quant_swarm.core.runtime import launch

launch(lambda bus, s, c: EventMonitorAgent(bus, s, c), "event_monitor")
