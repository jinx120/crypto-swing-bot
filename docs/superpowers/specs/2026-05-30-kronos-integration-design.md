# Kronos Forecast Signal — Integration Design

**Date:** 2026-05-30  
**Status:** Approved  
**Approach:** In-Process Optional Adapter (Approach A)

---

## Goal

Integrate the [Kronos](https://github.com/shiyu-coder/Kronos) time-series foundation model as an optional, weighted signal inside SwingBot's existing `ConfluenceEngine`. Kronos forecasts future OHLCV values; the signal converts the forecast into a 0..1 long-entry score. All existing risk controls, regime gate, ATR exits, broker adapters, and live-mode guardrails remain unchanged.

---

## Constraints

- Torch and Kronos are **optional**. Users who do not enable the signal install nothing extra.
- No model downloads during normal tests. Tests use a `FakePredictor`.
- No live trading until paper/backtest validation exists (Phase 2 precedes live).
- Signal must satisfy the existing `Signal` protocol: `evaluate(ctx: MarketContext) -> SignalResult`.
- No bypassing of existing risk controls.
- Implementation stays small and idiomatic to the existing codebase.

---

## Architecture Overview

Three new files. Two existing files receive minimal additions.

```
src/swingbot/signals/
    kronos_adapter.py      # model lifecycle, column mapping, cache, timeout
    kronos_forecast.py     # Signal protocol implementation + scoring

tests/
    test_kronos_forecast.py   # Phase 1 & 2 unit tests (FakePredictor, no torch)
    test_kronos_smoke.py      # Phase 4 real-model smoke test (env-gated)
```

**Existing file changes:**
- `src/swingbot/confluence.py` — register `"kronos_forecast": KronosForecastSignal` in `_REGISTRY`
- `pyproject.toml` — add `[project.optional-dependencies] kronos = [...]`

`StrategyProfile`, `types.py`, `backtest.py`, `orchestrator.py` — **no changes.**

---

## Phase Plan

| Phase | Scope |
|-------|-------|
| 1 | Adapter + Signal + FakePredictor unit tests + confluence registration |
| 2 | Backtest support: precomputed forecast cache, lookahead-safety verification |
| 3 | Dashboard: profile form fields for Kronos params |
| 4 | Optional real-model smoke test gated by `KRONOS_SMOKE_TEST=1` env var |

---

## Component: `KronosAdapter` (`kronos_adapter.py`)

### Responsibilities

- Owns the real `KronosPredictor` instance (or any `PredictorProtocol` duck-type).
- Maps SwingBot candle columns to Kronos input format.
- Caches the last forecast keyed by the last candle's `ts` timestamp.
- Enforces a wall-clock timeout on inference; returns `None` on timeout or exception.
- Provides `from_profile(params)` class method that lazily imports `kronos.model` — the only place where the torch import occurs.

### Interface

```python
class PredictorProtocol(Protocol):
    def predict(
        self, df: pd.DataFrame,
        x_timestamp: pd.Timestamp, y_timestamp: pd.Timestamp,
        pred_len: int, T: int,
        top_k: int, top_p: float,
        sample_count: int, verbose: bool,
    ) -> pd.DataFrame: ...

class KronosAdapter:
    def __init__(
        self,
        predictor: PredictorProtocol,
        pred_len: int = 4,
        timeout_s: float = 30.0,
        T: int = 200,
        top_k: int = 5,
        top_p: float = 1.0,
        sample_count: int = 10,
    ) -> None: ...

    @classmethod
    def from_profile(cls, params: dict) -> "KronosAdapter":
        """Lazy-imports kronos.model. Raises ImportError with install hint if absent."""
        ...

    def forecast(self, candles: pd.DataFrame) -> pd.DataFrame | None:
        """Returns a Kronos forecast DataFrame or None on failure."""
        ...
```

### Column Mapping

SwingBot candles: `ts, open, high, low, close, volume`  
Kronos expects: `datetime, open, high, low, close, volume` (optional `amount`)

The adapter renames `ts → datetime` before calling the predictor and drops no other columns.

### Cache

- Key: `candles["ts"].iloc[-1]` (the last closed bar's timestamp).
- One entry only — evicted when a new timestamp is seen.
- Thread-safe: the adapter is constructed once and shared; the cache update is a simple dict assignment (GIL-protected for CPython; sufficient for single-threaded swing trading loop).

### Timeout

Uses `concurrent.futures.ThreadPoolExecutor(max_workers=1)`. Submits inference as a future, calls `future.result(timeout=timeout_s)`. On `TimeoutError` or any exception: logs a warning, returns `None`, does not re-raise.

### Lazy Import

```python
def _load_kronos():
    try:
        from kronos.model import Kronos, KronosTokenizer, KronosPredictor
        return Kronos, KronosTokenizer, KronosPredictor
    except ImportError as exc:
        raise ImportError(
            "Kronos forecast signal requires torch and the Kronos package. "
            "Install with: pip install -e '.[kronos]'"
        ) from exc
```

Only called from `KronosAdapter.from_profile()`. Module-level imports of `kronos_adapter` and `kronos_forecast` are always safe.

---

## Component: `KronosForecastSignal` (`kronos_forecast.py`)

### Interface

```python
class KronosForecastSignal:
    name = "kronos_forecast"

    def __init__(
        self,
        weight: float,
        adapter: KronosAdapter,
        threshold_pct: float = 0.02,
        min_history: int = 50,
        neutral_on_error: bool = True,
    ) -> None: ...

    def evaluate(self, ctx: MarketContext) -> SignalResult: ...
```

### Scoring Formula

```
current_close  = ctx.candles["close"].iloc[-1]
forecast_close = forecast_df["close"].iloc[-1]   # last predicted bar

pct_change = (forecast_close - current_close) / current_close
score      = clip(pct_change / threshold_pct, 0.0, 1.0)
```

- `threshold_pct=0.02`: a 2% expected gain produces score 1.0. Tunable per profile.
- Flat or negative forecast → score 0.0 (clamped).
- No short signals; this is a long-only bot.

### Error / Fallback Behavior

| Condition | Return value |
|-----------|-------------|
| `len(ctx.candles) < min_history` | `SignalResult(..., 0.0, {"error": "insufficient_history"})` |
| `adapter.forecast()` returns `None` | `SignalResult(..., 0.5 if neutral_on_error else 0.0, {"error": "no_forecast"})` |
| Normal path | `SignalResult(..., score, {"pct_change": ..., "forecast_close": ...})` |

Default `neutral_on_error=True` so a single Kronos failure doesn't drag the whole confluence score to zero and accidentally suppress entries from healthy signals.

### Construction from Profile

`KronosForecastSignal` is constructed by `build_signals` using the same `cls(**params)` pattern as all other signals. **The signal owns adapter construction** — `__init__` builds the adapter from its own params, so `build_signals` and `_REGISTRY` need no special-casing beyond the one-line registration.

The `__init__` signature:

```python
def __init__(
    self,
    weight: float,
    pred_len: int = 4,
    threshold_pct: float = 0.02,
    min_history: int = 50,
    neutral_on_error: bool = True,
    _adapter: KronosAdapter | None = None,   # test injection only; not a profile field
) -> None:
    self.weight = weight
    ...
    self.adapter = _adapter or KronosAdapter.from_profile({
        "pred_len": pred_len, ...
    })
```

The `_adapter` parameter uses a leading underscore to signal it is not a valid profile key. Because `build_signals` passes only the profile `params` dict (which never contains `_adapter`), live construction always calls `KronosAdapter.from_profile()`. Tests construct a `KronosAdapter(predictor=FakePredictor(...), ...)` and pass it as `_adapter=` — no torch import required.

---

## Confluence Registration

```python
# src/swingbot/confluence.py
from swingbot.signals.kronos_forecast import KronosForecastSignal

_REGISTRY = {
    "oversold": OversoldSignal,
    "vwap": VwapSignal,
    "relative_strength": RelativeStrengthSignal,
    "fvg": FvgSignal,
    "kronos_forecast": KronosForecastSignal,   # new
}
```

`kronos_forecast.py` does not import torch at module level, so this import is always safe regardless of whether `[kronos]` is installed.

### Profile Config Example

```json
{
  "signals": {
    "kronos_forecast": {
      "weight": 0.25,
      "pred_len": 4,
      "threshold_pct": 0.02,
      "min_history": 50,
      "neutral_on_error": true
    }
  }
}
```

---

## Backtest Lookahead Safety (Phase 2)

`run_backtest` already passes `df.iloc[:i+1]` as `ctx.candles`. The adapter's cache key is `candles["ts"].iloc[-1]`, which equals `df["ts"].iloc[i]`. This makes each bar's forecast structurally isolated from future bars — no special handling required.

### Precomputed Cache (Phase 2)

For acceptable backtest speed, `KronosAdapter` accepts an optional `precomputed: dict[datetime, pd.DataFrame]` mapping. When populated, `forecast()` is a dict lookup (zero inference). A helper function:

```python
def precompute_forecasts(
    df: pd.DataFrame,
    adapter: KronosAdapter,
    warmup: int,
) -> dict[datetime, pd.DataFrame | None]:
    """Run inference for every bar from warmup to end. Returns cache dict."""
```

Called once at the top of `run_backtest` when the signal list contains a `KronosForecastSignal`. The adapter is populated with the result before the main loop begins.

`run_backtest` detects whether any signal is an instance of `KronosForecastSignal` and calls `precompute_forecasts` automatically. No changes to `StrategyProfile` or the main loop logic.

---

## Optional Dependency

```toml
[project.optional-dependencies]
kronos = [
    "torch>=2.0",
    "huggingface_hub>=0.20",
    "einops",
    "safetensors",
    "tqdm",
]
```

Install: `pip install -e ".[kronos]"`  
Normal install and `swingbot[dev]` tests: no torch, no ML packages.

---

## Test Strategy

### Phase 1 — Unit Tests (no torch required)

File: `tests/test_kronos_forecast.py`

```
FakePredictor:
    A class satisfying PredictorProtocol.
    Accepts a fixed forecast DataFrame in __init__.
    Tracks call_count for cache verification.

Helper _df(closes):
    Returns minimal SwingBot candle DataFrame (same pattern as test_signals.py).

Helper _forecast(closes):
    Returns minimal Kronos-format forecast DataFrame.
```

| Test | Expected result |
|------|-----------------|
| `test_bullish_forecast_scores_high` | FakePredictor returns +3% close; score ≥ 0.9 |
| `test_flat_forecast_scores_zero` | 0% change; score == 0.0 |
| `test_negative_forecast_scores_zero` | −2% change; score == 0.0 (clamped, not negative) |
| `test_forecast_timeout_returns_neutral` | adapter.forecast returns None; signal returns score 0.5 |
| `test_insufficient_history_returns_zero` | len(candles) < min_history; score 0.0, no adapter call |
| `test_confluence_accepts_kronos_signal` | build_signals with kronos_forecast profile; no error |
| `test_candle_ts_renamed_to_datetime` | predictor receives df with "datetime" column, not "ts" |
| `test_cache_calls_predictor_once` | two evaluate() calls with same last ts; call_count == 1 |
| `test_neutral_on_error_false_returns_zero` | adapter returns None, neutral_on_error=False; score 0.0 |

### Phase 2 — Backtest Tests

File: `tests/test_kronos_backtest.py`

| Test | Expected result |
|------|-----------------|
| `test_lookahead_safe` | FakePredictor at bar i receives candles[:i+1]; asserts max ts in input == df["ts"].iloc[i] |
| `test_precompute_cache_matches_live` | precomputed dict produces identical scores to live inference |
| `test_precompute_skips_bars_before_warmup` | no forecast generated for bars < warmup |

### Phase 4 — Smoke Test (env-gated)

File: `tests/test_kronos_smoke.py`

```python
@pytest.mark.skipif(
    not os.environ.get("KRONOS_SMOKE_TEST"),
    reason="set KRONOS_SMOKE_TEST=1 to run real model"
)
def test_real_predictor_returns_correct_shape():
    # Loads real Kronos model, runs predict() on synthetic OHLCV data,
    # asserts output has columns [open, high, low, close] and pred_len rows.
```

Run with: `KRONOS_SMOKE_TEST=1 pytest tests/test_kronos_smoke.py -v`

---

## What Is Not Changing

- `MarketContext`, `SignalResult`, `ConfluenceResult`, `EntrySignal`, `OpenPosition` — unchanged.
- `Signal` protocol — unchanged.
- `RegimeFilter`, `RiskManager`, `SizingEngine`, all broker adapters — unchanged.
- `run_backtest` loop logic — unchanged (Phase 2 adds a precompute call before the loop).
- `Orchestrator.tick()` — unchanged.
- Dashboard API — unchanged until Phase 3.
- `StrategyProfile` dataclass — unchanged (Kronos params live inside `signals` dict like all other signals).
