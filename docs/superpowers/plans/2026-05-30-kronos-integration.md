# Kronos Forecast Signal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Kronos as an optional in-process forecast signal that integrates with the existing `ConfluenceEngine` without changing any risk, broker, or orchestrator code.

**Architecture:** A `KronosAdapter` owns model lifecycle and handles column mapping, a single-entry cache keyed on last candle timestamp, and a ThreadPoolExecutor timeout. `KronosForecastSignal` satisfies the existing `Signal` protocol, accepting a `_adapter=` kwarg for test injection so no torch import is required in the unit test suite. All four phases are TDD: failing test first, minimal implementation, verify green.

**Tech Stack:** Python 3.11+, pandas, concurrent.futures (stdlib), pytest. Torch/HuggingFace only in `[kronos]` optional dep group and Phase 4 smoke test.

---

## File Map

| Path | Action | Responsibility |
|------|--------|---------------|
| `pyproject.toml` | Modify | Add `[kronos]` optional dep group |
| `src/swingbot/signals/kronos_adapter.py` | Create | `PredictorProtocol`, `KronosAdapter`, `_load_kronos()` |
| `src/swingbot/signals/kronos_forecast.py` | Create | `KronosForecastSignal` — Signal protocol, scoring, fallback |
| `src/swingbot/confluence.py` | Modify | Register `"kronos_forecast"` in `_REGISTRY` |
| `src/swingbot/backtest.py` | Modify (Phase 2) | Add `precompute_forecasts()`, `_maybe_precompute_kronos()`, one call before main loop |
| `tests/test_kronos_forecast.py` | Create | Phase 1 unit tests (FakePredictor, no torch) |
| `tests/test_kronos_backtest.py` | Create | Phase 2 backtest tests (lookahead, precompute) |
| `frontend/src/pages/Strategy.jsx` | Modify (Phase 3) | Add Kronos signal toggle + param fields |
| `tests/test_kronos_smoke.py` | Create (Phase 4) | Real-model smoke test, env-gated |

---

## Phase 1 — Adapter, Signal, Tests, Registration

---

### Task 1: Add `[kronos]` optional dependency group

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Edit pyproject.toml**

The file already has `[project.optional-dependencies]` with `dev`. Add `kronos` below it:

```toml
[project.optional-dependencies]
dev = ["pytest>=8.0", "httpx>=0.27"]
kronos = [
    "torch>=2.0",
    "huggingface_hub>=0.20",
    "einops",
    "safetensors",
    "tqdm",
]
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `pytest tests/ -x -q`
Expected: 112 passed, 0 failed (no changes to source code yet)

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add [kronos] optional dependency group"
```

---

### Task 2: Create `KronosAdapter`

**Files:**
- Create: `src/swingbot/signals/kronos_adapter.py`
- Create: `tests/test_kronos_forecast.py` (shared test file, grown across Tasks 2 & 3)

The adapter owns model lifecycle. Tests use a `FakePredictor` that satisfies `PredictorProtocol` — no torch import anywhere in the test file.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_kronos_forecast.py`:

```python
from __future__ import annotations

import pandas as pd
import pytest

from swingbot.signals.kronos_adapter import KronosAdapter


# ── helpers ────────────────────────────────────────────────────────────────

def _df(closes: list[float]) -> pd.DataFrame:
    """Minimal SwingBot candle DataFrame (same pattern as test_signals.py)."""
    n = len(closes)
    return pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open": closes,
        "high": [c + 0.5 for c in closes],
        "low":  [c - 0.5 for c in closes],
        "close": closes,
        "volume": [100.0] * n,
    })


def _forecast_df(closes: list[float]) -> pd.DataFrame:
    """Minimal Kronos-format forecast DataFrame (datetime column, not ts)."""
    n = len(closes)
    return pd.DataFrame({
        "datetime": pd.date_range("2026-01-02", periods=n, freq="15min", tz="UTC"),
        "open":   closes,
        "high":   [c + 0.5 for c in closes],
        "low":    [c - 0.5 for c in closes],
        "close":  closes,
        "volume": [100.0] * n,
    })


class FakePredictor:
    """Satisfies PredictorProtocol without importing torch."""

    def __init__(self, forecast: pd.DataFrame, delay_s: float = 0.0):
        self._forecast = forecast
        self._delay_s = delay_s
        self.call_count = 0
        self.last_df_columns: list[str] = []

    def predict(self, df, x_timestamp, y_timestamp, pred_len,
                T, top_k, top_p, sample_count, verbose):
        import time
        self.last_df_columns = list(df.columns)
        self.call_count += 1
        if self._delay_s:
            time.sleep(self._delay_s)
        return self._forecast


# ── KronosAdapter tests ────────────────────────────────────────────────────

def test_candle_ts_renamed_to_datetime():
    """Adapter renames 'ts' → 'datetime' before calling predictor."""
    candles = _df([100.0, 101.0, 102.0])
    fcast = _forecast_df([103.0])
    predictor = FakePredictor(fcast)
    adapter = KronosAdapter(predictor=predictor, pred_len=1)
    adapter.forecast(candles)
    assert "datetime" in predictor.last_df_columns
    assert "ts" not in predictor.last_df_columns


