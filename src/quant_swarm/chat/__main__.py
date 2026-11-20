"""python -m quant_swarm.chat — standalone chat service process."""

from quant_swarm.chat.service import ChatService
from quant_swarm.core.runtime import launch

launch(lambda b, s, c: ChatService(b, s, c), "chat")
