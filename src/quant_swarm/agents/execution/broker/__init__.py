"""Broker adapters — paper for MVP, real brokers land much later."""

from quant_swarm.agents.execution.broker.base import Broker
from quant_swarm.agents.execution.broker.paper import PaperBroker

__all__ = ["Broker", "PaperBroker"]