def test_cache_calls_predictor_once():
    """Two forecast() calls with the same last candle ts hit cache; predictor called once."""
    candles = _df([100.0, 101.0, 102.0])
    fcast = _forecast_df([103.0])
    predictor = FakePredictor(fcast)
    adapter = KronosAdapter(predictor=predictor, pred_len=1)
    adapter.forecast(candles)
    adapter.forecast(candles)  # same candles → same last ts → cache hit
    assert predictor.call_count == 1


def test_cache_invalidated_on_new_ts():
    """A new last candle timestamp causes a fresh predictor call."""
    candles_a = _df([100.0, 101.0])
    candles_b = _df([100.0, 101.0, 102.0])  # one more bar → different last ts
    fcast = _forecast_df([103.0])
    predictor = FakePredictor(fcast)
    adapter = KronosAdapter(predictor=predictor, pred_len=1)
    adapter.forecast(candles_a)
    adapter.forecast(candles_b)
    assert predictor.call_count == 2


def test_forecast_returns_none_on_timeout():
    """Inference that exceeds timeout_s returns None without raising."""
    candles = _df([100.0, 101.0, 102.0])
    fcast = _forecast_df([103.0])
    slow = FakePredictor(fcast, delay_s=10.0)
    adapter = KronosAdapter(predictor=slow, pred_len=1, timeout_s=0.05)
    result = adapter.forecast(candles)
    assert result is None


def test_forecast_returns_none_on_predictor_exception():
    """An exception inside predict() returns None without raising."""
    class BrokenPredictor:
        def predict(self, **kwargs):
            raise RuntimeError("model exploded")

    candles = _df([100.0, 101.0, 102.0])
    adapter = KronosAdapter(predictor=BrokenPredictor(), pred_len=1)
    result = adapter.forecast(candles)
    assert result is None
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_kronos_forecast.py -x -q`
Expected: `ImportError: No module named 'swingbot.signals.kronos_adapter'`

- [ ] **Step 3: Create `src/swingbot/signals/kronos_adapter.py`**

```python
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Protocol

import pandas as pd

logger = logging.getLogger(__name__)


class PredictorProtocol(Protocol):
    def predict(
        self,
        df: pd.DataFrame,
        x_timestamp: pd.Timestamp,
        y_timestamp: pd.Timestamp,
        pred_len: int,
        T: int,
        top_k: int,
        top_p: float,
        sample_count: int,
        verbose: bool,
    ) -> pd.DataFrame: ...


def _load_kronos():
    """Lazy import gate — only called from KronosAdapter.from_profile()."""
    try:
        from kronos.model import Kronos, KronosTokenizer, KronosPredictor  # noqa: F401
        return Kronos, KronosTokenizer, KronosPredictor
    except ImportError as exc:
        raise ImportError(
            "Kronos forecast signal requires torch and the Kronos package. "
            "Install with: pip install -e '.[kronos]'"
        ) from exc


