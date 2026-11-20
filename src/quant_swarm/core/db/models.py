"""Operational store — cards, decisions, orders, fills, positions, agent & job state."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class InfoCardRow(Base):
    __tablename__ = "info_cards"

    card_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    symbols: Mapped[list] = mapped_column(JSON, default=list)
    asof: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ttl_sec: Mapped[int] = mapped_column(Integer, default=3600)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(128), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    trace_id: Mapped[str] = mapped_column(String(64), default="", index=True)


class DecisionRow(Base):
    __tablename__ = "decisions"

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    action: Mapped[str] = mapped_column(String(16))
    target_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    horizon: Mapped[str | None] = mapped_column(String(16), nullable=True)
    rationale: Mapped[str] = mapped_column(Text, default="")
    card_refs: Mapped[list] = mapped_column(JSON, default=list)
    llm: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    trace_id: Mapped[str] = mapped_column(String(64), default="", index=True)


class OrderRow(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    decision_id: Mapped[str] = mapped_column(String(64), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(8))
    qty: Mapped[int] = mapped_column(Integer)
    order_type: Mapped[str] = mapped_column(String(8))
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    tif: Mapped[str] = mapped_column(String(8), default="DAY")
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    trace_id: Mapped[str] = mapped_column(String(64), default="", index=True)


class FillRow(Base):
    __tablename__ = "fills"

    fill_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16))
    filled_qty: Mapped[int] = mapped_column(Integer)
    avg_price: Mapped[float] = mapped_column(Float)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    broker: Mapped[str] = mapped_column(String(32), default="paper")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    trace_id: Mapped[str] = mapped_column(String(64), default="", index=True)


class PositionRow(Base):
    __tablename__ = "positions"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    qty: Mapped[int] = mapped_column(Integer, default=0)
    avg_cost: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    updated_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgentStateRow(Base):
    __tablename__ = "agent_state"

    agent: Mapped[str] = mapped_column(String(64), primary_key=True)
    state: Mapped[str] = mapped_column(String(16))
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class JobRunRow(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_name: Mapped[str] = mapped_column(String(128), index=True)
    scheduled_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str] = mapped_column(String(64), default="", index=True)
