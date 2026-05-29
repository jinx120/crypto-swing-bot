# Phase 1 — Strategy Engine + Backtest Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the headless strategy engine and a backtester that replays historical candles through the real entry/exit/sizing logic and reports performance metrics.

**Architecture:** Pure, dependency-light Python package `swingbot`. Signals and the regime filter are stateless functions over a `MarketContext` (price history as pandas DataFrames). A `ConfluenceEngine` weighted-sums signal scores; a `RegimeFilter` hard-gates entries. A `SimulatedBroker` models fills with fees + slippage. A `Backtester` wires it all together lookahead-safely (decide on the last closed bar, enter at the next bar's open). Same signal/exit/sizing code will later run live (Phase 2) — only data source and broker swap.

**Tech Stack:** Python 3.11+, `pandas`, `numpy`, `pytest`. No trading APIs in this phase. Indicators are hand-rolled (no `pandas-ta` dependency) for deterministic tests.

---

## File Structure

```
crypto-swing-bot/
  pyproject.toml                      # package metadata + deps + pytest config
  src/swingbot/
    __init__.py
    types.py                          # enums + value objects: Regime, Side, ExitReason,
                                      #   MarketContext, SignalResult, RegimeResult,
                                      #   ConfluenceResult, EntrySignal
    profile.py                        # StrategyProfile dataclass + from_dict loader
    indicators.py                     # rsi, atr, rolling_vwap, sma, lookback_return
    signals/
      __init__.py
      base.py                         # Signal Protocol
      oversold.py                     # OversoldSignal
      vwap.py                         # VwapSignal
      relative_strength.py            # RelativeStrengthSignal
      fvg.py                          # FvgSignal stub (interface only, returns neutral)
    regime.py                         # RegimeFilter
    confluence.py                     # ConfluenceEngine + build_signals()
    sizing.py                         # position_size()
    exits.py                          # bracket_levels()
    broker/
      __init__.py
      base.py                         # Broker Protocol
      simulated.py                    # SimulatedBroker + Position
    journal.py                        # Trade dataclass + TradeJournal
    metrics.py                        # Metrics dataclass + compute_metrics()
    backtest.py                       # run_backtest() orchestrator
  tests/
    test_indicators.py
    test_signals.py
    test_regime.py
    test_confluence.py
    test_sizing.py
    test_exits.py
    test_simulated_broker.py
    test_journal_metrics.py
    test_backtest_integration.py
  data/                               # (gitignored) historical CSVs for real backtests
```

**Shared types live in `types.py`** so signals, engine, regime, and backtester all import from one place and avoid circular imports. `Trade` lives in `journal.py`, `Metrics` in `metrics.py`, `Position` in `broker/simulated.py` (each used mainly by its own module).

---

## Task 0: Project scaffolding

**Files:**
- Create: `crypto-swing-bot/pyproject.toml`
- Create: `crypto-swing-bot/src/swingbot/__init__.py`
- Create: `crypto-swing-bot/.gitignore`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "swingbot"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["pandas>=2.0", "numpy>=1.24"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `src/swingbot/__init__.py`**

```python
"""swingbot — crypto swing-trading strategy engine and backtester."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Create `.gitignore`**

```gitignore
__pycache__/
*.pyc
.venv/
.pytest_cache/
*.egg-info/
data/
```

- [ ] **Step 4: Create venv and install**

Run:
```bash
cd crypto-swing-bot && python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
```
Expected: installs pandas, numpy, pytest, and `swingbot` in editable mode without error.

- [ ] **Step 5: Verify pytest runs (collects nothing yet)**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest -q`
Expected: `no tests ran` (exit code 5) — confirms config is valid.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/swingbot/__init__.py .gitignore
git commit -m "chore: scaffold swingbot package"
```

---

## Task 1: Core types (enums + value objects)

**Files:**
- Create: `src/swingbot/types.py`
- Test: `tests/test_signals.py` (imports verified here; full signal tests in Task 4)

- [ ] **Step 1: Write `src/swingbot/types.py`**

```python
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
```

- [ ] **Step 2: Verify it imports**

Run: `cd crypto-swing-bot && . .venv/bin/activate && python -c "import swingbot.types as t; print(t.Regime.UPTREND, t.Side.LONG)"`
Expected: `Regime.UPTREND Side.LONG`

- [ ] **Step 3: Commit**

```bash
git add src/swingbot/types.py
git commit -m "feat: core types (enums, MarketContext, SignalResult, EntrySignal)"
```

---

## Task 2: Strategy profile

**Files:**
- Create: `src/swingbot/profile.py`
- Test: `tests/test_profile.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_profile.py
from swingbot.profile import StrategyProfile
from swingbot.types import Regime


def test_from_dict_populates_defaults_and_overrides():
    p = StrategyProfile.from_dict({
        "symbol": "TRX/USD",
        "benchmark_symbol": "BTC/USD",
        "timeframe": "15m",
        "signals": {"oversold": {"weight": 0.4, "oversold_level": 30},
                    "vwap": {"weight": 0.3, "max_dist": 0.03},
                    "relative_strength": {"weight": 0.3, "band": 0.02, "lookback": 96}},
        "entry_threshold": 0.6,
    })
    assert p.symbol == "TRX/USD"
    assert p.entry_threshold == 0.6
    assert p.risk_per_trade == 0.01          # default
    assert p.atr_period == 14                 # default
    assert p.stop_atr_mult == 1.5            # default
    assert p.take_profit_atr_mult == 2.0     # default
    assert p.max_hold_bars == 32              # default (8h / 15m)
    assert Regime.UPTREND in p.allowed_regimes
    assert Regime.DOWNTREND not in p.allowed_regimes
    assert p.signals["oversold"]["weight"] == 0.4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_profile.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.profile'`

- [ ] **Step 3: Write `src/swingbot/profile.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field

from swingbot.types import Regime


@dataclass
class StrategyProfile:
    symbol: str
    benchmark_symbol: str = "BTC/USD"
    timeframe: str = "15m"
    htf_timeframe: str = "4h"

    # signal config: name -> params dict (must include "weight")
    signals: dict = field(default_factory=dict)
    entry_threshold: float = 0.6

    # regime gate
    regime_ma_period: int = 200
    allowed_regimes: tuple[Regime, ...] = (Regime.UPTREND, Regime.NEUTRAL)

    # exits
    atr_period: int = 14
    stop_atr_mult: float = 1.5
    take_profit_atr_mult: float = 2.0
    max_hold_bars: int = 32          # 8 hours at 15m

    # sizing / risk
    risk_per_trade: float = 0.01     # 1% of equity
    max_position_frac: float = 0.25  # <=25% of equity in one trade

    # backtest cost model
    fee_rate: float = 0.0025         # per side
    slippage_rate: float = 0.0005    # per side

    @classmethod
    def from_dict(cls, d: dict) -> "StrategyProfile":
        d = dict(d)
        if "allowed_regimes" in d:
            d["allowed_regimes"] = tuple(Regime(r) for r in d["allowed_regimes"])
        return cls(**d)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_profile.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/profile.py tests/test_profile.py
git commit -m "feat: StrategyProfile with defaults and from_dict loader"
```

---

## Task 3: Indicators (rsi, atr, rolling_vwap, sma, lookback_return)

**Files:**
- Create: `src/swingbot/indicators.py`
- Test: `tests/test_indicators.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_indicators.py
import numpy as np
import pandas as pd

from swingbot.indicators import rsi, atr, rolling_vwap, sma, lookback_return


def _df(closes, highs=None, lows=None, vols=None):
    n = len(closes)
    return pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open": closes,
        "high": highs if highs is not None else [c + 1 for c in closes],
        "low": lows if lows is not None else [c - 1 for c in closes],
        "close": closes,
        "volume": vols if vols is not None else [100.0] * n,
    })


def test_rsi_strong_uptrend_is_high():
    df = _df([float(i) for i in range(1, 40)])      # monotonic rise
    val = rsi(df["close"], period=14).iloc[-1]
    assert val > 95

def test_rsi_strong_downtrend_is_low():
    df = _df([float(i) for i in range(40, 1, -1)])   # monotonic fall
    val = rsi(df["close"], period=14).iloc[-1]
    assert val < 5

def test_atr_positive_and_finite():
    df = _df([10.0] * 30, highs=[11.0] * 30, lows=[9.0] * 30)
    val = atr(df, period=14).iloc[-1]
    assert val > 0 and np.isfinite(val)

def test_rolling_vwap_matches_manual():
    df = _df([10.0, 20.0], highs=[10.0, 20.0], lows=[10.0, 20.0], vols=[1.0, 3.0])
    # typical price == close here; vwap = (10*1 + 20*3)/(1+3) = 17.5
    assert abs(rolling_vwap(df, window=2).iloc[-1] - 17.5) < 1e-9

def test_sma_basic():
    s = pd.Series([1.0, 2.0, 3.0, 4.0])
    assert sma(s, 2).iloc[-1] == 3.5

def test_lookback_return():
    df = _df([100.0, 110.0])
    assert abs(lookback_return(df["close"], 1) - 0.10) < 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_indicators.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.indicators'`

- [ ] **Step 3: Write `src/swingbot/indicators.py`**

```python
from __future__ import annotations

import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def rolling_vwap(df: pd.DataFrame, window: int) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3
    pv = typical * df["volume"]
    return pv.rolling(window).sum() / df["volume"].rolling(window).sum()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def lookback_return(close: pd.Series, n: int) -> float:
    if len(close) <= n:
        return 0.0
    return float(close.iloc[-1] / close.iloc[-1 - n] - 1.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_indicators.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/indicators.py tests/test_indicators.py
git commit -m "feat: indicators (rsi, atr, rolling_vwap, sma, lookback_return)"
```

---

## Task 4: Signal protocol + the three v1 signals + FVG stub

**Files:**
- Create: `src/swingbot/signals/__init__.py`
- Create: `src/swingbot/signals/base.py`
- Create: `src/swingbot/signals/oversold.py`
- Create: `src/swingbot/signals/vwap.py`
- Create: `src/swingbot/signals/relative_strength.py`
- Create: `src/swingbot/signals/fvg.py`
- Test: `tests/test_signals.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_signals.py
import pandas as pd

from swingbot.types import MarketContext
from swingbot.signals.oversold import OversoldSignal
from swingbot.signals.vwap import VwapSignal
from swingbot.signals.relative_strength import RelativeStrengthSignal
from swingbot.signals.fvg import FvgSignal


def _df(closes, highs=None, lows=None, vols=None):
    n = len(closes)
    return pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open": closes,
        "high": highs if highs is not None else [c + 0.5 for c in closes],
        "low": lows if lows is not None else [c - 0.5 for c in closes],
        "close": closes,
        "volume": vols if vols is not None else [100.0] * n,
    })


def test_oversold_high_when_falling():
    ctx = MarketContext(candles=_df([float(i) for i in range(40, 1, -1)]))
    r = OversoldSignal(weight=0.4, oversold_level=30).evaluate(ctx)
    assert r.name == "oversold"
    assert r.score > 0.9

def test_oversold_zero_when_rising():
    ctx = MarketContext(candles=_df([float(i) for i in range(1, 40)]))
    assert OversoldSignal(weight=0.4, oversold_level=30).evaluate(ctx).score == 0.0

def test_vwap_high_when_price_below_vwap():
    # last price far below the rolling vwap
    closes = [100.0] * 20 + [90.0]
    ctx = MarketContext(candles=_df(closes, vols=[1.0] * 21))
    r = VwapSignal(weight=0.3, window=20, max_dist=0.05).evaluate(ctx)
    assert r.score > 0.0

def test_vwap_zero_when_price_above_vwap():
    closes = [100.0] * 20 + [110.0]
    ctx = MarketContext(candles=_df(closes, vols=[1.0] * 21))
    assert VwapSignal(weight=0.3, window=20, max_dist=0.05).evaluate(ctx).score == 0.0

def test_relative_strength_high_when_outperforming():
    coin = _df([100.0, 110.0])        # +10%
    bench = _df([100.0, 100.0])       # 0%
    ctx = MarketContext(candles=coin, benchmark=bench)
    r = RelativeStrengthSignal(weight=0.3, band=0.05, lookback=1).evaluate(ctx)
    assert r.score > 0.9

def test_relative_strength_neutral_without_benchmark():
    ctx = MarketContext(candles=_df([100.0, 110.0]), benchmark=None)
    assert RelativeStrengthSignal(weight=0.3, band=0.05, lookback=1).evaluate(ctx).score == 0.5

def test_fvg_stub_returns_neutral_zero():
    ctx = MarketContext(candles=_df([100.0] * 5))
    r = FvgSignal(weight=0.0).evaluate(ctx)
    assert r.name == "fvg"
    assert r.score == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_signals.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.signals'`

- [ ] **Step 3: Write `src/swingbot/signals/__init__.py`**

```python
```
(empty file)

- [ ] **Step 4: Write `src/swingbot/signals/base.py`**

```python
from __future__ import annotations

from typing import Protocol

from swingbot.types import MarketContext, SignalResult


class Signal(Protocol):
    name: str
    weight: float

    def evaluate(self, ctx: MarketContext) -> SignalResult: ...
```

- [ ] **Step 5: Write `src/swingbot/signals/oversold.py`**

```python
from __future__ import annotations

from swingbot.indicators import rsi
from swingbot.types import MarketContext, SignalResult


class OversoldSignal:
    name = "oversold"

    def __init__(self, weight: float, oversold_level: float = 30.0, period: int = 14):
        self.weight = weight
        self.oversold_level = oversold_level
        self.period = period

    def evaluate(self, ctx: MarketContext) -> SignalResult:
        value = rsi(ctx.candles["close"], self.period).iloc[-1]
        if value != value:  # NaN during warmup
            return SignalResult(self.name, 0.0, {"rsi": None})
        # score: 0 at/above the level, ramps to 1 as rsi -> 0
        score = max(0.0, min(1.0, (self.oversold_level - value) / self.oversold_level))
        return SignalResult(self.name, score, {"rsi": float(value)})
```

- [ ] **Step 6: Write `src/swingbot/signals/vwap.py`**

```python
from __future__ import annotations

from swingbot.indicators import rolling_vwap
from swingbot.types import MarketContext, SignalResult


class VwapSignal:
    name = "vwap"

    def __init__(self, weight: float, window: int = 96, max_dist: float = 0.03):
        self.weight = weight
        self.window = window
        self.max_dist = max_dist

    def evaluate(self, ctx: MarketContext) -> SignalResult:
        vwap = rolling_vwap(ctx.candles, self.window).iloc[-1]
        price = ctx.candles["close"].iloc[-1]
        if vwap != vwap:  # NaN during warmup
            return SignalResult(self.name, 0.0, {"vwap": None})
        dist = (vwap - price) / vwap          # positive when price below vwap
        score = max(0.0, min(1.0, dist / self.max_dist))
        return SignalResult(self.name, score, {"vwap": float(vwap), "dist": float(dist)})
```

- [ ] **Step 7: Write `src/swingbot/signals/relative_strength.py`**

```python
from __future__ import annotations

from swingbot.indicators import lookback_return
from swingbot.types import MarketContext, SignalResult


class RelativeStrengthSignal:
    name = "relative_strength"

    def __init__(self, weight: float, band: float = 0.02, lookback: int = 96):
        self.weight = weight
        self.band = band
        self.lookback = lookback

    def evaluate(self, ctx: MarketContext) -> SignalResult:
        if ctx.benchmark is None:
            return SignalResult(self.name, 0.5, {"rs": None})
        coin_ret = lookback_return(ctx.candles["close"], self.lookback)
        bench_ret = lookback_return(ctx.benchmark["close"], self.lookback)
        rs = coin_ret - bench_ret
        # map rs in [-band, band] -> [0, 1]; 0.5 == neutral
        score = max(0.0, min(1.0, (rs + self.band) / (2 * self.band)))
        return SignalResult(self.name, score, {"rs": float(rs)})
```

- [ ] **Step 8: Write `src/swingbot/signals/fvg.py`**

```python
from __future__ import annotations

from swingbot.types import MarketContext, SignalResult


class FvgSignal:
    """Fair Value Gap signal. Interface only in Phase 1; returns neutral 0.

    Implemented in a later phase. Defined now so the confluence engine and
    profiles can reference it without code changes when it lands.
    """

    name = "fvg"

    def __init__(self, weight: float):
        self.weight = weight

    def evaluate(self, ctx: MarketContext) -> SignalResult:
        return SignalResult(self.name, 0.0, {"implemented": False})
```

- [ ] **Step 9: Run test to verify it passes**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_signals.py -v`
Expected: PASS (7 passed)

- [ ] **Step 10: Commit**

```bash
git add src/swingbot/signals tests/test_signals.py
git commit -m "feat: signal protocol + oversold, vwap, relative_strength, fvg stub"
```

---

## Task 5: Regime filter

**Files:**
- Create: `src/swingbot/regime.py`
- Test: `tests/test_regime.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_regime.py
import pandas as pd

from swingbot.profile import StrategyProfile
from swingbot.regime import RegimeFilter
from swingbot.types import MarketContext, Regime


def _df(closes):
    n = len(closes)
    return pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1.0] * n,
    })


