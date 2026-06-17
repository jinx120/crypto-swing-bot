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
    # Full Alpaca order lifecycle. Every status Alpaca can return must be a member
    # here: the broker serializer raises on any unknown status, and that exception
    # propagates through pending-order reconcile into auto-start — a single live
    # order sitting in a transient state (e.g. `pending_new`, which Alpaca paper
    # crypto buys can hold for hours) would otherwise take the whole bot down.
    # Only REJECTED/CANCELED/EXPIRED are treated as terminal failures
    # (see orchestrator._FAILED_ORDER_STATUSES); every other non-FILLED status is
    # treated as "still pending" and re-reconciled next cycle.
    NEW = "new"
    ACCEPTED = "accepted"
    PENDING_NEW = "pending_new"
    ACCEPTED_FOR_BIDDING = "accepted_for_bidding"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    DONE_FOR_DAY = "done_for_day"
    REPLACED = "replaced"
    PENDING_CANCEL = "pending_cancel"
    PENDING_REPLACE = "pending_replace"
    STOPPED = "stopped"
    SUSPENDED = "suspended"
    CALCULATED = "calculated"
    HELD = "held"
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
