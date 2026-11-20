from quant_swarm.core.runtime import launch
from quant_swarm.im.telegram import TelegramGateway

launch(lambda b, s, c: TelegramGateway(b, s, c), "im_telegram")