class KronosAdapter:
    """Wraps a PredictorProtocol: column mapping, single-entry cache, timeout."""

    def __init__(
        self,
        predictor: PredictorProtocol,
        pred_len: int = 4,
        timeout_s: float = 30.0,
        T: int = 200,
        top_k: int = 5,
        top_p: float = 1.0,
        sample_count: int = 10,
    ) -> None:
        self._predictor = predictor
        self.pred_len = pred_len
        self._timeout_s = timeout_s
        self._T = T
        self._top_k = top_k
        self._top_p = top_p
        self._sample_count = sample_count
        self._cache_key = None
        self._cache_val: pd.DataFrame | None = None
        self._precomputed: dict | None = None
        self._executor = ThreadPoolExecutor(max_workers=1)

    @classmethod
    def from_profile(cls, params: dict) -> "KronosAdapter":
        """Load real Kronos model. Only call this when torch is installed.

        Verify the exact KronosPredictor constructor against the Kronos README
        (https://github.com/shiyu-coder/Kronos) before using in production.
        """
        _, _, KronosPredictor = _load_kronos()
        predictor = KronosPredictor()  # adjust args per Kronos README
        return cls(
            predictor=predictor,
            pred_len=params.get("pred_len", 4),
            timeout_s=params.get("timeout_s", 30.0),
            T=params.get("T", 200),
            top_k=params.get("top_k", 5),
            top_p=params.get("top_p", 1.0),
            sample_count=params.get("sample_count", 10),
        )

    def set_precomputed(self, cache: dict) -> None:
        """Populate the precomputed forecast cache (used by run_backtest)."""
        self._precomputed = cache

    def forecast(self, candles: pd.DataFrame) -> pd.DataFrame | None:
        """Return forecast DataFrame, or None if inference fails/times out."""
        ts_key = candles["ts"].iloc[-1]
        if self._precomputed is not None:
            return self._precomputed.get(ts_key)
        if ts_key == self._cache_key:
            return self._cache_val
        result = self._run_with_timeout(candles)
        self._cache_key = ts_key
        self._cache_val = result
        return result

    def _run_with_timeout(self, candles: pd.DataFrame) -> pd.DataFrame | None:
        """Execute predictor.predict() in a thread; return None on timeout or error."""
        kronos_df = candles.rename(columns={"ts": "datetime"})
        last_ts = pd.Timestamp(kronos_df["datetime"].iloc[-1])
        bar_dur = kronos_df["datetime"].iloc[-1] - kronos_df["datetime"].iloc[-2]
        future_ts = last_ts + bar_dur * self.pred_len

        def _call() -> pd.DataFrame:
            return self._predictor.predict(
                df=kronos_df,
                x_timestamp=last_ts,
                y_timestamp=future_ts,
                pred_len=self.pred_len,
                T=self._T,
                top_k=self._top_k,
                top_p=self._top_p,
                sample_count=self._sample_count,
                verbose=False,
            )

        try:
            fut = self._executor.submit(_call)
            return fut.result(timeout=self._timeout_s)
        except (FuturesTimeoutError, Exception):
            logger.warning("Kronos inference failed or timed out", exc_info=True)
            return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_kronos_forecast.py -x -q`
Expected: 5 passed

- [ ] **Step 5: Verify full suite still green**

Run: `pytest tests/ -x -q`
Expected: 117 passed (112 existing + 5 new)

- [ ] **Step 6: Commit**

```bash
git add src/swingbot/signals/kronos_adapter.py tests/test_kronos_forecast.py
git commit -m "feat: add KronosAdapter with cache, timeout, and column mapping"
```

---

### Task 3: Create `KronosForecastSignal`

**Files:**
- Create: `src/swingbot/signals/kronos_forecast.py`
- Modify: `tests/test_kronos_forecast.py` (append new tests)

- [ ] **Step 1: Append failing tests to `tests/test_kronos_forecast.py`**

Add after the existing imports and helpers (keep all existing code; add below the KronosAdapter tests):

```python
from swingbot.signals.kronos_forecast import KronosForecastSignal
from swingbot.types import MarketContext


# ── KronosForecastSignal tests ────────────────────────────────────────────

def _make_signal(forecast_closes, min_history=3, threshold_pct=0.02,
                 neutral_on_error=True) -> KronosForecastSignal:
    fcast = _forecast_df(forecast_closes)
    predictor = FakePredictor(fcast)
    adapter = KronosAdapter(predictor=predictor, pred_len=len(forecast_closes))
    return KronosForecastSignal(
        weight=0.25,
        _adapter=adapter,
        min_history=min_history,
        threshold_pct=threshold_pct,
        neutral_on_error=neutral_on_error,
    )


def test_bullish_forecast_scores_high():
    """Forecast +3% above current close with threshold_pct=0.02 → score ≥ 0.9."""
    current_close = 100.0
    forecast_close = 103.0   # +3% → pct_change=0.03, threshold=0.02 → score=1.0
    signal = _make_signal([forecast_close], threshold_pct=0.02)
    ctx = MarketContext(candles=_df([current_close] * 5))
    r = signal.evaluate(ctx)
    assert r.name == "kronos_forecast"
    assert r.score >= 0.9


def test_threshold_scales_score():
    """Forecast exactly at threshold_pct produces score exactly 1.0."""
    signal = _make_signal([102.0], threshold_pct=0.02)   # 2% gain, 2% threshold → 1.0
    ctx = MarketContext(candles=_df([100.0] * 5))
    r = signal.evaluate(ctx)
    assert r.score == pytest.approx(1.0)


def test_flat_forecast_scores_zero():
    """Forecast close == current close → score == 0.0."""
    signal = _make_signal([100.0])
    ctx = MarketContext(candles=_df([100.0] * 5))
    assert signal.evaluate(ctx).score == 0.0


def test_negative_forecast_scores_zero():
    """Negative expected return is clamped to 0, not negative."""
    signal = _make_signal([98.0])   # -2%
    ctx = MarketContext(candles=_df([100.0] * 5))
    r = signal.evaluate(ctx)
    assert r.score == 0.0


def test_insufficient_history_returns_zero():
    """Fewer candles than min_history returns score 0.0 without calling adapter."""
    fcast = _forecast_df([105.0])
    predictor = FakePredictor(fcast)
    adapter = KronosAdapter(predictor=predictor, pred_len=1)
    signal = KronosForecastSignal(weight=0.25, _adapter=adapter, min_history=10)
    ctx = MarketContext(candles=_df([100.0] * 5))  # only 5 bars < min_history=10
    r = signal.evaluate(ctx)
    assert r.score == 0.0
    assert predictor.call_count == 0


