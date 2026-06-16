from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import pandas as pd

# Candle history is a pandas DataFrame with columns:
#   ["ts", "open", "high", "low", "close", "volume"]
# sorted ascending by ts (UTC, tz-aware). The LAST row is the most recent CLOSED bar.


class Regime(str, Enum):
    UPTREND = "uptrend"
    NEUTRAL = "neutral"
    DOWNTREND = "downtrend"


class Side(str, Enum):
    LONG = "long"


class ExitReason(str, Enum):
    STOP = "stop"
    TAKE_PROFIT = "take_profit"
    TIME_CAP = "time_cap"
    END_OF_DATA = "end_of_data"


class DecisionCode(str, Enum):
    PAUSED = "PAUSED"
    HALTED = "HALTED"
    BROKER_POSITION_EXISTS = "BROKER_POSITION_EXISTS"
    RISK_BLOCKED = "RISK_BLOCKED"
    REGIME_BLOCKED = "REGIME_BLOCKED"
    SIGNAL_BELOW_THRESHOLD = "SIGNAL_BELOW_THRESHOLD"
    ATR_INVALID = "ATR_INVALID"
    SIZE_ZERO = "SIZE_ZERO"
    PORTFOLIO_BLOCKED = "PORTFOLIO_BLOCKED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_PENDING = "ORDER_PENDING"
    ENTERED = "ENTERED"
    ORDER_FAILED = "ORDER_FAILED"
    MANAGED_NO_EXIT = "MANAGED_NO_EXIT"
    EXIT_SUBMITTED = "EXIT_SUBMITTED"
    EXITED = "EXITED"
    PROBE_COMPLETE = "PROBE_COMPLETE"
    ERROR = "ERROR"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    NEW = "new"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELED = "canceled"
    EXPIRED = "expired"


@dataclass(frozen=True)
class DecisionResult:
    code: DecisionCode
    reason: str
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class BrokerOrder:
    order_id: str
    symbol: str
    side: OrderSide
    status: OrderStatus
    requested_qty: float
    filled_qty: float
    filled_avg_price: float | None
    client_order_id: str | None = None


@dataclass(frozen=True)
class PendingOrder:
    client_order_id: str
    broker_order_id: str | None
    symbol: str
    side: OrderSide
    submitted_at: datetime
    requested_qty: float
    stop: float
    tp: float
    max_hold_until: datetime
    score_at_entry: float
    regime_at_entry: Regime
    exit_reason: ExitReason | None = None
    observed_exit_price: float | None = None


@dataclass(frozen=True)
class MarketContext:
    """Everything a signal/regime needs, as of the last closed bar in `candles`."""
    candles: pd.DataFrame                      # primary trading timeframe
    benchmark: pd.DataFrame | None = None      # e.g. BTC/USD, same timeframe
    htf: pd.DataFrame | None = None            # higher timeframe for regime; falls back to candles


@dataclass(frozen=True)
class SignalResult:
    name: str
    score: float           # normalized 0..1 (higher = stronger long case)
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RegimeResult:
    regime: Regime
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ConfluenceResult:
    score: float                       # weighted sum of contributions
    threshold: float
    passed: bool
    contributions: dict[str, float]    # signal name -> score*weight
    signals: dict[str, SignalResult]   # raw per-signal results


@dataclass(frozen=True)
class EntrySignal:
    ts: datetime
    side: Side
    score: float
    regime: Regime
    meta: dict = field(default_factory=dict)


@dataclass
class OpenPosition:
    """A live open position, persisted by the StateStore."""
    symbol: str
    entry_ts: datetime
    entry_price: float
    qty: float
    stop: float
    tp: float
    max_hold_until: datetime
    score_at_entry: float
    regime_at_entry: Regime
    side: Side = Side.LONG
    entry_order_id: str | None = None