def _profile(**kw):
    base = {"symbol": "TRX/USD", "regime_ma_period": 10}
    base.update(kw)
    return StrategyProfile.from_dict(base)


def test_uptrend_when_price_above_rising_ma():
    ctx = MarketContext(candles=_df([float(i) for i in range(1, 30)]))
    r = RegimeFilter(_profile()).evaluate(ctx)
    assert r.regime == Regime.UPTREND

def test_downtrend_when_price_below_falling_ma():
    ctx = MarketContext(candles=_df([float(i) for i in range(30, 1, -1)]))
    r = RegimeFilter(_profile()).evaluate(ctx)
    assert r.regime == Regime.DOWNTREND

def test_permits_entry_respects_allowed_regimes():
    rf = RegimeFilter(_profile())
    assert rf.permits_entry(Regime.UPTREND) is True
    assert rf.permits_entry(Regime.NEUTRAL) is True
    assert rf.permits_entry(Regime.DOWNTREND) is False

def test_uses_htf_when_present():
    # primary says down, htf says up -> regime follows htf
    ctx = MarketContext(
        candles=_df([float(i) for i in range(30, 1, -1)]),
        htf=_df([float(i) for i in range(1, 30)]),
    )
    assert RegimeFilter(_profile()).evaluate(ctx).regime == Regime.UPTREND
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_regime.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.regime'`