def test_forecast_none_returns_neutral_when_neutral_on_error_true():
    """adapter.forecast() → None and neutral_on_error=True → score 0.5."""
    class NonePredictor:
        def predict(self, **kwargs):
            raise RuntimeError("always fails")

    adapter = KronosAdapter(predictor=NonePredictor(), pred_len=1)
    signal = KronosForecastSignal(weight=0.25, _adapter=adapter, neutral_on_error=True)
    ctx = MarketContext(candles=_df([100.0] * 5))
    r = signal.evaluate(ctx)
    assert r.score == 0.5
    assert r.meta["error"] == "no_forecast"


def test_neutral_on_error_false_returns_zero():
    """adapter.forecast() → None and neutral_on_error=False → score 0.0."""
    class NonePredictor:
        def predict(self, **kwargs):
            raise RuntimeError("always fails")

    adapter = KronosAdapter(predictor=NonePredictor(), pred_len=1)
    signal = KronosForecastSignal(weight=0.25, _adapter=adapter, neutral_on_error=False)
    ctx = MarketContext(candles=_df([100.0] * 5))
    r = signal.evaluate(ctx)
    assert r.score == 0.0


def test_meta_contains_pct_change_and_forecast_close():
    """Normal result includes pct_change and forecast_close in meta."""
    signal = _make_signal([102.0])
    ctx = MarketContext(candles=_df([100.0] * 5))
    r = signal.evaluate(ctx)
    assert "pct_change" in r.meta
    assert "forecast_close" in r.meta
    assert r.meta["forecast_close"] == pytest.approx(102.0)
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_kronos_forecast.py -x -q`
Expected: `ImportError: No module named 'swingbot.signals.kronos_forecast'`

- [ ] **Step 3: Create `src/swingbot/signals/kronos_forecast.py`**

```python
from __future__ import annotations

from swingbot.signals.kronos_adapter import KronosAdapter
from swingbot.types import MarketContext, SignalResult


class KronosForecastSignal:
    """Kronos-based forecast signal. Satisfies the Signal protocol.

    In tests, inject a pre-built KronosAdapter via _adapter=.
    In production (build_signals), omit _adapter and the signal
    calls KronosAdapter.from_profile() to load the real model.
    """

    name = "kronos_forecast"

    def __init__(
        self,
        weight: float,
        pred_len: int = 4,
        threshold_pct: float = 0.02,
        min_history: int = 50,
        neutral_on_error: bool = True,
        _adapter: KronosAdapter | None = None,
    ) -> None:
        self.weight = weight
        self.threshold_pct = threshold_pct
        self.min_history = min_history
        self.neutral_on_error = neutral_on_error
        self.adapter = _adapter or KronosAdapter.from_profile({
            "pred_len": pred_len,
        })

    def evaluate(self, ctx: MarketContext) -> SignalResult:
        if len(ctx.candles) < self.min_history:
            return SignalResult(self.name, 0.0, {"error": "insufficient_history"})

        forecast = self.adapter.forecast(ctx.candles)
        if forecast is None:
            fallback = 0.5 if self.neutral_on_error else 0.0
            return SignalResult(self.name, fallback, {"error": "no_forecast"})

        current_close = float(ctx.candles["close"].iloc[-1])
        forecast_close = float(forecast["close"].iloc[-1])
        pct_change = (forecast_close - current_close) / current_close
        score = max(0.0, min(1.0, pct_change / self.threshold_pct))
        return SignalResult(
            self.name,
            score,
            {"pct_change": pct_change, "forecast_close": forecast_close},
        )
```

- [ ] **Step 4: Run signal tests to verify they pass**

Run: `pytest tests/test_kronos_forecast.py -x -q`
Expected: 13 passed

- [ ] **Step 5: Verify full suite still green**

Run: `pytest tests/ -x -q`
Expected: 125 passed

- [ ] **Step 6: Commit**

```bash
git add src/swingbot/signals/kronos_forecast.py tests/test_kronos_forecast.py
git commit -m "feat: add KronosForecastSignal with scoring and fallback"
```

---

### Task 4: Register `kronos_forecast` in `ConfluenceEngine`

**Files:**
- Modify: `src/swingbot/confluence.py`
- Modify: `tests/test_kronos_forecast.py` (append registration test)

- [ ] **Step 1: Append the failing test to `tests/test_kronos_forecast.py`**

```python
from swingbot.confluence import build_signals
from swingbot.profile import StrategyProfile


def test_confluence_accepts_kronos_signal():
    """build_signals with a kronos_forecast entry constructs the signal without error.

    Uses _adapter injection so no torch import occurs.
    """
    fcast = _forecast_df([103.0])
    predictor = FakePredictor(fcast)
    adapter = KronosAdapter(predictor=predictor, pred_len=1)

    profile = StrategyProfile(
        symbol="BTC/USD",
        signals={
            "kronos_forecast": {
                "weight": 0.25,
                "pred_len": 1,
                "_adapter": adapter,
            }
        },
    )
    signals = build_signals(profile)
    assert len(signals) == 1
    assert signals[0].name == "kronos_forecast"
