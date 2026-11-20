"""Broker contract — one method: take an order + a reference price, return a fill."""

from __future__ import annotations

from abc import ABC, abstractmethod

from quant_swarm.core.schemas import FillReport, OrderIntent


class Broker(ABC):
    name: str = "broker"

    @abstractmethod
    async def place(self, order: OrderIntent, price: float | None) -> FillReport: ...