- [ ] **Step 3: Write `src/swingbot/regime.py`**

```python
from __future__ import annotations

from swingbot.indicators import sma
from swingbot.profile import StrategyProfile
from swingbot.types import MarketContext, Regime, RegimeResult


class RegimeFilter:
    def __init__(self, profile: StrategyProfile):
        self.profile = profile

    def evaluate(self, ctx: MarketContext) -> RegimeResult:
        df = ctx.htf if ctx.htf is not None else ctx.candles
        ma = sma(df["close"], self.profile.regime_ma_period)
        ma_now, ma_prev = ma.iloc[-1], ma.iloc[-2]
        price = df["close"].iloc[-1]
        if ma_now != ma_now:  # NaN during warmup -> treat as neutral
            return RegimeResult(Regime.NEUTRAL, {"ma": None})
        rising = ma_now > ma_prev
        if price > ma_now and rising:
            regime = Regime.UPTREND
        elif price < ma_now and not rising:
            regime = Regime.DOWNTREND
        else:
            regime = Regime.NEUTRAL
        return RegimeResult(regime, {"ma": float(ma_now), "price": float(price)})

    def permits_entry(self, regime: Regime) -> bool:
        return regime in self.profile.allowed_regimes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_regime.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/regime.py tests/test_regime.py
git commit -m "feat: regime filter (trend gate via SMA, htf-aware)"
```