```

- [ ] **Step 2: Run to confirm it fails**

Run: `pytest tests/test_kronos_forecast.py::test_confluence_accepts_kronos_signal -v`
Expected: `KeyError: 'kronos_forecast'`

- [ ] **Step 3: Register the signal in `src/swingbot/confluence.py`**

Add the import and registry entry:

```python
from __future__ import annotations

from swingbot.profile import StrategyProfile
from swingbot.signals.base import Signal
from swingbot.signals.fvg import FvgSignal
from swingbot.signals.kronos_forecast import KronosForecastSignal
from swingbot.signals.oversold import OversoldSignal
from swingbot.signals.relative_strength import RelativeStrengthSignal
from swingbot.signals.vwap import VwapSignal
from swingbot.types import ConfluenceResult, MarketContext

_REGISTRY = {
    "oversold": OversoldSignal,
    "vwap": VwapSignal,
    "relative_strength": RelativeStrengthSignal,
    "fvg": FvgSignal,
    "kronos_forecast": KronosForecastSignal,
}
```

Everything else in `confluence.py` stays identical.

- [ ] **Step 4: Run the new test**

Run: `pytest tests/test_kronos_forecast.py::test_confluence_accepts_kronos_signal -v`
Expected: PASSED

- [ ] **Step 5: Verify full suite**

Run: `pytest tests/ -x -q`
Expected: 126 passed

- [ ] **Step 6: Commit**

```bash
git add src/swingbot/confluence.py tests/test_kronos_forecast.py
git commit -m "feat: register kronos_forecast signal in ConfluenceEngine"
```

---

## Phase 2 — Backtest Precompute Cache

---

### Task 5: Add precomputed cache + backtest auto-detection

**Files:**
- Modify: `src/swingbot/backtest.py`
- Create: `tests/test_kronos_backtest.py`

The adapter already stores `_precomputed`. This task adds `precompute_forecasts()` and `_maybe_precompute_kronos()` to `backtest.py` and calls the latter just before the main loop.

- [ ] **Step 1: Write failing backtest tests**

Create `tests/test_kronos_backtest.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from swingbot.backtest import run_backtest
from swingbot.profile import StrategyProfile
from swingbot.signals.kronos_adapter import KronosAdapter
from swingbot.signals.kronos_forecast import KronosForecastSignal


def _df(n: int, close: float = 100.0) -> pd.DataFrame:
    closes = [close] * n
    return pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open": closes,
        "high": [c + 1.0 for c in closes],
        "low":  [c - 1.0 for c in closes],
        "close": closes,
        "volume": [500.0] * n,
    })


class RecordingPredictor:
    """Records every candle slice it receives so we can verify lookahead safety."""

    def __init__(self, forecast_close: float = 102.0, pred_len: int = 1):
        self._forecast_close = forecast_close
        self._pred_len = pred_len
        self.received_max_ts: list = []

    def predict(self, df, x_timestamp, y_timestamp, pred_len,
                T, top_k, top_p, sample_count, verbose):
        self.received_max_ts.append(df["datetime"].max())
        n = pred_len
        return pd.DataFrame({
            "datetime": pd.date_range(y_timestamp, periods=n, freq="15min", tz="UTC"),
            "open":   [self._forecast_close] * n,
            "high":   [self._forecast_close + 0.5] * n,
            "low":    [self._forecast_close - 0.5] * n,
            "close":  [self._forecast_close] * n,
            "volume": [100.0] * n,
        })


def _profile_with_kronos(adapter: KronosAdapter) -> StrategyProfile:
    return StrategyProfile(
        symbol="BTC/USD",
        regime_ma_period=10,
        atr_period=5,
        signals={
            "kronos_forecast": {
                "weight": 1.0,
                "pred_len": 1,
                "threshold_pct": 0.01,
                "min_history": 3,
                "_adapter": adapter,
            }
        },
        entry_threshold=0.5,
    )


def test_lookahead_safe():
    """At every backtest bar i, predictor receives candles[:i+1] only.

    Asserts that the maximum timestamp in each predictor input equals
    df["ts"].iloc[i] — never a future bar.
    """
    df = _df(30)
    predictor = RecordingPredictor(forecast_close=102.0, pred_len=1)
    adapter = KronosAdapter(predictor=predictor, pred_len=1, timeout_s=5.0)
    profile = _profile_with_kronos(adapter)
    run_backtest(df, profile)

    from swingbot.backtest import _warmup_bars
    warmup = _warmup_bars(profile)
    expected_max_ts = [
        pd.Timestamp(df["ts"].iloc[i]) for i in range(warmup, len(df) - 1)
    ]
    # Every ts the predictor saw must be in expected_max_ts
    for seen_ts in predictor.received_max_ts:
        assert seen_ts in expected_max_ts, (
            f"Predictor received ts {seen_ts} which is not a valid bar boundary"
        )


