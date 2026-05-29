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