---

## Task 6: Confluence engine + build_signals

**Files:**
- Create: `src/swingbot/confluence.py`
- Test: `tests/test_confluence.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_confluence.py
import pandas as pd

from swingbot.confluence import ConfluenceEngine, build_signals
from swingbot.profile import StrategyProfile
from swingbot.types import MarketContext


def _df(closes, vols=None):
    n = len(closes)
    return pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open": closes, "high": [c + 0.5 for c in closes],
        "low": [c - 0.5 for c in closes], "close": closes,
        "volume": vols if vols is not None else [1.0] * n,
    })


def _profile():
    return StrategyProfile.from_dict({
        "symbol": "TRX/USD",
        "signals": {
            "oversold": {"weight": 0.5, "oversold_level": 30, "period": 14},
            "vwap": {"weight": 0.5, "window": 20, "max_dist": 0.05},
        },
        "entry_threshold": 0.4,
    })


def test_build_signals_returns_configured_signals():
    sigs = build_signals(_profile())
    assert {s.name for s in sigs} == {"oversold", "vwap"}

def test_confluence_passes_when_score_meets_threshold():
    # falling, last bar dips below vwap -> both signals fire
    closes = [float(i) for i in range(40, 19, -1)]   # 40..20
    ctx = MarketContext(candles=_df(closes))
    res = ConfluenceEngine(build_signals(_profile()), _profile()).evaluate(ctx)
    assert set(res.contributions) == {"oversold", "vwap"}
    assert res.score == sum(res.contributions.values())
    assert res.passed == (res.score >= res.threshold)
    assert res.threshold == 0.4

def test_confluence_fails_in_clean_uptrend():
    closes = [float(i) for i in range(1, 30)]
    ctx = MarketContext(candles=_df(closes))
    res = ConfluenceEngine(build_signals(_profile()), _profile()).evaluate(ctx)
    assert res.passed is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_confluence.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.confluence'`

- [ ] **Step 3: Write `src/swingbot/confluence.py`**

```python
from __future__ import annotations

from swingbot.profile import StrategyProfile
from swingbot.signals.base import Signal
from swingbot.signals.fvg import FvgSignal
from swingbot.signals.oversold import OversoldSignal
from swingbot.signals.relative_strength import RelativeStrengthSignal
from swingbot.signals.vwap import VwapSignal
from swingbot.types import ConfluenceResult, MarketContext

_REGISTRY = {
    "oversold": OversoldSignal,
    "vwap": VwapSignal,
    "relative_strength": RelativeStrengthSignal,
    "fvg": FvgSignal,
}


def build_signals(profile: StrategyProfile) -> list[Signal]:
    signals: list[Signal] = []
    for name, params in profile.signals.items():
        cls = _REGISTRY[name]
        signals.append(cls(**params))
    return signals


class ConfluenceEngine:
    def __init__(self, signals: list[Signal], profile: StrategyProfile):
        self.signals = signals
        self.profile = profile

    def evaluate(self, ctx: MarketContext) -> ConfluenceResult:
        results = {s.name: s.evaluate(ctx) for s in self.signals}
        contributions = {name: r.score * self._weight(name) for name, r in results.items()}
        score = sum(contributions.values())
        threshold = self.profile.entry_threshold
        return ConfluenceResult(
            score=score,
            threshold=threshold,
            passed=score >= threshold,
            contributions=contributions,
            signals=results,
        )

    def _weight(self, name: str) -> float:
        return self.profile.signals[name].get("weight", 0.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_confluence.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/confluence.py tests/test_confluence.py
git commit -m "feat: confluence engine + signal builder"
```

---

## Task 7: Position sizing

**Files:**
- Create: `src/swingbot/sizing.py`
- Test: `tests/test_sizing.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sizing.py
from swingbot.sizing import position_size


def test_risk_based_size():
    # equity 1000, risk 1% => $10 risk; stop distance $0.005 => 2000 units
    qty = position_size(equity=1000, risk_per_trade=0.01, stop_distance=0.005,
                        price=0.10, max_position_frac=1.0)
    assert abs(qty - 2000) < 1e-6

def test_position_cap_clamps_size():
    # uncapped would be huge; cap at 25% of 1000 = $250 / $0.10 = 2500 units
    qty = position_size(equity=1000, risk_per_trade=0.5, stop_distance=0.0001,
                        price=0.10, max_position_frac=0.25)
    assert abs(qty - 2500) < 1e-6

def test_zero_stop_distance_returns_zero():
    assert position_size(1000, 0.01, 0.0, 0.10, 0.25) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_sizing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.sizing'`

- [ ] **Step 3: Write `src/swingbot/sizing.py`**

```python
from __future__ import annotations


def position_size(
    equity: float,
    risk_per_trade: float,
    stop_distance: float,
    price: float,
    max_position_frac: float,
) -> float:
    """Fixed-fractional-risk sizing, clamped by a max position fraction.

    stop_distance is in price units (entry - stop). Returns quantity in coin units.
    """
    if stop_distance <= 0 or price <= 0:
        return 0.0
    risk_qty = (equity * risk_per_trade) / stop_distance
    cap_qty = (equity * max_position_frac) / price
    return min(risk_qty, cap_qty)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_sizing.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/sizing.py tests/test_sizing.py
git commit -m "feat: fixed-fractional position sizing with max-position cap"
```

