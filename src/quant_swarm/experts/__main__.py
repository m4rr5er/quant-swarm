"""python -m quant_swarm.experts <investor|quant> — expert process."""

import sys

from quant_swarm.core.runtime import launch
from quant_swarm.experts.base import ExpertService

name = sys.argv[1] if len(sys.argv) > 1 else "investor"


def factory(b, s, c):
    return ExpertService(b, s, c, expert_name=name)


factory.__name__ = name
launch(factory, name)