def test_precompute_cache_avoids_duplicate_inference():
    """When precomputed cache is populated, each bar is inferred exactly once."""
    df = _df(30)
    predictor = RecordingPredictor(forecast_close=102.0, pred_len=1)
    adapter = KronosAdapter(predictor=predictor, pred_len=1, timeout_s=5.0)
    profile = _profile_with_kronos(adapter)

    from swingbot.backtest import _warmup_bars, precompute_forecasts
    warmup = _warmup_bars(profile)
    cache = precompute_forecasts(df, adapter, warmup)

    # Each bar from warmup to end gets exactly one forecast
    assert len(cache) == len(df) - warmup
    # No bar was inferred twice
    assert predictor.call_count == len(df) - warmup


def test_precompute_skips_bars_before_warmup():
    """precompute_forecasts produces no entry for bars before warmup."""
    df = _df(30)
    predictor = RecordingPredictor(forecast_close=102.0, pred_len=1)
    adapter = KronosAdapter(predictor=predictor, pred_len=1, timeout_s=5.0)
    profile = _profile_with_kronos(adapter)

    from swingbot.backtest import _warmup_bars, precompute_forecasts
    warmup = _warmup_bars(profile)
    cache = precompute_forecasts(df, adapter, warmup)

    # None of the keys should be timestamps before the warmup bar
    pre_warmup_ts = set(df["ts"].iloc[:warmup].tolist())
    for ts_key in cache:
        assert ts_key not in pre_warmup_ts


def test_run_backtest_with_kronos_signal_completes():
    """run_backtest doesn't crash when a KronosForecastSignal is present."""
    df = _df(30)
    predictor = RecordingPredictor(forecast_close=102.0, pred_len=1)
    adapter = KronosAdapter(predictor=predictor, pred_len=1, timeout_s=5.0)
    profile = _profile_with_kronos(adapter)
    trades, metrics = run_backtest(df, profile, starting_equity=10_000.0)
    # Just verify it completes; trade count depends on signal strength
    assert isinstance(trades, list)
    assert metrics is not None
```

- [ ] **Step 2: Run to confirm they fail**

Run: `pytest tests/test_kronos_backtest.py -x -q`
Expected: `ImportError: cannot import name 'precompute_forecasts' from 'swingbot.backtest'`

- [ ] **Step 3: Add `precompute_forecasts` and `_maybe_precompute_kronos` to `src/swingbot/backtest.py`**

Add these two functions after the `_warmup_bars` function (before `run_backtest`):

```python
def precompute_forecasts(
    df: pd.DataFrame,
    adapter,
    warmup: int,
) -> dict:
    """Run Kronos inference for every bar from warmup to end of df.

    Returns a dict mapping last-candle ts → forecast DataFrame (or None).
    Bypasses the adapter's single-entry live cache by calling _run_with_timeout directly.
    """
    cache = {}
    for i in range(warmup, len(df)):
        candles_slice = df.iloc[: i + 1]
        ts_key = candles_slice["ts"].iloc[-1]
        cache[ts_key] = adapter._run_with_timeout(candles_slice)
    return cache


def _maybe_precompute_kronos(
    signals: list,
    df: pd.DataFrame,
    warmup: int,
) -> None:
    """If any signal is a KronosForecastSignal, pre-populate its adapter's cache."""
    from swingbot.signals.kronos_forecast import KronosForecastSignal
    for signal in signals:
        if isinstance(signal, KronosForecastSignal):
            cache = precompute_forecasts(df, signal.adapter, warmup)
            signal.adapter.set_precomputed(cache)
```

Then add one call inside `run_backtest`, after `warmup` and `max_hold` are calculated and before the main loop:

```python
    warmup = _warmup_bars(profile)
    bar_delta = df["ts"].iloc[1] - df["ts"].iloc[0]
    max_hold = bar_delta * profile.max_hold_bars

    _maybe_precompute_kronos(engine.signals, df, warmup)  # no-op if no Kronos signal

    for i in range(warmup, len(df) - 1):
```

The complete updated `run_backtest` (show full function so context is clear):

```python
def run_backtest(
    df: pd.DataFrame,
    profile: StrategyProfile,
    benchmark_df: pd.DataFrame | None = None,
    starting_equity: float = 1000.0,
) -> tuple[list[Trade], Metrics]:
    """Replay candles through the real strategy. Lookahead-safe:
    decide on the last CLOSED bar i, enter at bar i+1's open."""
    if len(df) < 2:
        raise ValueError("run_backtest needs at least 2 candles")
    broker = SimulatedBroker(starting_equity, profile.fee_rate, profile.slippage_rate)
    journal = TradeJournal()
    engine = ConfluenceEngine(build_signals(profile), profile)
    regime = RegimeFilter(profile)
    atr_series = atr(df, profile.atr_period)

    warmup = _warmup_bars(profile)
    bar_delta = df["ts"].iloc[1] - df["ts"].iloc[0]
    max_hold = bar_delta * profile.max_hold_bars

    _maybe_precompute_kronos(engine.signals, df, warmup)

    for i in range(warmup, len(df) - 1):
        current = df.iloc[i]

        trade = broker.update(current.to_dict())
        if trade is not None:
            journal.record(trade)

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

    last = df.iloc[-1]
    final = broker.force_close(last["ts"], float(last["close"]))
    if final is not None:
        journal.record(final)

    return journal.trades, compute_metrics(journal.trades)