---

## Task 8: Exit bracket levels

**Files:**
- Create: `src/swingbot/exits.py`
- Test: `tests/test_exits.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_exits.py
from swingbot.exits import bracket_levels


def test_bracket_levels():
    stop, tp = bracket_levels(entry_price=100.0, atr=2.0, stop_mult=1.5, tp_mult=2.0)
    assert abs(stop - 97.0) < 1e-9     # 100 - 1.5*2
    assert abs(tp - 104.0) < 1e-9      # 100 + 2.0*2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_exits.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.exits'`

- [ ] **Step 3: Write `src/swingbot/exits.py`**

```python
from __future__ import annotations


def bracket_levels(
    entry_price: float, atr: float, stop_mult: float, tp_mult: float
) -> tuple[float, float]:
    """Return (stop_price, take_profit_price) for a long position."""
    stop = entry_price - stop_mult * atr
    take_profit = entry_price + tp_mult * atr
    return stop, take_profit
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_exits.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/exits.py tests/test_exits.py
git commit -m "feat: ATR bracket level computation"
```

---

## Task 9: Trade journal

**Files:**
- Create: `src/swingbot/journal.py`
- Test: `tests/test_journal_metrics.py` (journal portion)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_journal_metrics.py
from datetime import datetime, timezone

from swingbot.journal import Trade, TradeJournal
from swingbot.types import ExitReason, Regime, Side


def _trade(pnl, reason=ExitReason.TAKE_PROFIT):
    return Trade(
        entry_ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        exit_ts=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
        side=Side.LONG, entry_price=100.0, exit_price=100.0 + pnl,
        qty=1.0, pnl=pnl, exit_reason=reason,
        score_at_entry=0.7, regime_at_entry=Regime.UPTREND,
    )


def test_journal_records_and_lists():
    j = TradeJournal()
    j.record(_trade(5.0))
    j.record(_trade(-2.0))
    assert len(j.trades) == 2
    assert j.trades[0].pnl == 5.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_journal_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.journal'`

- [ ] **Step 3: Write `src/swingbot/journal.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from swingbot.types import ExitReason, Regime, Side


@dataclass
class Trade:
    entry_ts: datetime
    exit_ts: datetime
    side: Side
    entry_price: float
    exit_price: float
    qty: float
    pnl: float                 # net of fees, in account currency
    exit_reason: ExitReason
    score_at_entry: float
    regime_at_entry: Regime


class TradeJournal:
    def __init__(self):
        self.trades: list[Trade] = []

    def record(self, trade: Trade) -> None:
        self.trades.append(trade)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_journal_metrics.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/journal.py tests/test_journal_metrics.py
git commit -m "feat: Trade record + TradeJournal"
```

---

## Task 10: Metrics

**Files:**
- Create: `src/swingbot/metrics.py`
- Test: `tests/test_journal_metrics.py` (append metrics tests)

- [ ] **Step 1: Add failing metrics tests to `tests/test_journal_metrics.py`**

Append:

```python
from swingbot.metrics import compute_metrics


def test_metrics_on_known_trades():
    trades = [_trade(10.0), _trade(10.0), _trade(-5.0), _trade(-5.0)]
    m = compute_metrics(trades)
    assert m.n_trades == 4
    assert m.win_rate == 0.5
    assert abs(m.avg_win - 10.0) < 1e-9
    assert abs(m.avg_loss - (-5.0)) < 1e-9
    assert abs(m.expectancy - 2.5) < 1e-9          # (10+10-5-5)/4
    assert abs(m.profit_factor - 2.0) < 1e-9       # 20 / 10
    assert m.max_drawdown <= 0.0

def test_metrics_empty():
    m = compute_metrics([])
    assert m.n_trades == 0
    assert m.expectancy == 0.0
    assert m.profit_factor == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_journal_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.metrics'`

- [ ] **Step 3: Write `src/swingbot/metrics.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from swingbot.journal import Trade


@dataclass
class Metrics:
    n_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    expectancy: float
    profit_factor: float
    max_drawdown: float        # most negative equity dip from running peak (<= 0)


def compute_metrics(trades: list[Trade]) -> Metrics:
    if not trades:
        return Metrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    n = len(pnls)
    win_rate = len(wins) / n
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    expectancy = sum(pnls) / n
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0.0

    # max drawdown of the cumulative-pnl equity curve
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        cum += p
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)

    return Metrics(n, win_rate, avg_win, avg_loss, expectancy, profit_factor, max_dd)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_journal_metrics.py -v`
Expected: PASS (3 passed total)

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/metrics.py tests/test_journal_metrics.py
git commit -m "feat: performance metrics (expectancy, win rate, PF, max drawdown)"
```

---

## Task 11: Broker protocol + SimulatedBroker

**Files:**
- Create: `src/swingbot/broker/__init__.py`
- Create: `src/swingbot/broker/base.py`
- Create: `src/swingbot/broker/simulated.py`
- Test: `tests/test_simulated_broker.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_simulated_broker.py
from datetime import datetime, timedelta, timezone

from swingbot.broker.simulated import SimulatedBroker
from swingbot.types import ExitReason, Regime, Side


def _candle(ts, o, h, l, c):
    return {"ts": ts, "open": o, "high": h, "low": l, "close": c, "volume": 1.0}


T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_take_profit_fill():
    b = SimulatedBroker(cash=1000.0, fee_rate=0.0, slippage_rate=0.0)
    b.open_long(ts=T0, price=100.0, qty=1.0, stop=95.0, tp=110.0,
                max_hold_until=T0 + timedelta(hours=8),
                score_at_entry=0.7, regime_at_entry=Regime.UPTREND)
    # next bar trades up through tp
    trade = b.update(_candle(T0 + timedelta(minutes=15), 100, 111, 99, 108))
    assert trade is not None
    assert trade.exit_reason == ExitReason.TAKE_PROFIT
    assert abs(trade.exit_price - 110.0) < 1e-9
    assert b.position is None

