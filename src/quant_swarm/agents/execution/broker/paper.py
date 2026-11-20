"""PaperBroker — instant simulated fills with a cash/position ledger in sqlite.

Fill rules (MVP):
- MARKET orders fill at the given price; LIMIT fills at limit price only.
- BUY needs ``qty*price <= cash``; SELL needs enough position.
- Positions track qty/avg_cost/realized_pnl; equity = cash + book value.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from quant_swarm.core.db.models import AccountRow, PositionRow
from quant_swarm.core.schemas import FillReport, FillStatus, OrderIntent, Side
from quant_swarm.core.timeutils import utcnow

from .base import Broker


class PaperBroker(Broker):
    name = "paper"

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        initial_cash: float = 1_000_000.0,
    ) -> None:
        self._sessions = sessions
        self._initial_cash = initial_cash

    async def place(self, order: OrderIntent, price: float | None) -> FillReport:
        if price is None or price <= 0:
            return self._fill(order, FillStatus.REJECTED, 0, 0.0, reason="no_price")
        async with self._sessions() as s:
            account = await self._account(s)
            if order.side is Side.BUY:
                if order.qty * price > account.cash:
                    return self._fill(
                        order, FillStatus.REJECTED, 0, 0.0, reason="insufficient_cash"
                    )
                await self._apply_buy(s, account, order.symbol, order.qty, price)
            else:
                pos = await self._position(s, order.symbol)
                if pos is None or pos.qty < order.qty:
                    return self._fill(
                        order, FillStatus.REJECTED, 0, 0.0, reason="insufficient_position"
                    )
                await self._apply_sell(s, account, pos, order.qty, price)
            account.updated_ts = utcnow()
            await s.commit()
            return self._fill(order, FillStatus.FILLED, order.qty, price)

    async def _account(self, s: AsyncSession) -> AccountRow:
        row = (
            await s.execute(select(AccountRow).where(AccountRow.account_id == "paper"))
        ).scalar_one_or_none()
        if row is None:
            row = AccountRow(
                account_id="paper",
                cash=self._initial_cash,
                equity=self._initial_cash,
                updated_ts=utcnow(),
            )
            s.add(row)
            await s.flush()
        return row

    async def _position(self, s: AsyncSession, symbol: str) -> PositionRow | None:
        return (
            await s.execute(select(PositionRow).where(PositionRow.symbol == symbol))
        ).scalar_one_or_none()

    async def _apply_buy(
        self, s: AsyncSession, account: AccountRow, symbol: str, qty: int, price: float
    ) -> None:
        pos = await self._position(s, symbol)
        if pos is None:
            pos = PositionRow(symbol=symbol, qty=0, avg_cost=0.0, updated_ts=utcnow())
            s.add(pos)
        pos.avg_cost = (pos.avg_cost * pos.qty + price * qty) / (pos.qty + qty)
        pos.qty += qty
        pos.updated_ts = utcnow()
        account.cash -= qty * price
        account.equity = account.cash + pos.qty * pos.avg_cost

    async def _apply_sell(
        self, s: AsyncSession, account: AccountRow, pos: PositionRow, qty: int, price: float
    ) -> None:
        pos.realized_pnl += (price - pos.avg_cost) * qty
        pos.qty -= qty
        if pos.qty == 0:
            pos.avg_cost = 0.0
        pos.updated_ts = utcnow()
        account.cash += qty * price
        account.equity = account.cash + pos.qty * pos.avg_cost

    def _fill(
        self, order: OrderIntent, status: FillStatus, qty: int, price: float, *, reason: str = ""
    ) -> FillReport:
        return FillReport(
            order_id=order.order_id,
            status=status,
            filled_qty=qty,
            avg_price=price,
            broker=self.name,
            meta={"reason": reason} if reason else {},
        )