```

- [ ] **Step 4: Run backtest tests**

Run: `pytest tests/test_kronos_backtest.py -x -q`
Expected: 4 passed

- [ ] **Step 5: Verify full suite**

Run: `pytest tests/ -x -q`
Expected: 130 passed

- [ ] **Step 6: Commit**

```bash
git add src/swingbot/backtest.py tests/test_kronos_backtest.py
git commit -m "feat: precompute Kronos forecasts in run_backtest for lookahead-safe replay"
```

---

## Phase 3 — Dashboard Profile Fields

---

### Task 6: Add Kronos signal section to `Strategy.jsx`

**Files:**
- Modify: `frontend/src/pages/Strategy.jsx`

The Strategy page already handles four signals (oversold, vwap, relative_strength, fvg) with a consistent pattern: toggle in `BLANK`, parse in `parseProfile`, assemble in `assembleProfile`, and a `<Toggle>` section in JSX. Add Kronos following the same pattern exactly.

- [ ] **Step 1: Add Kronos fields to the `BLANK` defaults object**

In `BLANK`, append these four keys at the end (before the closing `}`):

```js
const BLANK = {
  // ... existing fields ...
  fvg_on: false, fvg_weight: '0.0',
  kronos_on: false, kronos_weight: '0.25', kronos_pred_len: '4', kronos_threshold_pct: '0.02',
}
```

- [ ] **Step 2: Add Kronos parsing to `parseProfile`**

Inside `parseProfile`, add `kn = s.kronos_forecast || {}` alongside the existing destructure, then add four lines mapping the fields:

```js
function parseProfile(name, p){
  const s = p.signals || {}
  const o = s.oversold || {}, v = s.vwap || {}, r = s.relative_strength || {},
        fv = s.fvg || {}, kn = s.kronos_forecast || {}
  return {
    ...BLANK, name,
    // ... existing mappings ...
    fvg_on: !!s.fvg, fvg_weight: g(fv.weight, BLANK.fvg_weight),
    kronos_on: !!s.kronos_forecast,
    kronos_weight: g(kn.weight, BLANK.kronos_weight),
    kronos_pred_len: g(kn.pred_len, BLANK.kronos_pred_len),
    kronos_threshold_pct: g(kn.threshold_pct, BLANK.kronos_threshold_pct),
  }
}
```

- [ ] **Step 3: Add Kronos assembly to `assembleProfile`**

Inside `assembleProfile`, add the kronos_forecast entry alongside the others:

```js
function assembleProfile(f){
  const n = (x) => Number(x)
  const signals = {}
  if (f.oversold_on) signals.oversold = { weight: n(f.oversold_weight), oversold_level: n(f.oversold_level), period: n(f.oversold_period) }
  if (f.vwap_on) signals.vwap = { weight: n(f.vwap_weight), window: n(f.vwap_window), max_dist: n(f.vwap_max_dist) }
  if (f.rs_on) signals.relative_strength = { weight: n(f.rs_weight), band: n(f.rs_band), lookback: n(f.rs_lookback) }
  if (f.fvg_on) signals.fvg = { weight: n(f.fvg_weight) }
  if (f.kronos_on) signals.kronos_forecast = {
    weight: n(f.kronos_weight),
    pred_len: n(f.kronos_pred_len),
    threshold_pct: n(f.kronos_threshold_pct),
  }
  return {
    // ... rest unchanged ...
  }
}
```

- [ ] **Step 4: Add the Kronos `<Toggle>` section to the JSX**

Find the existing FVG signal section and add the Kronos section immediately after it. The exact location is after the closing `</div>` of the FVG block. Match the exact style of existing signal toggles:

```jsx
<Toggle f={f} set={set} label="FVG" k="fvg_on"
  hint="Fair Value Gap signal (stub — returns 0 until implemented).">
  <Num f={f} set={set} label="Weight" k="fvg_weight" step="0.01" />
</Toggle>

<Toggle f={f} set={set} label="Kronos Forecast" k="kronos_on"
  hint="Kronos time-series foundation model. Forecasts N bars ahead and scores the expected return. Requires pip install -e '[kronos]' on the server.">
  <Num f={f} set={set} label="Weight" k="kronos_weight" step="0.01"
    hint="Contribution to confluence score. 0.25 = 25% weight." />
  <Num f={f} set={set} label="Forecast bars (pred_len)" k="kronos_pred_len" step="1"
    hint="How many bars ahead to forecast. At 15m timeframe, 4 = 1 hour ahead." />
  <Num f={f} set={set} label="Bullish threshold %" k="kronos_threshold_pct" step="0.001"
    hint="Expected % gain that maps to score 1.0. E.g. 0.02 = 2% gain = max score." />