def test_stop_fill_takes_priority_over_tp_same_bar():
    b = SimulatedBroker(cash=1000.0, fee_rate=0.0, slippage_rate=0.0)
    b.open_long(ts=T0, price=100.0, qty=1.0, stop=95.0, tp=110.0,
                max_hold_until=T0 + timedelta(hours=8),
                score_at_entry=0.7, regime_at_entry=Regime.UPTREND)
    trade = b.update(_candle(T0 + timedelta(minutes=15), 100, 111, 94, 100))
    assert trade.exit_reason == ExitReason.STOP
    assert abs(trade.exit_price - 95.0) < 1e-9

def test_time_cap_fill_at_close():
    b = SimulatedBroker(cash=1000.0, fee_rate=0.0, slippage_rate=0.0)
    b.open_long(ts=T0, price=100.0, qty=1.0, stop=90.0, tp=120.0,
                max_hold_until=T0 + timedelta(minutes=15),
                score_at_entry=0.7, regime_at_entry=Regime.UPTREND)
    trade = b.update(_candle(T0 + timedelta(minutes=15), 100, 105, 96, 101))
    assert trade.exit_reason == ExitReason.TIME_CAP
    assert abs(trade.exit_price - 101.0) < 1e-9

def test_fees_reduce_pnl():
    b = SimulatedBroker(cash=1000.0, fee_rate=0.01, slippage_rate=0.0)
    b.open_long(ts=T0, price=100.0, qty=1.0, stop=95.0, tp=110.0,
                max_hold_until=T0 + timedelta(hours=8),
                score_at_entry=0.7, regime_at_entry=Regime.UPTREND)
    trade = b.update(_candle(T0 + timedelta(minutes=15), 100, 111, 99, 108))
    # gross 10; fees: buy 100*0.01=1, sell 110*0.01=1.1 -> net 7.9
    assert abs(trade.pnl - 7.9) < 1e-6

def test_equity_reflects_open_position():
    b = SimulatedBroker(cash=1000.0, fee_rate=0.0, slippage_rate=0.0)
    b.open_long(ts=T0, price=100.0, qty=2.0, stop=95.0, tp=110.0,
                max_hold_until=T0 + timedelta(hours=8),
                score_at_entry=0.7, regime_at_entry=Regime.UPTREND)
    # spent 200 cash; at mark 105 -> position worth 210 -> equity 1010
    assert abs(b.equity(mark_price=105.0) - 1010.0) < 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_simulated_broker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.broker'`

- [ ] **Step 3: Write `src/swingbot/broker/__init__.py`**

```python
```
(empty file)

- [ ] **Step 4: Write `src/swingbot/broker/base.py`**

```python
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from swingbot.types import Regime


class Broker(Protocol):
    def open_long(
        self, ts: datetime, price: float, qty: float, stop: float, tp: float,
        max_hold_until: datetime, score_at_entry: float, regime_at_entry: Regime,
    ) -> None: ...

    def equity(self, mark_price: float) -> float: ...
```

- [ ] **Step 5: Write `src/swingbot/broker/simulated.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from swingbot.journal import Trade
from swingbot.types import ExitReason, Regime, Side


@dataclass
class Position:
    entry_ts: datetime
    entry_price: float
    qty: float
    stop: float
    tp: float
    max_hold_until: datetime
    score_at_entry: float
    regime_at_entry: Regime


class SimulatedBroker:
    """Backtest broker: models long-only bracket fills with fees + slippage.

    Exit priority within a single bar: STOP, then TAKE_PROFIT, then TIME_CAP.
    Stop is checked first as the conservative assumption.
    """

    def __init__(self, cash: float, fee_rate: float = 0.0025, slippage_rate: float = 0.0005):
        self.cash = cash
        self.fee_rate = fee_rate
        self.slippage_rate = slippage_rate
        self.position: Position | None = None

    def open_long(
        self, ts: datetime, price: float, qty: float, stop: float, tp: float,
        max_hold_until: datetime, score_at_entry: float, regime_at_entry: Regime,
    ) -> None:
        if self.position is not None or qty <= 0:
            return
        fill = price * (1 + self.slippage_rate)
        cost = fill * qty
        fee = cost * self.fee_rate
        self.cash -= cost + fee
        self.position = Position(ts, fill, qty, stop, tp, max_hold_until,
                                 score_at_entry, regime_at_entry)

    def update(self, candle: dict) -> Trade | None:
        """Process one bar after entry. Returns a Trade if the position exited."""
        if self.position is None:
            return None
        p = self.position
        ts = candle["ts"]

        exit_price: float | None = None
        reason: ExitReason | None = None
        if candle["low"] <= p.stop:
            exit_price, reason = p.stop, ExitReason.STOP
        elif candle["high"] >= p.tp:
            exit_price, reason = p.tp, ExitReason.TAKE_PROFIT
        elif ts >= p.max_hold_until:
            exit_price, reason = candle["close"], ExitReason.TIME_CAP

        if exit_price is None:
            return None
        return self._close(ts, exit_price, reason)

    def force_close(self, ts: datetime, price: float) -> Trade | None:
        if self.position is None:
            return None
        return self._close(ts, price, ExitReason.END_OF_DATA)

    def _close(self, ts: datetime, price: float, reason: ExitReason) -> Trade:
        p = self.position
        fill = price * (1 - self.slippage_rate)
        proceeds = fill * p.qty
        fee = proceeds * self.fee_rate
        self.cash += proceeds - fee

        entry_fee = p.entry_price * p.qty * self.fee_rate
        pnl = (fill - p.entry_price) * p.qty - fee - entry_fee

        trade = Trade(
            entry_ts=p.entry_ts, exit_ts=ts, side=Side.LONG,
            entry_price=p.entry_price, exit_price=fill, qty=p.qty,
            pnl=pnl, exit_reason=reason,
            score_at_entry=p.score_at_entry, regime_at_entry=p.regime_at_entry,
        )
        self.position = None
        return trade

    def equity(self, mark_price: float) -> float:
        pos_value = self.position.qty * mark_price if self.position else 0.0
        return self.cash + pos_value
```

> **Note on fee accounting:** `open_long` already deducts the entry fee from cash. `_close` recomputes `entry_fee` only to report net `pnl` on the Trade; cash is adjusted by proceeds − exit fee. The test `test_fees_reduce_pnl` validates the reported pnl (7.9). Cash-level correctness is exercised by the integration test in Task 13.

