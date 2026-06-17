from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Action(str, Enum):
    ENTER_LONG = "enter_long"
    HOLD = "hold"
    EXIT = "exit"


@dataclass(frozen=True)
class Decision:
    action: Action
    confidence: float
    reason: str
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    qty: float
    entry_price: float
    stop: float
    tp: float
    max_hold_until: datetime
    reason: str


@dataclass
class EnginePosition:
    symbol: str
    entry_ts: datetime | None
    entry_price: float
    qty: float
    stop: float
    tp: float
    max_hold_until: datetime | None


@dataclass(frozen=True)
class JournalEvent:
    ts: datetime
    kind: str  # decision|order|fill|exit|pnl|killswitch|error
    symbol: str
    reason: str
    payload: dict = field(default_factory=dict)