</Toggle>
```

- [ ] **Step 5: Build the frontend and verify no errors**

Run from the repo root:
```bash
cd frontend && npm run build 2>&1 | tail -20
```
Expected: `✓ built in ...` with no errors. Bundle sizes similar to before.

- [ ] **Step 6: Commit**

```bash
cd ..
git add frontend/src/pages/Strategy.jsx
git commit -m "feat: add Kronos signal section to Strategy dashboard form"
```

---

## Phase 4 — Real-Model Smoke Test

---

### Task 7: Add env-gated smoke test

**Files:**
- Create: `tests/test_kronos_smoke.py`

This test is skipped in normal CI. It only runs when `KRONOS_SMOKE_TEST=1` is set and the `[kronos]` extras are installed. It verifies that the real `KronosPredictor` loads and returns a DataFrame of the right shape — nothing more.

- [ ] **Step 1: Create `tests/test_kronos_smoke.py`**

```python
from __future__ import annotations

import os

import pandas as pd
import pytest

SMOKE = bool(os.environ.get("KRONOS_SMOKE_TEST"))


@pytest.mark.skipif(not SMOKE, reason="set KRONOS_SMOKE_TEST=1 to run real model")
def test_real_predictor_returns_correct_shape():
    """Load the real Kronos model and verify predict() output shape.

    Before running: pip install -e '.[kronos]'
    Verify KronosPredictor() constructor args against the Kronos README.
    """
    from swingbot.signals.kronos_adapter import KronosAdapter, _load_kronos

    _, _, KronosPredictor = _load_kronos()
    predictor = KronosPredictor()  # adjust constructor if README differs

    n = 100
    candles = pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open":   [100.0 + i * 0.1 for i in range(n)],
        "high":   [101.0 + i * 0.1 for i in range(n)],
        "low":    [99.0  + i * 0.1 for i in range(n)],
        "close":  [100.5 + i * 0.1 for i in range(n)],
        "volume": [1000.0] * n,
    })

    pred_len = 4
    adapter = KronosAdapter(predictor=predictor, pred_len=pred_len, timeout_s=120.0)
    result = adapter.forecast(candles)

    assert result is not None, "Real Kronos predictor returned None"
    assert len(result) == pred_len, f"Expected {pred_len} rows, got {len(result)}"
    for col in ("open", "high", "low", "close"):
        assert col in result.columns, f"Missing column {col!r} in forecast"
    assert result["close"].notna().all(), "Forecast close contains NaN"


@pytest.mark.skipif(not SMOKE, reason="set KRONOS_SMOKE_TEST=1 to run real model")
def test_missing_kronos_import_gives_helpful_error():
    """ImportError message includes the pip install command."""
    import sys
    import importlib

    # Temporarily hide kronos if it's installed, to test the error path
    original = sys.modules.pop("kronos", None)
    original_model = sys.modules.pop("kronos.model", None)
    try:
        from swingbot.signals.kronos_adapter import _load_kronos
        with pytest.raises(ImportError, match="pip install -e"):
            _load_kronos()
    finally:
        if original is not None:
            sys.modules["kronos"] = original
        if original_model is not None:
            sys.modules["kronos.model"] = original_model
```

- [ ] **Step 2: Verify smoke test is skipped in normal run**

Run: `pytest tests/test_kronos_smoke.py -v`
Expected:
```
SKIPPED [2] test_kronos_smoke.py:... set KRONOS_SMOKE_TEST=1 to run real model
2 skipped
```

- [ ] **Step 3: Verify full suite still green**

Run: `pytest tests/ -x -q`
Expected: 130 passed, 2 skipped

- [ ] **Step 4: Commit**

```bash
git add tests/test_kronos_smoke.py
git commit -m "test: add env-gated Kronos real-model smoke test"
```

---

## Self-Review Checklist

| Spec requirement | Task |
|-----------------|------|
| `PredictorProtocol` defined | Task 2 |
| `KronosAdapter` with cache, timeout, column mapping | Task 2 |
| `_load_kronos()` lazy import with helpful error | Task 2 |
| `KronosForecastSignal` satisfies Signal protocol | Task 3 |
| Scoring formula: `clip(pct_change / threshold_pct, 0, 1)` | Task 3 |
| Fallback: None → 0.5 if neutral_on_error, else 0.0 | Task 3 |
| Fallback: insufficient history → 0.0, no adapter call | Task 3 |
| `_adapter=` test injection param | Task 3 |
| `"kronos_forecast"` in `_REGISTRY` | Task 4 |
| `pyproject.toml [kronos]` optional dep group | Task 1 |
| Backtest lookahead safety verified by test | Task 5 |
| `precompute_forecasts()` + `set_precomputed()` | Task 5 |
| `_maybe_precompute_kronos()` called in `run_backtest` | Task 5 |
| Dashboard form fields for all Kronos params | Task 6 |
| Smoke test gated by `KRONOS_SMOKE_TEST=1` | Task 7 |
| No torch import in normal test suite | Tasks 2–5 use FakePredictor |
| Existing 112 tests stay green throughout | Verified after each task |