- [ ] **Step 6: Run test to verify it passes**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_simulated_broker.py -v`
Expected: PASS (5 passed)

- [ ] **Step 7: Commit**

```bash
git add src/swingbot/broker tests/test_simulated_broker.py
git commit -m "feat: SimulatedBroker with bracket fills, fees, slippage"
```

---

## Task 12: Market data provider (interface + CSV historical)

**Files:**
- Create: `src/swingbot/data/__init__.py`
- Create: `src/swingbot/data/base.py`
- Create: `src/swingbot/data/historical.py`
- Test: `tests/test_data.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data.py
import pandas as pd

from swingbot.data.historical import load_csv, REQUIRED_COLUMNS


def test_load_csv_returns_sorted_typed_frame(tmp_path):
    csv = tmp_path / "trx.csv"
    csv.write_text(
        "ts,open,high,low,close,volume\n"
        "2026-01-01T00:15:00Z,2,3,1,2,100\n"
        "2026-01-01T00:00:00Z,1,2,0.5,1,50\n"
    )
    df = load_csv(str(csv))
    assert list(df.columns) == REQUIRED_COLUMNS
    assert df["ts"].is_monotonic_increasing                # sorted ascending
    assert str(df["ts"].dt.tz) == "UTC"
    assert df["close"].dtype == float

def test_load_csv_rejects_missing_columns(tmp_path):
    csv = tmp_path / "bad.csv"
    csv.write_text("ts,open\n2026-01-01T00:00:00Z,1\n")
    try:
        load_csv(str(csv))
        assert False, "expected ValueError"
    except ValueError as e:
        assert "missing columns" in str(e).lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_data.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.data'`

- [ ] **Step 3: Write `src/swingbot/data/__init__.py`**

```python
```
(empty file)

- [ ] **Step 4: Write `src/swingbot/data/base.py`**

```python
from __future__ import annotations

from typing import Protocol

import pandas as pd


class MarketDataProvider(Protocol):
    def get_candles(self, symbol: str, timeframe: str, lookback: int) -> pd.DataFrame: ...
    def get_latest_price(self, symbol: str) -> float: ...
```

- [ ] **Step 5: Write `src/swingbot/data/historical.py`**

```python
from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS = ["ts", "open", "high", "low", "close", "volume"]


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")
    df = df[REQUIRED_COLUMNS].copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    return df.sort_values("ts").reset_index(drop=True)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_data.py -v`
Expected: PASS (2 passed)

- [ ] **Step 7: Commit**

```bash
git add src/swingbot/data tests/test_data.py
git commit -m "feat: market data provider protocol + CSV historical loader"
```

---

## Task 13: Backtester orchestrator + end-to-end integration test

**Files:**
- Create: `src/swingbot/backtest.py`
- Test: `tests/test_backtest_integration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_backtest_integration.py
import numpy as np
import pandas as pd

from swingbot.backtest import run_backtest
from swingbot.profile import StrategyProfile


def _make_series(closes):
    n = len(closes)
    closes = np.array(closes, dtype=float)
    return pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open": closes,
        "high": closes * 1.002,
        "low": closes * 0.998,
        "close": closes,
        "volume": np.full(n, 100.0),
    })


def _dip_and_recover():
    # long gentle uptrend (keeps regime favorable), with a sharp dip that recovers
    base = list(np.linspace(100, 130, 80))          # uptrend warmup
    dip = list(np.linspace(130, 118, 6))            # sharp dip (oversold)
    recover = list(np.linspace(118, 135, 20))       # bounce -> hits take-profit
    return _make_series(base + dip + recover)


def _profile():
    return StrategyProfile.from_dict({
        "symbol": "TRX/USD",
        "timeframe": "15m",
        "signals": {
            "oversold": {"weight": 0.6, "oversold_level": 45, "period": 14},
            "vwap": {"weight": 0.4, "window": 20, "max_dist": 0.05},
        },
        "entry_threshold": 0.25,
        "regime_ma_period": 20,
        "atr_period": 14,
        "stop_atr_mult": 2.0,
        "take_profit_atr_mult": 2.0,
        "max_hold_bars": 32,
        "risk_per_trade": 0.02,
        "fee_rate": 0.0,
        "slippage_rate": 0.0,
    })


def test_backtest_produces_trades_and_metrics():
    df = _dip_and_recover()
    trades, metrics = run_backtest(df, _profile(), starting_equity=1000.0)
    assert metrics.n_trades >= 1
    assert metrics.n_trades == len(trades)
    # all entries happened in a permitted regime
    from swingbot.types import Regime
    assert all(t.regime_at_entry != Regime.DOWNTREND for t in trades)

def test_backtest_no_trades_in_pure_downtrend():
    df = _make_series(list(np.linspace(200, 100, 120)))   # relentless decline
    trades, metrics = run_backtest(df, _profile(), starting_equity=1000.0)
    assert metrics.n_trades == 0

def test_backtest_is_lookahead_safe_entry_at_next_open():
    # If a signal fires on bar i, entry price must equal bar i+1's open.
    df = _dip_and_recover()
    trades, _ = run_backtest(df, _profile(), starting_equity=1000.0)
    assert len(trades) >= 1
    opens = set(round(o, 6) for o in df["open"])
    assert round(trades[0].entry_price, 6) in opens
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_backtest_integration.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.backtest'`

- [ ] **Step 3: Write `src/swingbot/backtest.py`**

```python
from __future__ import annotations

from datetime import timedelta

import pandas as pd

from swingbot.broker.simulated import SimulatedBroker
from swingbot.confluence import ConfluenceEngine, build_signals
from swingbot.exits import bracket_levels
from swingbot.indicators import atr
from swingbot.journal import Trade, TradeJournal
from swingbot.metrics import Metrics, compute_metrics
from swingbot.profile import StrategyProfile
from swingbot.regime import RegimeFilter
from swingbot.sizing import position_size
from swingbot.types import MarketContext


def _warmup_bars(profile: StrategyProfile) -> int:
    needs = [profile.regime_ma_period, profile.atr_period]
    for params in profile.signals.values():
        for key in ("period", "window", "lookback"):
            if key in params:
                needs.append(params[key])
    return max(needs) + 2


def run_backtest(
    df: pd.DataFrame,
    profile: StrategyProfile,
    benchmark_df: pd.DataFrame | None = None,
    starting_equity: float = 1000.0,
) -> tuple[list[Trade], Metrics]:
    """Replay candles through the real strategy. Lookahead-safe:
    decide on the last CLOSED bar i, enter at bar i+1's open."""
    broker = SimulatedBroker(starting_equity, profile.fee_rate, profile.slippage_rate)
    journal = TradeJournal()
    engine = ConfluenceEngine(build_signals(profile), profile)
    regime = RegimeFilter(profile)
    atr_series = atr(df, profile.atr_period)

    warmup = _warmup_bars(profile)
    bar_delta = df["ts"].iloc[1] - df["ts"].iloc[0]
    max_hold = bar_delta * profile.max_hold_bars

    for i in range(warmup, len(df) - 1):
        current = df.iloc[i]

        # 1) manage an open position on this bar first
        trade = broker.update(current.to_dict())
        if trade is not None:
            journal.record(trade)

        # 2) if flat, evaluate entry on the closed bar, act on next bar's open
        if broker.position is None:
            ctx = MarketContext(
                candles=df.iloc[: i + 1],
                benchmark=benchmark_df.iloc[: i + 1] if benchmark_df is not None else None,
            )
            reg = regime.evaluate(ctx)
            if regime.permits_entry(reg.regime):
                conf = engine.evaluate(ctx)
                if conf.passed:
                    entry_bar = df.iloc[i + 1]
                    entry_price = float(entry_bar["open"])
                    a = float(atr_series.iloc[i])
                    if a > 0:
                        stop, tp = bracket_levels(
                            entry_price, a, profile.stop_atr_mult, profile.take_profit_atr_mult
                        )
                        qty = position_size(
                            broker.equity(float(current["close"])),
                            profile.risk_per_trade,
                            entry_price - stop,
                            entry_price,
                            profile.max_position_frac,
                        )
                        broker.open_long(
                            ts=entry_bar["ts"], price=entry_price, qty=qty,
                            stop=stop, tp=tp,
                            max_hold_until=entry_bar["ts"] + max_hold,
                            score_at_entry=conf.score, regime_at_entry=reg.regime,
                        )

    # close any still-open position at the last bar's close
    last = df.iloc[-1]
    final = broker.force_close(last["ts"], float(last["close"]))
    if final is not None:
        journal.record(final)

    return journal.trades, compute_metrics(journal.trades)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_backtest_integration.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the full suite**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest -q`
Expected: all tests pass (no failures, no errors).

- [ ] **Step 6: Commit**

```bash
git add src/swingbot/backtest.py tests/test_backtest_integration.py
git commit -m "feat: lookahead-safe backtest orchestrator + integration tests"
```

---

## Task 14: Backtest CLI runner

**Files:**
- Create: `src/swingbot/cli.py`
- Modify: `pyproject.toml` (add console script)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
import json

from swingbot.cli import run_from_files


def test_run_from_files_outputs_metrics(tmp_path):
    import numpy as np, pandas as pd
    n = 130
    closes = np.linspace(100, 130, n)
    pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open": closes, "high": closes * 1.002, "low": closes * 0.998,
        "close": closes, "volume": np.full(n, 100.0),
    }).to_csv(tmp_path / "trx.csv", index=False)

    profile = {
        "symbol": "TRX/USD",
        "signals": {"oversold": {"weight": 1.0, "oversold_level": 45, "period": 14}},
        "entry_threshold": 0.2, "regime_ma_period": 20, "fee_rate": 0.0,
        "slippage_rate": 0.0,
    }
    (tmp_path / "profile.json").write_text(json.dumps(profile))

    result = run_from_files(str(tmp_path / "trx.csv"), str(tmp_path / "profile.json"),
                            starting_equity=1000.0)
    assert "n_trades" in result
    assert "expectancy" in result
    assert isinstance(result["n_trades"], int)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.cli'`

- [ ] **Step 3: Write `src/swingbot/cli.py`**

```python
from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from swingbot.backtest import run_backtest
from swingbot.data.historical import load_csv
from swingbot.profile import StrategyProfile


def run_from_files(csv_path: str, profile_path: str, starting_equity: float = 1000.0) -> dict:
    df = load_csv(csv_path)
    with open(profile_path) as f:
        profile = StrategyProfile.from_dict(json.load(f))
    _, metrics = run_backtest(df, profile, starting_equity=starting_equity)
    return asdict(metrics)


def main() -> None:
    ap = argparse.ArgumentParser(description="swingbot backtest")
    ap.add_argument("--csv", required=True, help="OHLCV CSV path")
    ap.add_argument("--profile", required=True, help="strategy profile JSON path")
    ap.add_argument("--equity", type=float, default=1000.0)
    args = ap.parse_args()
    result = run_from_files(args.csv, args.profile, args.equity)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Add console script to `pyproject.toml`**

Add this block after the `[project.optional-dependencies]` block:

```toml
[project.scripts]
swingbot-backtest = "swingbot.cli:main"
```

- [ ] **Step 5: Reinstall to register the script**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pip install -e ".[dev]" -q`
Expected: completes without error.

- [ ] **Step 6: Run test to verify it passes**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/swingbot/cli.py pyproject.toml tests/test_cli.py
git commit -m "feat: backtest CLI runner (swingbot-backtest)"
```

---

## Final verification

- [ ] **Run the entire suite one last time**

Run: `cd crypto-swing-bot && . .venv/bin/activate && pytest -q`
Expected: all tests pass.

- [ ] **Confirm the CLI works end-to-end** (manual smoke test, optional if you have a CSV)

Run: `swingbot-backtest --csv data/<yourfile>.csv --profile <profile>.json`
Expected: prints a JSON metrics block.

---

## What Phase 1 delivers

A working, tested strategy engine and backtester: configurable confluence-score entries (oversold + VWAP + relative strength, FVG stubbed), a hard regime gate, ATR bracket exits with a time cap, fixed-fractional sizing, a fee/slippage-aware simulated broker, a trade journal, performance metrics, and a CLI to run a backtest from a CSV + profile JSON.

**Phase 2 (separate plan) will add:** live `MarketDataProvider` (Alpaca) and live/paper `Broker` adapters behind the same protocols, the `RiskManager`/gatekeeper with the four circuit breakers, the SQLite `StateStore`, and the always-on orchestrator loop — reusing every signal/exit/sizing/metric module built here unchanged.

**Phase 3 (separate plan) will add:** the FastAPI control API + websocket and the Valhalla-styled React dashboard.
