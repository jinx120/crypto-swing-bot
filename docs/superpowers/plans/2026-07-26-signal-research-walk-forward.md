# Signal Research & Walk-Forward Promotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable walk-forward validation harness plus keyless data ingress for three candidate signals (4h EMA trend, funding-rate mean reversion, exchange-flow proxy), run the research in `lab/`, and promote to the live engine only what clears the live-cost gate.

**Architecture:** All research runs in `lab/` against the existing vectorized `run_backtest_fast` harness (bit-for-bit validated against production `run_backtest`). Two new signal types are implemented **once**, as real `Signal` classes in `src/swingbot/signals/`, and mirrored by vectorized branches in the lab harness with a parity test pinning the two implementations together — so research fidelity and live behaviour cannot diverge. Non-price series (funding, premium) land in a new generic `SeriesStore` and reach signals through a new `MarketContext.extras` field. Promotion is gated on an explicit, coded verdict function; nothing reaches the live engine that has not passed it.

**Tech Stack:** Python 3.11, pandas/numpy, ccxt 4.5.56, SQLite, pytest, ruff. No new dependencies.

## Global Constraints

- **Branch:** `core-engine`. One commit per task. Push after each task.
- **Backend gate (must stay green):** `.venv/bin/python -m pytest -q` — baseline is **534 passed, 5 skipped** — and `.venv/bin/ruff check src/`.
- **Docker rebuild is mandatory and pre-authorized for every change under `src/`:** `docker compose build swingbot && docker compose up -d swingbot`. Do not ask; just run it as part of the task. Changes confined to `lab/`, `tests/`, `docs/`, or `pyproject.toml` do **not** require a rebuild.
- **Research data dir:** `SWINGBOT_DATA_DIR=/tmp/swingbot-bt`. `/tmp` is ephemeral — re-run the backfill in Task 3 after any host reboot. The host `~/.swingbot/candles.db` is root-owned and read-only; never write research data there.
- **Live cost tier = 60 bps round trip** — `fee_rate=0.0025` per side + `slippage_rate=0.0005` per side. This is the `StrategyProfile` default and Alpaca's real crypto cost.
- **The promotion gate is evaluated at 60 bps only.** Lower tiers (0/10/25 bps) are reported as diagnostic context, never as a pass condition. A signal that is only profitable below 60 bps is a REJECT.
- **Long-only.** The bot opens `Side.LONG` positions exclusively. Every signal returns a score in `0..1` where higher = stronger long case. There is no short path; a bearish signal expresses itself as a score near 0.
- **No paid API keys and no new accounts.** Verified keyless sources for this host (2026-07-26):
  - Funding rates: **Hyperliquid** via ccxt, symbol `BTC/USDC:USDC`, hourly, history from **2023-05-12**. (Binance → HTTP 451 geo-block; `binanceus` is spot-only with no perpetuals so it has no funding rates at all; Bybit → CloudFront 403; OKX funding history is capped at ~97 days.)
  - Exchange-flow proxy: **Coinbase premium** = Coinbase `BTC/USD` vs OKX `BTC/USDT` spot close spread. OKX spot OHLCV paginates keyless from 2022. This replaces spec §6c's on-chain net flow, which has **no** free data source (Glassnode/CryptoQuant exchange-flow metrics are paid tiers only).
- **No network calls in unit tests.** Every ingest function takes an injected exchange/provider object; tests pass fakes.
- **Never mutate live state during research.** No writes to `~/.swingbot/`, no `PUT`/`POST` against the running container.

---

## File Structure

**Create — `lab/` (research, not shipped in the Docker image):**
- `lab/research_data.py` — shared loaders: `load`, `resample`, `align`, `attach_extra`, `split_extras`.
- `lab/walkforward.py` — `Window`, `generate_windows`, `apply_combo`, `walk_forward`, `promotion_verdict`.
- `lab/funding_ingest.py` — Hyperliquid funding history → `SeriesStore`.
- `lab/premium_ingest.py` — Coinbase/OKX premium series → `SeriesStore`.
- `lab/research_ema_4h.py` — walk-forward runner for spec §6a.
- `lab/research_funding.py` — walk-forward runner for spec §6b.
- `lab/research_premium.py` — walk-forward runner for the §6c substitute.

**Create — `src/` (shipped; each requires a Docker rebuild):**
- `src/swingbot/data/series_store.py` — `SeriesStore`: generic `(name, symbol, ts, value)` SQLite table.
- `src/swingbot/signals/funding.py` — `FundingMeanReversionSignal`.
- `src/swingbot/signals/premium_flow.py` — `PremiumFlowSignal`.
- `src/swingbot/fusion.py` — regime-aware signal weighting (spec §6 "Signal Fusion").

**Create — tests:**
- `tests/test_series_store.py`, `tests/test_lab_walkforward.py`, `tests/test_lab_ingest.py`,
  `tests/test_signal_funding.py`, `tests/test_signal_premium_flow.py`,
  `tests/test_lab_signal_parity.py`, `tests/test_fusion.py`.

**Create — docs:**
- `docs/SIGNAL_RESEARCH_FINDINGS.md` — evidence + verdict per signal (the deliverable of Phase 4).

**Modify:**
- `pyproject.toml` — add repo root to `pythonpath` so `tests/` can import `lab.*`.
- `lab/strategy_backtest.py` — `extras` support in `_signal_scores` / `run_backtest_fast`.
- `src/swingbot/types.py` — add `MarketContext.extras`.
- `src/swingbot/confluence.py` — register the two new signals.
- `src/swingbot/orchestrator.py`, `src/swingbot/supervisor.py` — live `extras` wiring (Phase 5 only).
- `docs/ROADMAP_STATUS.md` — session record.

---

## Phase 1 — Walk-forward harness

### Task 1: Shared research loaders + `lab` importable from tests

**Files:**
- Modify: `pyproject.toml:29-33`
- Create: `lab/research_data.py`
- Test: `tests/test_lab_research_data.py`

**Interfaces:**
- Consumes: `lab.strategy_backtest.load`, `lab.strategy_backtest.align` (existing).
- Produces: `resample(df, rule) -> pd.DataFrame`; `attach_extra(df, key, series_df) -> pd.DataFrame`; `split_extras(df) -> tuple[pd.DataFrame, dict[str, np.ndarray]]`; constant `EXTRA_PREFIX = "x_"`. Re-exports `load`, `align`.

- [x] **Step 1: Make `lab` importable under pytest**

`tests/` currently cannot `import lab.*` — pytest only puts `src` and `tests/` on `sys.path`. Edit the `[tool.pytest.ini_options]` block in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
pythonpath = ["src", "."]
testpaths = ["tests"]
markers = ["integration: opt-in tests that require a live :8000 instance"]
```

- [x] **Step 2: Write the failing test**

Create `tests/test_lab_research_data.py`:

```python
import numpy as np
import pandas as pd

from lab.research_data import EXTRA_PREFIX, attach_extra, resample, split_extras


def _bars(n, start="2024-01-01", freq="15min"):
    ts = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({
        "ts": ts,
        "open": np.arange(n, dtype=float) + 100.0,
        "high": np.arange(n, dtype=float) + 101.0,
        "low": np.arange(n, dtype=float) + 99.0,
        "close": np.arange(n, dtype=float) + 100.5,
        "volume": np.ones(n),
    })


def test_resample_15m_to_4h_aggregates_ohlcv():
    df = _bars(32)  # 32 x 15m == 8h == two 4h bars
    out = resample(df, "4h")
    assert len(out) == 2
    assert out["open"].iloc[0] == df["open"].iloc[0]
    assert out["close"].iloc[0] == df["close"].iloc[15]
    assert out["high"].iloc[0] == df["high"].iloc[:16].max()
    assert out["low"].iloc[0] == df["low"].iloc[:16].min()
    assert out["volume"].iloc[0] == 16.0


def test_attach_extra_is_causal_backward_asof():
    df = _bars(4, freq="1h")
    series = pd.DataFrame({
        "ts": pd.to_datetime(["2024-01-01 00:00", "2024-01-01 02:00"], utc=True),
        "value": [0.1, 0.9],
    })
    merged = attach_extra(df, "funding_8h", series)
    col = merged[EXTRA_PREFIX + "funding_8h"].tolist()
    # bar 0 and 1 see the 00:00 reading; bars 2,3 see the 02:00 reading.
    # No bar ever sees a value stamped after its own ts.
    assert col == [0.1, 0.1, 0.9, 0.9]


def test_attach_extra_leaves_nan_before_first_reading():
    df = _bars(3, freq="1h")
    series = pd.DataFrame({
        "ts": pd.to_datetime(["2024-01-01 02:00"], utc=True),
        "value": [0.5],
    })
    merged = attach_extra(df, "cb_premium", series)
    col = merged[EXTRA_PREFIX + "cb_premium"]
    assert bool(col.isna().iloc[0]) and bool(col.isna().iloc[1])
    assert col.iloc[2] == 0.5


def test_split_extras_returns_ohlcv_frame_and_arrays():
    df = attach_extra(_bars(3, freq="1h"), "funding_8h", pd.DataFrame(
        {"ts": pd.to_datetime(["2024-01-01 00:00"], utc=True), "value": [0.2]}))
    ohlc, extras = split_extras(df)
    assert list(ohlc.columns) == ["ts", "open", "high", "low", "close", "volume"]
    assert set(extras) == {"funding_8h"}
    assert extras["funding_8h"].tolist() == [0.2, 0.2, 0.2]
```

- [x] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_lab_research_data.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'lab.research_data'`

- [x] **Step 4: Write the implementation**

Create `lab/research_data.py`:

```python
"""Shared data helpers for the signal-research runners.

Everything here is causal: a bar never sees a value stamped after its own ts.
`load`/`align` are re-exported from the validated 2026-06 harness so the research
runners have a single import surface.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lab.strategy_backtest import align, load  # noqa: F401  (re-export)

EXTRA_PREFIX = "x_"
_OHLCV = ["ts", "open", "high", "low", "close", "volume"]


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample OHLCV bars to a coarser timeframe (e.g. 15m -> '4h')."""
    d = df.set_index("ts")
    out = d.resample(rule).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return out.dropna().reset_index()


def attach_extra(df: pd.DataFrame, key: str, series_df: pd.DataFrame) -> pd.DataFrame:
    """Merge a (ts, value) series onto bars as column `x_<key>`.

    Uses a BACKWARD as-of join: each bar carries the most recent reading at or
    before its own timestamp, so there is no lookahead. Bars earlier than the
    first reading get NaN, which every consumer maps to a neutral 0.5 score.
    """
    right = series_df.sort_values("ts")[["ts", "value"]].rename(
        columns={"value": EXTRA_PREFIX + key})
    return pd.merge_asof(df.sort_values("ts"), right, on="ts", direction="backward")


def split_extras(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    """Split a frame built by attach_extra back into (OHLCV frame, extras arrays).

    Windowing/slicing happens on the combined frame so extras can never fall out
    of alignment with the bars they were joined to.
    """
    extras = {
        c[len(EXTRA_PREFIX):]: df[c].to_numpy(dtype=float)
        for c in df.columns if c.startswith(EXTRA_PREFIX)
    }
    return df[_OHLCV].reset_index(drop=True), extras
```

- [x] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_lab_research_data.py -q`
Expected: 4 passed

- [x] **Step 6: Confirm the full suite still collects**

Run: `.venv/bin/python -m pytest -q`
Expected: 538 passed, 5 skipped (534 baseline + 4 new)

- [x] **Step 7: Commit**

```bash
git add pyproject.toml lab/research_data.py tests/test_lab_research_data.py
git commit -m "feat(lab): shared research loaders + causal extras attachment"
git push origin core-engine
```

---

### Task 2: Walk-forward window generation and parameter selection

**Files:**
- Create: `lab/walkforward.py`
- Test: `tests/test_lab_walkforward.py`

**Interfaces:**
- Consumes: `lab.strategy_backtest.run_backtest_fast` (extended in Task 5 with `extras`; this task calls it without extras), `lab.strategy_backtest._warmup_bars` is NOT used — use `swingbot.backtest._warmup_bars`.
- Produces:
  - `@dataclass(frozen=True) Window(train_start, train_end, test_start, test_end)` — all `pd.Timestamp`.
  - `generate_windows(first_ts, last_ts, train_days=365, test_days=90, step_days=90) -> list[Window]`
  - `apply_combo(profile: StrategyProfile, combo: dict) -> StrategyProfile` — dotted keys (`"ema_trend.fast"`) target `profile.signals`, bare keys target top-level fields.
  - `with_cost(profile, round_trip: float) -> StrategyProfile`

- [x] **Step 1: Write the failing test**

Create `tests/test_lab_walkforward.py`:

```python
import pandas as pd
import pytest

from lab.walkforward import Window, apply_combo, generate_windows, with_cost
from swingbot.profile import StrategyProfile


def _ts(s):
    return pd.Timestamp(s, tz="UTC")


def test_generate_windows_rolls_forward_by_step():
    ws = generate_windows(_ts("2022-01-01"), _ts("2024-01-01"),
                          train_days=365, test_days=90, step_days=90)
    assert ws[0] == Window(_ts("2022-01-01"), _ts("2023-01-01"),
                           _ts("2023-01-01"), _ts("2023-04-01"))
    assert ws[1].train_start == _ts("2022-04-01")
    # test period always starts exactly where training ended: no gap, no overlap
    assert all(w.test_start == w.train_end for w in ws)


def test_generate_windows_drops_a_window_that_would_run_past_the_data():
    ws = generate_windows(_ts("2022-01-01"), _ts("2023-02-01"),
                          train_days=365, test_days=90, step_days=90)
    assert ws == []  # 2022-01-01 + 365d + 90d = 2023-04-01 > 2023-02-01


def test_generate_windows_rejects_nonpositive_spans():
    with pytest.raises(ValueError):
        generate_windows(_ts("2022-01-01"), _ts("2024-01-01"), train_days=0)


def test_apply_combo_sets_nested_signal_params_and_top_level_fields():
    base = StrategyProfile(symbol="BTC/USD",
                           signals={"ema_trend": {"weight": 1.0, "fast": 21, "slow": 55}},
                           entry_threshold=0.65)
    out = apply_combo(base, {"ema_trend.fast": 8, "ema_trend.slow": 34,
                             "entry_threshold": 0.5})
    assert out.signals["ema_trend"]["fast"] == 8
    assert out.signals["ema_trend"]["slow"] == 34
    assert out.entry_threshold == 0.5
    # the base profile must not be mutated - combos are evaluated in a loop
    assert base.signals["ema_trend"]["fast"] == 21
    assert base.entry_threshold == 0.65


def test_apply_combo_rejects_an_unknown_signal_name():
    base = StrategyProfile(symbol="BTC/USD", signals={"ema_trend": {"weight": 1.0}})
    with pytest.raises(KeyError):
        apply_combo(base, {"funding_mr.high_thresh": 0.1})


def test_with_cost_splits_round_trip_across_both_sides():
    p = with_cost(StrategyProfile(symbol="BTC/USD"), 0.006)
    assert p.fee_rate == 0.003
    assert p.slippage_rate == 0.0
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_lab_walkforward.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'lab.walkforward'`

- [x] **Step 3: Write the implementation**

Create `lab/walkforward.py`:

```python
"""Walk-forward validation for candidate trading signals.

Method: split history into rolling (train, test) window pairs. Inside each
window, pick the best parameter combination on the TRAIN slice only, then trade
that frozen combination through the TEST slice. Concatenating the test slices
gives a single out-of-sample record with no in-sample parameter fitting in it.

Every backtest runs through the validated `run_backtest_fast` (bit-for-bit equal
to production `run_backtest`), so the exits, sizing and broker are the real ones.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import pandas as pd

from swingbot.profile import StrategyProfile


@dataclass(frozen=True)
class Window:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def generate_windows(first_ts, last_ts, train_days: int = 365,
                     test_days: int = 90, step_days: int = 90) -> list[Window]:
    """Rolling train/test splits covering [first_ts, last_ts].

    A window is emitted only if its full test period fits inside the data, so a
    truncated final window can never inflate or deflate the out-of-sample record.
    """
    if train_days <= 0 or test_days <= 0 or step_days <= 0:
        raise ValueError("train_days, test_days and step_days must all be > 0")
    first, last = pd.Timestamp(first_ts), pd.Timestamp(last_ts)
    train_len = pd.Timedelta(days=train_days)
    test_len = pd.Timedelta(days=test_days)
    step = pd.Timedelta(days=step_days)

    windows: list[Window] = []
    train_start = first
    while True:
        train_end = train_start + train_len
        test_end = train_end + test_len
        if test_end > last:
            return windows
        windows.append(Window(train_start, train_end, train_end, test_end))
        train_start = train_start + step


def apply_combo(profile: StrategyProfile, combo: dict) -> StrategyProfile:
    """Return a COPY of `profile` with a parameter combination applied.

    Dotted keys ("ema_trend.fast") set a param inside profile.signals; bare keys
    ("entry_threshold") set a top-level profile field. The input profile and its
    nested signal dicts are never mutated, so a combo loop stays independent.
    """
    signals = {name: dict(params) for name, params in profile.signals.items()}
    top: dict = {}
    for key, value in combo.items():
        if "." in key:
            signal_name, param = key.split(".", 1)
            if signal_name not in signals:
                raise KeyError(f"combo targets unknown signal {signal_name!r}")
            signals[signal_name][param] = value
        else:
            top[key] = value
    return dataclasses.replace(profile, signals=signals, **top)


def with_cost(profile: StrategyProfile, round_trip: float) -> StrategyProfile:
    """Set the total round-trip cost, charged symmetrically as fees."""
    return dataclasses.replace(profile, fee_rate=round_trip / 2.0, slippage_rate=0.0)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_lab_walkforward.py -q`
Expected: 6 passed

- [x] **Step 5: Commit**

```bash
git add lab/walkforward.py tests/test_lab_walkforward.py
git commit -m "feat(lab): walk-forward window generation and combo application"
git push origin core-engine
```

---

### Task 3: Walk-forward runner and the promotion gate

**Files:**
- Modify: `lab/walkforward.py`
- Test: `tests/test_lab_walkforward.py` (append)

**Interfaces:**
- Consumes: `Window`, `generate_windows`, `apply_combo`, `with_cost` (Task 2); `lab.research_data.split_extras` (Task 1); `swingbot.backtest._warmup_bars`; `lab.strategy_backtest.run_backtest_fast`.
- Produces:
  - `@dataclass(frozen=True) WindowResult(window, combo, train_pf, trades, net_pnl)`
  - `@dataclass(frozen=True) WalkForwardResult(label, symbol, windows, oos_trades)`
  - `walk_forward(df, base_profile, grid, *, round_trip, train_days=365, test_days=90, step_days=90, min_train_trades=20, benchmark_df=None, starting_equity=1000.0) -> WalkForwardResult`
  - `@dataclass(frozen=True) Verdict(label, symbol, decision, reason, n_trades, net_return_pct, profit_factor, positive_window_frac)`
  - `promotion_verdict(result, *, min_trades=30, min_pf=1.10, min_positive_window_frac=0.5) -> Verdict`
  - `profit_factor(trades) -> float`

`df` passed to `walk_forward` is the combined frame from `attach_extra` (OHLCV plus any `x_*` columns); `walk_forward` slices it and calls `split_extras` internally so extras stay aligned with their bars.

- [x] **Step 1: Write the failing test**

Append to `tests/test_lab_walkforward.py`:

```python
from lab.walkforward import (
    WalkForwardResult, WindowResult, profit_factor, promotion_verdict, walk_forward,
)


class _FakeTrade:
    """Minimal stand-in for swingbot.journal.Trade for gate arithmetic."""

    def __init__(self, entry_ts, pnl, entry_price=100.0, qty=1.0):
        self.entry_ts = entry_ts
        self.exit_ts = entry_ts + pd.Timedelta(hours=4)
        self.pnl = pnl
        self.entry_price = entry_price
        self.qty = qty


def _result(pnls_by_window, label="x", symbol="BTC/USD"):
    windows, oos = [], []
    for i, pnls in enumerate(pnls_by_window):
        start = _ts("2023-01-01") + pd.Timedelta(days=90 * i)
        trades = [_FakeTrade(start + pd.Timedelta(hours=j), p) for j, p in enumerate(pnls)]
        oos.extend(trades)
        windows.append(WindowResult(
            window=Window(start, start, start, start + pd.Timedelta(days=90)),
            combo={}, train_pf=1.5, trades=trades, net_pnl=sum(pnls)))
    return WalkForwardResult(label=label, symbol=symbol, windows=windows, oos_trades=oos)


def test_profit_factor_is_gross_profit_over_gross_loss():
    assert profit_factor([_FakeTrade(_ts("2023-01-01"), 30.0),
                          _FakeTrade(_ts("2023-01-02"), -10.0)]) == 3.0


def test_profit_factor_of_no_trades_is_zero():
    assert profit_factor([]) == 0.0


def test_promotion_verdict_promotes_a_profitable_consistent_signal():
    # 4 windows, all positive, PF = 400/100 = 4.0, 40 trades
    v = promotion_verdict(_result([[20.0] * 5 + [-5.0] * 5] * 4))
    assert v.decision == "PROMOTE"
    assert v.n_trades == 40
    assert v.profit_factor == 4.0
    assert v.positive_window_frac == 1.0


def test_promotion_verdict_rejects_when_too_few_trades():
    v = promotion_verdict(_result([[20.0] * 5]))
    assert v.decision == "REJECT"
    assert "trades" in v.reason


def test_promotion_verdict_rejects_a_profitable_signal_carried_by_one_window():
    # window 1 huge winner, windows 2-4 losers -> PF passes but consistency fails
    v = promotion_verdict(_result([[100.0] * 10, [-1.0] * 10, [-1.0] * 10, [-1.0] * 10]))
    assert v.decision == "REJECT"
    assert "window" in v.reason


def test_promotion_verdict_rejects_negative_net_return():
    v = promotion_verdict(_result([[5.0, -20.0] * 6, [5.0, -20.0] * 6,
                                   [5.0, -20.0] * 6, [5.0, -20.0] * 6]))
    assert v.decision == "REJECT"


def test_walk_forward_never_trains_and_tests_on_the_same_bars(monkeypatch):
    """The recorded out-of-sample trades must all fall inside test periods."""
    import lab.walkforward as wf

    seen_ranges = []

    def fake_run(df, profile, benchmark_df=None, starting_equity=1000.0,
                 kronos_pct=None, extras=None):
        seen_ranges.append((df["ts"].iloc[0], df["ts"].iloc[-1]))
        mid = df["ts"].iloc[len(df) // 2]
        return [_FakeTrade(mid, 1.0) for _ in range(25)], None

    monkeypatch.setattr(wf, "run_backtest_fast", fake_run)

    ts = pd.date_range("2022-01-01", periods=365 * 3 * 6, freq="4h", tz="UTC")
    df = pd.DataFrame({"ts": ts, "open": 100.0, "high": 101.0, "low": 99.0,
                       "close": 100.0, "volume": 1.0})
    base = StrategyProfile(symbol="BTC/USD",
                           signals={"ema_trend": {"weight": 1.0, "fast": 21, "slow": 55}})
    res = walk_forward(df, base, [{"ema_trend.fast": 8}, {"ema_trend.fast": 21}],
                       round_trip=0.006)

    assert len(res.windows) >= 4
    for w in res.windows:
        for t in w.trades:
            assert w.window.test_start <= t.entry_ts <= w.window.test_end
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_lab_walkforward.py -q`
Expected: FAIL with `ImportError: cannot import name 'walk_forward'`

- [x] **Step 3: Write the implementation**

Append to `lab/walkforward.py` (add the imports at the top of the file alongside the existing ones):

```python
from lab.research_data import split_extras
from lab.strategy_backtest import run_backtest_fast
from swingbot.backtest import _warmup_bars


@dataclass(frozen=True)
class WindowResult:
    window: Window
    combo: dict
    train_pf: float
    trades: list
    net_pnl: float


@dataclass(frozen=True)
class WalkForwardResult:
    label: str
    symbol: str
    windows: list[WindowResult]
    oos_trades: list


@dataclass(frozen=True)
class Verdict:
    label: str
    symbol: str
    decision: str          # "PROMOTE" | "REJECT"
    reason: str
    n_trades: int
    net_return_pct: float
    profit_factor: float
    positive_window_frac: float


def profit_factor(trades) -> float:
    gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss = -sum(t.pnl for t in trades if t.pnl < 0)
    if gross_loss > 0:
        return gross_profit / gross_loss
    return float("inf") if gross_profit > 0 else 0.0


def _slice(df: pd.DataFrame, start, end, warmup: int) -> pd.DataFrame:
    """Bars in [start, end] plus `warmup` bars of lead-in for the indicators.

    The lead-in is required (indicators need history) but must not produce
    tradeable bars, so callers filter the returned trades by entry_ts >= start.
    """
    positions = df.index[df["ts"] >= start]
    if len(positions) == 0:
        return df.iloc[0:0]
    first = max(0, int(positions[0]) - warmup)
    window = df.iloc[first:]
    return window[window["ts"] <= end].reset_index(drop=True)


def _run(df: pd.DataFrame, profile, benchmark_df, starting_equity):
    ohlc, extras = split_extras(df)
    trades, _ = run_backtest_fast(
        ohlc, profile, benchmark_df=benchmark_df,
        starting_equity=starting_equity, extras=extras or None)
    return trades


def walk_forward(df: pd.DataFrame, base_profile: StrategyProfile, grid: list[dict], *,
                 round_trip: float, train_days: int = 365, test_days: int = 90,
                 step_days: int = 90, min_train_trades: int = 20,
                 benchmark_df: pd.DataFrame | None = None,
                 starting_equity: float = 1000.0) -> WalkForwardResult:
    """Roll train/test windows, fitting `grid` on train and trading it on test.

    Selection metric on the training slice is profit factor at the SAME cost tier
    the verdict is graded at - selecting on gross performance and grading on net
    would pick parameters that only work at costs we do not pay.
    """
    costed = with_cost(base_profile, round_trip)
    # Warmup must cover the HUNGRIEST combo in the grid, not the base profile: a
    # combo that raises `lookback` needs more lead-in, and slicing to the base
    # profile's warmup would silently feed it a neutral score for hundreds of
    # bars into the test window.
    warmup = max(_warmup_bars(apply_combo(costed, c)) for c in grid) if grid \
        else _warmup_bars(costed)
    windows = generate_windows(df["ts"].iloc[0], df["ts"].iloc[-1],
                               train_days=train_days, test_days=test_days,
                               step_days=step_days)

    results: list[WindowResult] = []
    oos: list = []
    for window in windows:
        train_df = _slice(df, window.train_start, window.train_end, warmup)
        best_combo, best_pf = None, float("-inf")
        for combo in grid:
            trades = _run(train_df, apply_combo(costed, combo), benchmark_df, starting_equity)
            trades = [t for t in trades if t.entry_ts >= window.train_start]
            if len(trades) < min_train_trades:
                continue
            pf = profit_factor(trades)
            if pf > best_pf:
                best_combo, best_pf = combo, pf
        if best_combo is None:
            continue  # nothing traded enough on this training slice to choose from

        test_df = _slice(df, window.test_start, window.test_end, warmup)
        test_trades = _run(test_df, apply_combo(costed, best_combo),
                           benchmark_df, starting_equity)
        test_trades = [t for t in test_trades if t.entry_ts >= window.test_start]
        oos.extend(test_trades)
        results.append(WindowResult(
            window=window, combo=best_combo, train_pf=best_pf,
            trades=test_trades, net_pnl=sum(t.pnl for t in test_trades)))

    return WalkForwardResult(label=base_profile.label or "unlabelled",
                             symbol=base_profile.symbol,
                             windows=results, oos_trades=oos)


def promotion_verdict(result: WalkForwardResult, *, min_trades: int = 30,
                      min_pf: float = 1.10,
                      min_positive_window_frac: float = 0.5) -> Verdict:
    """Grade an out-of-sample record. PROMOTE only if ALL conditions hold.

    A signal must be (a) traded often enough to be more than noise, (b) net
    positive overall, (c) profitable enough to be worth the risk, and (d)
    consistent across windows rather than carried by one lucky quarter.
    """
    trades = result.oos_trades
    n = len(trades)
    notional = sum(t.entry_price * t.qty for t in trades)
    net_pct = (sum(t.pnl for t in trades) / notional * 100.0) if notional else 0.0
    pf = profit_factor(trades)
    positive = sum(1 for w in result.windows if w.net_pnl > 0)
    frac = positive / len(result.windows) if result.windows else 0.0

    reasons = []
    if n < min_trades:
        reasons.append(f"only {n} out-of-sample trades (need >= {min_trades})")
    if net_pct <= 0:
        reasons.append(f"net return {net_pct:.2f}% is not positive")
    if pf < min_pf:
        reasons.append(f"profit factor {pf:.2f} below {min_pf:.2f}")
    if frac < min_positive_window_frac:
        reasons.append(
            f"only {frac:.0%} of windows positive (need >= {min_positive_window_frac:.0%})")

    return Verdict(
        label=result.label, symbol=result.symbol,
        decision="REJECT" if reasons else "PROMOTE",
        reason="; ".join(reasons) if reasons else "passed all walk-forward criteria",
        n_trades=n, net_return_pct=net_pct, profit_factor=pf,
        positive_window_frac=frac)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_lab_walkforward.py -q`
Expected: 13 passed

- [x] **Step 5: Commit**

```bash
git add lab/walkforward.py tests/test_lab_walkforward.py
git commit -m "feat(lab): walk-forward runner and out-of-sample promotion gate"
git push origin core-engine
```

---

## Phase 2 — Data ingress

### Task 4: `SeriesStore` for non-price series

**Files:**
- Create: `src/swingbot/data/series_store.py`
- Test: `tests/test_series_store.py`

**Interfaces:**
- Produces: `SeriesStore(path)` with `upsert(name, symbol, rows) -> int` where `rows: list[tuple[int, float]]` of `(epoch_seconds, value)`; `get_df(name, symbol, start_ts=None, end_ts=None) -> pd.DataFrame` with columns `["ts", "value"]` and tz-aware UTC `ts`; `coverage(name, symbol) -> dict` with keys `min_ts`, `max_ts`, `count`; `names() -> list[dict]`.

This module ships inside the Docker image (a promoted signal reads from it live), so it mirrors `CandleStore`'s conventions exactly: WAL mode, a `threading.Lock`, epoch-second storage, idempotent `INSERT OR REPLACE`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_series_store.py`:

```python
import pandas as pd

from swingbot.data.series_store import SeriesStore


def _store(tmp_path):
    return SeriesStore(str(tmp_path / "series.db"))


def test_upsert_then_get_df_returns_utc_timestamps_oldest_first(tmp_path):
    s = _store(tmp_path)
    assert s.upsert("funding_8h", "BTC/USD", [(1700000000, 0.0004),
                                              (1699999000, 0.0001)]) == 2
    df = s.get_df("funding_8h", "BTC/USD")
    assert list(df.columns) == ["ts", "value"]
    assert df["ts"].is_monotonic_increasing
    assert str(df["ts"].dt.tz) == "UTC"
    assert df["value"].tolist() == [0.0001, 0.0004]


def test_upsert_is_idempotent_on_the_same_timestamp(tmp_path):
    s = _store(tmp_path)
    s.upsert("funding_8h", "BTC/USD", [(1700000000, 0.0004)])
    s.upsert("funding_8h", "BTC/USD", [(1700000000, 0.0009)])
    df = s.get_df("funding_8h", "BTC/USD")
    assert len(df) == 1
    assert df["value"].iloc[0] == 0.0009  # last write wins, no duplicate row


def test_series_are_isolated_by_name_and_symbol(tmp_path):
    s = _store(tmp_path)
    s.upsert("funding_8h", "BTC/USD", [(1, 0.1)])
    s.upsert("cb_premium", "BTC/USD", [(1, 0.2)])
    s.upsert("funding_8h", "ETH/USD", [(1, 0.3)])
    assert s.get_df("funding_8h", "BTC/USD")["value"].tolist() == [0.1]
    assert s.get_df("cb_premium", "BTC/USD")["value"].tolist() == [0.2]
    assert s.get_df("funding_8h", "ETH/USD")["value"].tolist() == [0.3]


def test_get_df_honours_the_time_bounds(tmp_path):
    s = _store(tmp_path)
    s.upsert("f", "BTC/USD", [(100, 1.0), (200, 2.0), (300, 3.0)])
    assert s.get_df("f", "BTC/USD", start_ts=200)["value"].tolist() == [2.0, 3.0]
    assert s.get_df("f", "BTC/USD", end_ts=200)["value"].tolist() == [1.0, 2.0]
    assert s.get_df("f", "BTC/USD", start_ts=200, end_ts=200)["value"].tolist() == [2.0]


def test_get_df_on_an_unknown_series_returns_an_empty_typed_frame(tmp_path):
    df = _store(tmp_path).get_df("nope", "BTC/USD")
    assert df.empty
    assert list(df.columns) == ["ts", "value"]


def test_coverage_reports_bounds_and_count(tmp_path):
    s = _store(tmp_path)
    s.upsert("f", "BTC/USD", [(100, 1.0), (300, 3.0)])
    assert s.coverage("f", "BTC/USD") == {"min_ts": 100, "max_ts": 300, "count": 2}
    assert s.coverage("f", "ETH/USD") == {"min_ts": None, "max_ts": None, "count": 0}


def test_upsert_of_nothing_writes_nothing(tmp_path):
    assert _store(tmp_path).upsert("f", "BTC/USD", []) == 0


def test_names_lists_stored_series(tmp_path):
    s = _store(tmp_path)
    s.upsert("funding_8h", "BTC/USD", [(1, 0.1)])
    s.upsert("cb_premium", "BTC/USD", [(1, 0.2)])
    assert sorted(n["name"] for n in s.names()) == ["cb_premium", "funding_8h"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_series_store.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.data.series_store'`

- [ ] **Step 3: Write the implementation**

Create `src/swingbot/data/series_store.py`:

```python
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pandas as pd

_DDL = """
CREATE TABLE IF NOT EXISTS series (
    name   TEXT NOT NULL,
    symbol TEXT NOT NULL,
    ts     INTEGER NOT NULL,
    value  REAL NOT NULL,
    PRIMARY KEY (name, symbol, ts)
);
"""

_EMPTY = pd.DataFrame({"ts": pd.Series(dtype="datetime64[ns, UTC]"),
                       "value": pd.Series(dtype="float64")})


class SeriesStore:
    """SQLite store for non-price time series (funding rates, premium spreads).

    One row per (series name, symbol, timestamp). `ts` is UTC epoch seconds, the
    same convention as CandleStore, so the two can be joined without conversion.
    """

    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as con:
            con.execute(_DDL)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=10)
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def upsert(self, name: str, symbol: str, rows: list[tuple[int, float]]) -> int:
        """Insert/replace (ts, value) pairs. Re-running an ingest is safe."""
        if not rows:
            return 0
        payload = [(name, symbol, int(ts), float(value)) for ts, value in rows]
        with self._lock, self._connect() as con:
            con.executemany(
                "INSERT OR REPLACE INTO series (name, symbol, ts, value) VALUES (?,?,?,?)",
                payload,
            )
        return len(payload)

    def get_df(self, name: str, symbol: str, start_ts: int | None = None,
               end_ts: int | None = None) -> pd.DataFrame:
        """Oldest-first (ts, value) frame with tz-aware UTC timestamps."""
        sql = "SELECT ts, value FROM series WHERE name=? AND symbol=?"
        params: list = [name, symbol]
        if start_ts is not None:
            sql += " AND ts>=?"
            params.append(int(start_ts))
        if end_ts is not None:
            sql += " AND ts<=?"
            params.append(int(end_ts))
        sql += " ORDER BY ts"
        with self._lock, self._connect() as con:
            rows = con.execute(sql, params).fetchall()
        if not rows:
            return _EMPTY.copy()
        df = pd.DataFrame(rows, columns=["ts", "value"])
        df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True)
        df["value"] = df["value"].astype(float)
        return df

    def coverage(self, name: str, symbol: str) -> dict:
        with self._lock, self._connect() as con:
            min_ts, max_ts, count = con.execute(
                "SELECT MIN(ts), MAX(ts), COUNT(*) FROM series WHERE name=? AND symbol=?",
                (name, symbol),
            ).fetchone()
        return {"min_ts": min_ts, "max_ts": max_ts, "count": count}

    def names(self) -> list[dict]:
        with self._lock, self._connect() as con:
            rows = con.execute("SELECT DISTINCT name, symbol FROM series").fetchall()
        return [{"name": n, "symbol": s} for n, s in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_series_store.py -q`
Expected: 8 passed

- [ ] **Step 5: Run the gate and rebuild the container**

```bash
.venv/bin/python -m pytest -q && .venv/bin/ruff check src/
docker compose build swingbot && docker compose up -d swingbot
```
Expected: 559 passed, 5 skipped; ruff clean; container healthy.

- [ ] **Step 6: Commit**

```bash
git add src/swingbot/data/series_store.py tests/test_series_store.py
git commit -m "feat(data): SeriesStore for non-price time series"
git push origin core-engine
```

---

### Task 5: `extras` support in the lab backtest harness

**Files:**
- Modify: `lab/strategy_backtest.py:41-88` (`_signal_scores`), `lab/strategy_backtest.py:110-150` (`run_backtest_fast`)
- Test: `tests/test_lab_extras.py`

**Interfaces:**
- Produces: `_signal_scores(df, profile, benchmark_df, kronos_pct=None, extras=None)` and `run_backtest_fast(df, profile, benchmark_df=None, starting_equity=1000.0, kronos_pct=None, extras=None)`, where `extras: dict[str, np.ndarray]` maps a series key to a per-bar array the same length as `df`. Adds vectorized branches for signal names `funding_mr` and `premium_flow`.
- The scoring formulas here are pinned to the `Signal` classes of Tasks 7 and 8 by the parity test in Task 9. **If you change a formula here, change it there too.**

- [ ] **Step 1: Write the failing test**

Create `tests/test_lab_extras.py`:

```python
import numpy as np
import pandas as pd
import pytest

from lab.strategy_backtest import _signal_scores
from swingbot.profile import StrategyProfile


def _df(n=300):
    ts = pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC")
    close = np.linspace(100.0, 200.0, n)
    return pd.DataFrame({"ts": ts, "open": close, "high": close + 1,
                         "low": close - 1, "close": close, "volume": np.ones(n)})


def test_funding_mr_scores_one_at_or_below_the_low_threshold():
    df = _df(10)
    profile = StrategyProfile(symbol="BTC/USD", signals={
        "funding_mr": {"weight": 1.0, "high_thresh": 0.0005, "low_thresh": -0.0001}})
    extras = {"funding_8h": np.full(10, -0.0005)}  # deeply negative -> crowded short
    assert _signal_scores(df, profile, None, extras=extras).tolist() == [1.0] * 10


def test_funding_mr_scores_zero_at_or_above_the_high_threshold():
    df = _df(10)
    profile = StrategyProfile(symbol="BTC/USD", signals={
        "funding_mr": {"weight": 1.0, "high_thresh": 0.0005, "low_thresh": -0.0001}})
    extras = {"funding_8h": np.full(10, 0.002)}  # crowded long -> no new longs
    assert _signal_scores(df, profile, None, extras=extras).tolist() == [0.0] * 10


def test_funding_mr_is_neutral_where_the_series_has_no_reading():
    df = _df(3)
    profile = StrategyProfile(symbol="BTC/USD", signals={"funding_mr": {"weight": 1.0}})
    extras = {"funding_8h": np.array([np.nan, np.nan, -0.001])}
    assert _signal_scores(df, profile, None, extras=extras).tolist() == [0.5, 0.5, 1.0]


def test_premium_flow_scores_high_when_premium_is_far_above_its_own_mean():
    df = _df(60)
    profile = StrategyProfile(symbol="BTC/USD", signals={
        "premium_flow": {"weight": 1.0, "lookback": 20, "band": 2.0}})
    series = np.concatenate([np.zeros(59), [10.0]])  # last bar is a huge positive z
    scores = _signal_scores(df, profile, None, extras={"cb_premium": series})
    assert scores[-1] == 1.0


def test_premium_flow_is_neutral_during_its_warmup():
    df = _df(60)
    profile = StrategyProfile(symbol="BTC/USD", signals={
        "premium_flow": {"weight": 1.0, "lookback": 20, "band": 2.0}})
    scores = _signal_scores(df, profile, None,
                            extras={"cb_premium": np.random.RandomState(0).randn(60)})
    assert scores[:19].tolist() == [0.5] * 19


def test_a_signal_that_needs_extras_fails_loudly_when_they_are_absent():
    df = _df(10)
    profile = StrategyProfile(symbol="BTC/USD", signals={"funding_mr": {"weight": 1.0}})
    with pytest.raises(ValueError, match="funding_mr"):
        _signal_scores(df, profile, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_lab_extras.py -q`
Expected: FAIL — `_signal_scores() got an unexpected keyword argument 'extras'`

- [ ] **Step 3: Add the extras branches to `_signal_scores`**

In `lab/strategy_backtest.py`, change the signature and add a lookup helper plus the two branches. Replace the `def _signal_scores(...)` line and its docstring tail, then insert the new branches immediately after the existing `kronos_forecast` branch (the block ending in `continue`):

```python
def _signal_scores(df, profile, benchmark_df, kronos_pct=None, extras=None) -> np.ndarray:
```

Add this helper above `_signal_scores`:

```python
def _extra(extras, signal_name, key):
    """Fetch a per-bar extras array, failing loudly rather than scoring silently."""
    if not extras or key not in extras:
        raise ValueError(
            f"profile uses {signal_name!r} but extras[{key!r}] was not provided")
    return np.asarray(extras[key], dtype=float)
```

Insert after the `kronos_forecast` branch:

```python
        if name == "funding_mr":
            # Mirrors FundingMeanReversionSignal: crowded longs (high funding)
            # score 0, crowded shorts (negative funding) score 1, linear between.
            arr = _extra(extras, name, params.get("series_key", "funding_8h"))
            hi = params.get("high_thresh", 0.0005)
            lo = params.get("low_thresh", -0.0001)
            s_arr = np.clip((hi - arr) / (hi - lo), 0.0, 1.0)
            total += w * np.where(np.isnan(arr), 0.5, s_arr)
            continue
        if name == "premium_flow":
            # Mirrors PremiumFlowSignal: z-score of the premium over `lookback`,
            # mapped through +/- `band` standard deviations onto 0..1.
            arr = _extra(extras, name, params.get("series_key", "cb_premium"))
            lb = int(params.get("lookback", 180))
            band = float(params.get("band", 2.0))
            s = pd.Series(arr)
            z = (s - s.rolling(lb).mean()) / s.rolling(lb).std()
            s_arr = np.clip((z.to_numpy() + band) / (2 * band), 0.0, 1.0)
            total += w * np.where(np.isfinite(z.to_numpy()), s_arr, 0.5)
            continue
```

- [ ] **Step 4: Thread `extras` through `run_backtest_fast`**

In `lab/strategy_backtest.py`, change the `run_backtest_fast` signature and its `_signal_scores` call:

```python
def run_backtest_fast(df, profile, benchmark_df=None, starting_equity=1000.0,
                      kronos_pct=None, extras=None):
```
```python
    score = _signal_scores(df, profile, benchmark_df, kronos_pct=kronos_pct, extras=extras)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_lab_extras.py -q`
Expected: 6 passed

- [ ] **Step 6: Verify the existing harness is unbroken**

Run: `.venv/bin/python -m pytest -q`
Expected: 565 passed, 5 skipped

- [ ] **Step 7: Commit**

```bash
git add lab/strategy_backtest.py tests/test_lab_extras.py
git commit -m "feat(lab): extras-aware scoring for funding and premium signals"
git push origin core-engine
```

---

### Task 6: Funding-rate and premium ingest

**Files:**
- Create: `lab/funding_ingest.py`, `lab/premium_ingest.py`
- Test: `tests/test_lab_ingest.py`

**Interfaces:**
- Consumes: `swingbot.data.series_store.SeriesStore` (Task 4), `lab.research_data.resample` (Task 1).
- Produces:
  - `funding_ingest.fetch_funding(exchange, symbol, since_ms, end_ms, page_limit=500) -> list[tuple[int, float]]` — hourly `(epoch_seconds, rate)`.
  - `funding_ingest.to_8h_equivalent(rows) -> list[tuple[int, float]]` — rolling 8-hour sum of hourly rates, so the values are directly comparable to spec §6b's 8h thresholds.
  - `funding_ingest.ingest(store, exchange, *, symbol="BTC/USDC:USDC", store_symbol="BTC/USD", since_ms, end_ms) -> int`
  - `premium_ingest.compute_premium(local_4h, offshore_4h) -> pd.DataFrame` with `["ts", "value"]`.
  - `premium_ingest.ingest(store, local_15m, offshore_provider, *, store_symbol="BTC/USD", offshore_symbol="BTC/USDT", start_ms, end_ms) -> int`

- [ ] **Step 1: Write the failing test**

Create `tests/test_lab_ingest.py`:

```python
import numpy as np
import pandas as pd
import pytest

from lab.funding_ingest import fetch_funding, ingest as ingest_funding, to_8h_equivalent
from lab.premium_ingest import compute_premium, ingest as ingest_premium
from swingbot.data.series_store import SeriesStore

HOUR_MS = 3_600_000


class FakePerpExchange:
    """Stands in for ccxt.hyperliquid: honours `since`, pages forward."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def fetch_funding_rate_history(self, symbol, since=None, limit=None):
        self.calls.append((symbol, since, limit))
        out = [r for r in self.rows if since is None or r["timestamp"] >= since]
        return out[: (limit or len(out))]


class FakeSpotProvider:
    def __init__(self, df):
        self.df = df

    def get_candles_range(self, symbol, timeframe, start_ms, end_ms):
        return self.df


def _funding_rows(n, start_ms=1_700_000_000_000, rate=0.0001):
    return [{"timestamp": start_ms + i * HOUR_MS, "fundingRate": rate} for i in range(n)]


def test_fetch_funding_pages_forward_until_the_end_timestamp():
    ex = FakePerpExchange(_funding_rows(250))
    start = 1_700_000_000_000
    rows = fetch_funding(ex, "BTC/USDC:USDC", start, start + 249 * HOUR_MS, page_limit=100)
    assert len(rows) == 250
    assert len(ex.calls) >= 3            # paged rather than one giant request
    assert rows[0][0] == start // 1000   # epoch SECONDS in the returned rows
    assert [r[1] for r in rows] == [0.0001] * 250


def test_fetch_funding_stops_at_end_ms():
    ex = FakePerpExchange(_funding_rows(250))
    start = 1_700_000_000_000
    rows = fetch_funding(ex, "BTC/USDC:USDC", start, start + 9 * HOUR_MS, page_limit=100)
    assert len(rows) == 10


def test_fetch_funding_terminates_when_the_venue_stops_advancing():
    ex = FakePerpExchange(_funding_rows(5))   # far fewer rows than requested
    start = 1_700_000_000_000
    rows = fetch_funding(ex, "BTC/USDC:USDC", start, start + 10_000 * HOUR_MS)
    assert len(rows) == 5


def test_to_8h_equivalent_sums_a_trailing_eight_hour_window():
    rows = [(i * 3600, 0.0001) for i in range(10)]
    out = to_8h_equivalent(rows)
    assert len(out) == 3                       # first full window is at index 7
    assert out[0][0] == 7 * 3600
    assert out[0][1] == pytest.approx(0.0008)


def test_ingest_funding_writes_8h_equivalents_under_the_store_symbol(tmp_path):
    store = SeriesStore(str(tmp_path / "s.db"))
    ex = FakePerpExchange(_funding_rows(24))
    start = 1_700_000_000_000
    written = ingest_funding(store, ex, since_ms=start, end_ms=start + 23 * HOUR_MS)
    assert written == 17                       # 24 hourly readings -> 17 full windows
    df = store.get_df("funding_8h", "BTC/USD")
    assert len(df) == 17
    assert df["value"].iloc[0] == pytest.approx(0.0008)


def _ohlc(ts, close):
    return pd.DataFrame({"ts": ts, "open": close, "high": close,
                         "low": close, "close": close, "volume": np.ones(len(close))})


def test_compute_premium_is_the_relative_spread_on_shared_timestamps():
    ts = pd.date_range("2024-01-01", periods=3, freq="4h", tz="UTC")
    local = _ohlc(ts, np.array([101.0, 102.0, 103.0]))
    offshore = _ohlc(ts, np.array([100.0, 102.0, 100.0]))
    out = compute_premium(local, offshore)
    assert list(out.columns) == ["ts", "value"]
    assert out["value"].round(6).tolist() == [0.01, 0.0, 0.03]


def test_compute_premium_only_keeps_timestamps_present_in_both_venues():
    local = _ohlc(pd.date_range("2024-01-01", periods=3, freq="4h", tz="UTC"),
                  np.array([101.0, 102.0, 103.0]))
    offshore = _ohlc(pd.date_range("2024-01-01 04:00", periods=3, freq="4h", tz="UTC"),
                     np.array([100.0, 100.0, 100.0]))
    out = compute_premium(local, offshore)
    assert len(out) == 2


def test_ingest_premium_resamples_local_15m_and_stores_the_series(tmp_path):
    store = SeriesStore(str(tmp_path / "s.db"))
    ts15 = pd.date_range("2024-01-01", periods=32, freq="15min", tz="UTC")
    local15 = _ohlc(ts15, np.full(32, 101.0))
    ts4h = pd.date_range("2024-01-01", periods=2, freq="4h", tz="UTC")
    offshore = _ohlc(ts4h, np.full(2, 100.0))
    written = ingest_premium(store, local15, FakeSpotProvider(offshore),
                             start_ms=0, end_ms=10**13)
    assert written == 2
    df = store.get_df("cb_premium", "BTC/USD")
    assert df["value"].round(6).tolist() == [0.01, 0.01]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_lab_ingest.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'lab.funding_ingest'`

- [ ] **Step 3: Write `lab/funding_ingest.py`**

```python
"""Ingest perpetual-swap funding rates into SeriesStore.

Venue: Hyperliquid via ccxt. It is the only keyless source verified to serve deep
funding history from this host - Binance returns HTTP 451 (geo-block), binance.us
is spot-only and has no perpetuals at all, Bybit's edge returns 403, and OKX caps
public funding history at ~97 days. Hyperliquid honours `since` and pages FORWARD
from 2023-05-12, at HOURLY granularity.

Spec 6b states thresholds for 8-hour funding, so hourly readings are converted to
a trailing 8-hour sum before storage; stored values are directly comparable to the
+0.05% / -0.01% thresholds.

Run (writes to the research data dir, never to ~/.swingbot):
    SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.funding_ingest
"""
from __future__ import annotations

import os

HOUR_MS = 3_600_000
WINDOW_HOURS = 8


def fetch_funding(exchange, symbol: str, since_ms: int, end_ms: int,
                  page_limit: int = 500) -> list[tuple[int, float]]:
    """Page forward through funding history, returning (epoch_seconds, rate).

    Stops when the venue returns nothing, stops advancing, or passes end_ms - so
    a venue that silently caps its history terminates instead of looping.
    """
    out: dict[int, float] = {}
    since = since_ms
    while since <= end_ms:
        page = exchange.fetch_funding_rate_history(symbol, since=since, limit=page_limit)
        if not page:
            break
        for row in page:
            ts_ms = int(row["timestamp"])
            if ts_ms > end_ms:
                break
            out[ts_ms // 1000] = float(row["fundingRate"])
        last_ms = int(page[-1]["timestamp"])
        if last_ms < since:
            break                      # no forward progress
        if len(page) < page_limit:
            break                      # partial page: history is exhausted
        since = last_ms + HOUR_MS
    return sorted(out.items())


def to_8h_equivalent(rows: list[tuple[int, float]]) -> list[tuple[int, float]]:
    """Trailing 8-hour sum of hourly rates, stamped at the window's last hour.

    Rows before the first complete window are dropped rather than partially
    summed - a partial window would understate funding and bias the signal long.
    """
    out = []
    for i in range(WINDOW_HOURS - 1, len(rows)):
        window = rows[i - WINDOW_HOURS + 1: i + 1]
        out.append((rows[i][0], sum(v for _, v in window)))
    return out


def ingest(store, exchange, *, symbol: str = "BTC/USDC:USDC",
           store_symbol: str = "BTC/USD", since_ms: int, end_ms: int) -> int:
    """Fetch, convert to 8h-equivalent, and upsert under series name funding_8h."""
    hourly = fetch_funding(exchange, symbol, since_ms, end_ms)
    return store.upsert("funding_8h", store_symbol, to_8h_equivalent(hourly))


def main() -> None:
    import ccxt
    import pandas as pd

    from swingbot.data.series_store import SeriesStore

    data_dir = os.environ.get("SWINGBOT_DATA_DIR", "/tmp/swingbot-bt")
    store = SeriesStore(os.path.join(data_dir, "series.db"))
    exchange = ccxt.hyperliquid({"enableRateLimit": True})
    since = int(pd.Timestamp("2023-05-01", tz="UTC").timestamp() * 1000)
    end = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
    written = ingest(store, exchange, since_ms=since, end_ms=end)
    cov = store.coverage("funding_8h", "BTC/USD")
    print(f"[funding] wrote {written} rows; coverage {cov}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write `lab/premium_ingest.py`**

```python
"""Ingest the Coinbase premium series into SeriesStore.

This is the keyless stand-in for spec 6c's on-chain exchange net flow, which has
no free data source (Glassnode / CryptoQuant expose exchange flows on paid tiers
only). The premium - Coinbase BTC/USD against offshore BTC/USDT - is a
well-documented proxy for the same thing: US spot demand pressure. A positive
premium means US buyers are lifting offers (accumulation); a negative premium
means US supply is hitting bids (distribution).

Local leg: the Coinbase 15m bars already in the research archive, resampled to 4h.
Offshore leg: OKX BTC/USDT spot 4h, which paginates keyless back to 2022.

Run:
    SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.premium_ingest
"""
from __future__ import annotations

import os

import pandas as pd

from lab.research_data import resample


def compute_premium(local_4h: pd.DataFrame, offshore_4h: pd.DataFrame) -> pd.DataFrame:
    """Relative close spread on timestamps present at BOTH venues.

    (local - offshore) / offshore. Inner-joining on ts means a venue outage drops
    the bar entirely rather than producing a fabricated spread.
    """
    merged = local_4h[["ts", "close"]].merge(
        offshore_4h[["ts", "close"]], on="ts", suffixes=("_local", "_offshore"))
    merged["value"] = (merged["close_local"] - merged["close_offshore"]) / \
        merged["close_offshore"]
    return merged[["ts", "value"]].sort_values("ts").reset_index(drop=True)


def ingest(store, local_15m: pd.DataFrame, offshore_provider, *,
           store_symbol: str = "BTC/USD", offshore_symbol: str = "BTC/USDT",
           start_ms: int, end_ms: int) -> int:
    """Resample the local leg to 4h, fetch the offshore leg, store the spread."""
    local_4h = resample(local_15m, "4h")
    offshore_4h = offshore_provider.get_candles_range(
        offshore_symbol, "4h", start_ms, end_ms)
    series = compute_premium(local_4h, offshore_4h)
    rows = [(int(ts.timestamp()), float(v))
            for ts, v in zip(series["ts"], series["value"])]
    return store.upsert("cb_premium", store_symbol, rows)


def main() -> None:
    from lab.research_data import load
    from swingbot.data.ccxt_provider import CcxtProvider
    from swingbot.data.series_store import SeriesStore

    data_dir = os.environ.get("SWINGBOT_DATA_DIR", "/tmp/swingbot-bt")
    store = SeriesStore(os.path.join(data_dir, "series.db"))
    local_15m = load("BTC/USD", "15m")
    # OKX quotes USDT natively, so no quote remapping is wanted here.
    provider = CcxtProvider(exchange_id="okx", quote_map={})
    start = int(pd.Timestamp("2022-01-01", tz="UTC").timestamp() * 1000)
    end = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
    written = ingest(store, local_15m, provider, start_ms=start, end_ms=end)
    cov = store.coverage("cb_premium", "BTC/USD")
    print(f"[premium] wrote {written} rows; coverage {cov}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_lab_ingest.py -q`
Expected: 8 passed

- [ ] **Step 6: Commit**

```bash
git add lab/funding_ingest.py lab/premium_ingest.py tests/test_lab_ingest.py
git commit -m "feat(lab): keyless funding and Coinbase-premium ingest"
git push origin core-engine
```

---

## Phase 3 — Signal implementations

### Task 7: `MarketContext.extras` + `FundingMeanReversionSignal`

**Files:**
- Modify: `src/swingbot/types.py:123-129`, `src/swingbot/confluence.py:1-20`
- Create: `src/swingbot/signals/funding.py`
- Test: `tests/test_signal_funding.py`

**Interfaces:**
- Produces: `MarketContext.extras: dict[str, pd.DataFrame]` (default `{}`, each value a `["ts", "value"]` frame); `FundingMeanReversionSignal(weight, high_thresh=0.0005, low_thresh=-0.0001, series_key="funding_8h")` with `name = "funding_mr"`, registered in `confluence._REGISTRY` under `"funding_mr"`.
- The scoring formula must match the `funding_mr` branch added in Task 5.

- [ ] **Step 1: Write the failing test**

Create `tests/test_signal_funding.py`:

```python
import pandas as pd
import pytest

from swingbot.confluence import build_signals
from swingbot.profile import StrategyProfile
from swingbot.signals.funding import FundingMeanReversionSignal
from swingbot.types import MarketContext


def _candles(n=5):
    return pd.DataFrame({
        "ts": pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC"),
        "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0,
    })


def _ctx(values):
    extras = {"funding_8h": pd.DataFrame({
        "ts": pd.date_range("2024-01-01", periods=len(values), freq="4h", tz="UTC"),
        "value": values,
    })}
    return MarketContext(candles=_candles(), extras=extras)


def test_market_context_defaults_to_no_extras():
    ctx = MarketContext(candles=_candles())
    assert ctx.extras == {}


def test_crowded_longs_score_zero():
    sig = FundingMeanReversionSignal(weight=1.0)
    assert sig.evaluate(_ctx([0.002])).score == 0.0


def test_crowded_shorts_score_one():
    sig = FundingMeanReversionSignal(weight=1.0)
    assert sig.evaluate(_ctx([-0.002])).score == 1.0


def test_midpoint_funding_scores_half():
    sig = FundingMeanReversionSignal(weight=1.0, high_thresh=0.001, low_thresh=-0.001)
    assert sig.evaluate(_ctx([0.0])).score == pytest.approx(0.5)


def test_only_the_most_recent_reading_is_used():
    sig = FundingMeanReversionSignal(weight=1.0)
    assert sig.evaluate(_ctx([-0.002, 0.002])).score == 0.0


def test_missing_series_is_neutral_and_flagged():
    sig = FundingMeanReversionSignal(weight=1.0)
    result = sig.evaluate(MarketContext(candles=_candles()))
    assert result.score == 0.5
    assert result.meta["error"] == "no_data"


def test_empty_series_is_neutral_and_flagged():
    sig = FundingMeanReversionSignal(weight=1.0)
    ctx = MarketContext(candles=_candles(),
                        extras={"funding_8h": pd.DataFrame({"ts": [], "value": []})})
    result = sig.evaluate(ctx)
    assert result.score == 0.5
    assert result.meta["error"] == "no_data"


def test_meta_carries_the_funding_reading():
    sig = FundingMeanReversionSignal(weight=1.0)
    assert sig.evaluate(_ctx([0.0003])).meta["funding_8h"] == pytest.approx(0.0003)


def test_inverted_thresholds_are_rejected_at_construction():
    with pytest.raises(ValueError):
        FundingMeanReversionSignal(weight=1.0, high_thresh=-0.001, low_thresh=0.001)


def test_build_signals_constructs_it_from_a_profile():
    profile = StrategyProfile(symbol="BTC/USD", signals={
        "funding_mr": {"weight": 0.4, "high_thresh": 0.0006}})
    built = build_signals(profile)
    assert len(built) == 1
    assert built[0].name == "funding_mr"
    assert built[0].high_thresh == 0.0006
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_signal_funding.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.signals.funding'`

- [ ] **Step 3: Add `extras` to `MarketContext`**

In `src/swingbot/types.py`, replace the `MarketContext` dataclass with:

```python
@dataclass(frozen=True)
class MarketContext:
    """Everything a signal/regime needs, as of the last closed bar in `candles`."""
    candles: pd.DataFrame                      # primary trading timeframe
    benchmark: pd.DataFrame | None = None      # e.g. BTC/USD, same timeframe
    htf: pd.DataFrame | None = None            # higher timeframe for regime; falls back to candles
    # Non-price series keyed by name (e.g. "funding_8h", "cb_premium"), each a
    # ["ts", "value"] frame sorted oldest-first and truncated to readings at or
    # before the last closed bar. Empty by default so existing call sites and
    # signals are unaffected.
    extras: dict = field(default_factory=dict)
```

- [ ] **Step 4: Write the signal**

Create `src/swingbot/signals/funding.py`:

```python
from __future__ import annotations

from swingbot.types import MarketContext, SignalResult


class FundingMeanReversionSignal:
    """Perpetual funding as a long-entry filter (spec 6b).

    Sustained positive funding means longs are paying shorts: the perp is crowded
    long and price often snaps back, so this is a bad moment to add another long.
    Negative funding means shorts are paying: crowded short, and squeezes resolve
    upward. The bot is long-only, so the signal expresses the bearish case as a
    score near 0 rather than as a short.

    score = clamp((high_thresh - funding) / (high_thresh - low_thresh), 0, 1)

    Defaults follow the spec: 8h funding at or above +0.05% scores 0, at or below
    -0.01% scores 1. A missing reading scores a neutral 0.5 - the funding feed is
    third-party, and an outage must not silently veto every entry.
    """

    name = "funding_mr"

    def __init__(self, weight: float, high_thresh: float = 0.0005,
                 low_thresh: float = -0.0001, series_key: str = "funding_8h"):
        if high_thresh <= low_thresh:
            raise ValueError("high_thresh must be greater than low_thresh")
        self.weight = weight
        self.high_thresh = high_thresh
        self.low_thresh = low_thresh
        self.series_key = series_key

    def evaluate(self, ctx: MarketContext) -> SignalResult:
        series = (ctx.extras or {}).get(self.series_key)
        if series is None or len(series) == 0:
            return SignalResult(self.name, 0.5,
                                {self.series_key: None, "error": "no_data"})
        funding = float(series["value"].iloc[-1])
        if funding != funding:  # NaN
            return SignalResult(self.name, 0.5,
                                {self.series_key: None, "error": "no_data"})
        span = self.high_thresh - self.low_thresh
        score = max(0.0, min(1.0, (self.high_thresh - funding) / span))
        return SignalResult(self.name, score, {self.series_key: funding})
```

- [ ] **Step 5: Register it**

In `src/swingbot/confluence.py`, add the import and registry entry:

```python
from swingbot.signals.funding import FundingMeanReversionSignal
```
```python
    "funding_mr": FundingMeanReversionSignal,
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_signal_funding.py -q`
Expected: 10 passed

- [ ] **Step 7: Run the gate and rebuild the container**

```bash
.venv/bin/python -m pytest -q && .venv/bin/ruff check src/
docker compose build swingbot && docker compose up -d swingbot
```
Expected: 583 passed, 5 skipped; ruff clean; container healthy. `MarketContext.extras` defaults to `{}`, so no existing test or call site changes behaviour.

- [ ] **Step 8: Commit**

```bash
git add src/swingbot/types.py src/swingbot/confluence.py src/swingbot/signals/funding.py tests/test_signal_funding.py
git commit -m "feat(signals): MarketContext extras + funding mean-reversion signal"
git push origin core-engine
```

---

### Task 8: `PremiumFlowSignal`

**Files:**
- Create: `src/swingbot/signals/premium_flow.py`
- Modify: `src/swingbot/confluence.py:1-22`
- Test: `tests/test_signal_premium_flow.py`

**Interfaces:**
- Consumes: `MarketContext.extras` (Task 7).
- Produces: `PremiumFlowSignal(weight, lookback=180, band=2.0, series_key="cb_premium")` with `name = "premium_flow"`, registered in `confluence._REGISTRY` under `"premium_flow"`.
- The scoring formula must match the `premium_flow` branch added in Task 5, including pandas' default sample standard deviation (`ddof=1`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_signal_premium_flow.py`:

```python
import numpy as np
import pandas as pd
import pytest

from swingbot.confluence import build_signals
from swingbot.profile import StrategyProfile
from swingbot.signals.premium_flow import PremiumFlowSignal
from swingbot.types import MarketContext


def _candles(n=5):
    return pd.DataFrame({
        "ts": pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC"),
        "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0,
    })


def _ctx(values):
    return MarketContext(candles=_candles(), extras={"cb_premium": pd.DataFrame({
        "ts": pd.date_range("2024-01-01", periods=len(values), freq="4h", tz="UTC"),
        "value": values,
    })})


def test_premium_far_above_its_own_mean_scores_one():
    values = list(np.zeros(29)) + [10.0]
    assert PremiumFlowSignal(weight=1.0, lookback=30).evaluate(_ctx(values)).score == 1.0


def test_premium_far_below_its_own_mean_scores_zero():
    values = list(np.zeros(29)) + [-10.0]
    assert PremiumFlowSignal(weight=1.0, lookback=30).evaluate(_ctx(values)).score == 0.0


def test_premium_at_its_own_mean_scores_half():
    values = [0.001, -0.001] * 15
    sig = PremiumFlowSignal(weight=1.0, lookback=30)
    assert sig.evaluate(_ctx(values + [0.0])).score == pytest.approx(0.5, abs=0.05)


def test_score_uses_only_the_trailing_lookback_window():
    # a huge old premium outside the window must not move today's z-score
    values = [50.0] + list(np.zeros(29)) + [0.0]
    sig = PremiumFlowSignal(weight=1.0, lookback=30)
    assert sig.evaluate(_ctx(values)).score == pytest.approx(0.5, abs=0.05)


def test_short_history_is_neutral_and_flagged():
    result = PremiumFlowSignal(weight=1.0, lookback=30).evaluate(_ctx([0.001] * 5))
    assert result.score == 0.5
    assert result.meta["error"] == "insufficient_history"


def test_a_flat_series_is_neutral_rather_than_dividing_by_zero():
    result = PremiumFlowSignal(weight=1.0, lookback=30).evaluate(_ctx([0.001] * 40))
    assert result.score == 0.5
    assert result.meta["error"] == "zero_variance"


def test_missing_series_is_neutral_and_flagged():
    result = PremiumFlowSignal(weight=1.0).evaluate(MarketContext(candles=_candles()))
    assert result.score == 0.5
    assert result.meta["error"] == "no_data"


def test_meta_carries_the_premium_and_its_z_score():
    values = list(np.zeros(29)) + [1.0]
    meta = PremiumFlowSignal(weight=1.0, lookback=30).evaluate(_ctx(values)).meta
    assert meta["cb_premium"] == 1.0
    assert meta["z"] > 2.0


def test_nonpositive_band_is_rejected_at_construction():
    with pytest.raises(ValueError):
        PremiumFlowSignal(weight=1.0, band=0.0)


def test_build_signals_constructs_it_from_a_profile():
    profile = StrategyProfile(symbol="BTC/USD", signals={
        "premium_flow": {"weight": 0.3, "lookback": 90, "band": 1.5}})
    built = build_signals(profile)
    assert built[0].name == "premium_flow"
    assert built[0].lookback == 90
    assert built[0].band == 1.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_signal_premium_flow.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.signals.premium_flow'`

- [ ] **Step 3: Write the signal**

Create `src/swingbot/signals/premium_flow.py`:

```python
from __future__ import annotations

from swingbot.types import MarketContext, SignalResult


class PremiumFlowSignal:
    """Exchange-flow pressure via the Coinbase premium (spec 6c substitute).

    Spec 6c called for on-chain exchange net flow, which has no free data source.
    The Coinbase premium - US spot price against offshore USDT price - proxies the
    same pressure: a premium means US demand is lifting offers (accumulation, the
    on-chain "outflow" case), a discount means US supply is hitting bids
    (distribution, the "inflow" case).

    The raw premium drifts with venue basis, so the level is meaningless on its
    own; what matters is where it sits relative to its own recent range. The score
    is therefore the z-score over `lookback` bars mapped through +/- `band`
    standard deviations onto 0..1.

    Insufficient history, a flat series, or a missing feed all score a neutral 0.5
    rather than vetoing entries on a data problem.
    """

    name = "premium_flow"

    def __init__(self, weight: float, lookback: int = 180, band: float = 2.0,
                 series_key: str = "cb_premium"):
        if band <= 0:
            raise ValueError("band must be positive")
        if lookback < 2:
            raise ValueError("lookback must be at least 2")
        self.weight = weight
        self.lookback = lookback
        self.band = band
        self.series_key = series_key

    def evaluate(self, ctx: MarketContext) -> SignalResult:
        series = (ctx.extras or {}).get(self.series_key)
        if series is None or len(series) == 0:
            return SignalResult(self.name, 0.5,
                                {self.series_key: None, "error": "no_data"})
        window = series["value"].iloc[-self.lookback:]
        if len(window) < self.lookback:
            return SignalResult(self.name, 0.5,
                                {self.series_key: float(window.iloc[-1]),
                                 "error": "insufficient_history"})
        std = float(window.std())          # ddof=1, matching the lab harness
        latest = float(window.iloc[-1])
        if not (std > 0):
            return SignalResult(self.name, 0.5,
                                {self.series_key: latest, "error": "zero_variance"})
        z = (latest - float(window.mean())) / std
        score = max(0.0, min(1.0, (z + self.band) / (2 * self.band)))
        return SignalResult(self.name, score, {self.series_key: latest, "z": z})
```

- [ ] **Step 4: Register it**

In `src/swingbot/confluence.py`, add the import and registry entry:

```python
from swingbot.signals.premium_flow import PremiumFlowSignal
```
```python
    "premium_flow": PremiumFlowSignal,
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_signal_premium_flow.py -q`
Expected: 10 passed

- [ ] **Step 6: Run the gate and rebuild the container**

```bash
.venv/bin/python -m pytest -q && .venv/bin/ruff check src/
docker compose build swingbot && docker compose up -d swingbot
```
Expected: 593 passed, 5 skipped; ruff clean; container healthy.

- [ ] **Step 7: Commit**

```bash
git add src/swingbot/signals/premium_flow.py src/swingbot/confluence.py tests/test_signal_premium_flow.py
git commit -m "feat(signals): Coinbase-premium exchange-flow signal"
git push origin core-engine
```

---

### Task 9: Lab/production parity test

**Files:**
- Create: `tests/test_lab_signal_parity.py`

**Interfaces:**
- Consumes: `lab.strategy_backtest._signal_scores` (Task 5), `FundingMeanReversionSignal` (Task 7), `PremiumFlowSignal` (Task 8), `swingbot.confluence.ConfluenceEngine`.

The lab harness scores signals with vectorized numpy for speed; the live engine scores them one bar at a time through the `Signal` classes. This test pins the two together bar-for-bar. Without it, a research verdict can be produced by code that does not match what would actually trade. This mirrors the `validate()` guarantee that the 2026-06 harness already provides for the price-based signals.

- [ ] **Step 1: Write the test**

Create `tests/test_lab_signal_parity.py`:

```python
"""The lab's vectorized scoring must equal the live Signal classes, bar for bar.

If this fails, a research verdict no longer describes what the live engine would
do. Fix the formulas rather than loosening the tolerance.
"""
import numpy as np
import pandas as pd
import pytest

from lab.strategy_backtest import _signal_scores
from swingbot.confluence import ConfluenceEngine, build_signals
from swingbot.profile import StrategyProfile
from swingbot.types import MarketContext

N = 400
LOOKBACK = 60


@pytest.fixture
def frames():
    rng = np.random.RandomState(7)
    ts = pd.date_range("2024-01-01", periods=N, freq="4h", tz="UTC")
    close = 100.0 * np.cumprod(1 + rng.randn(N) * 0.01)
    candles = pd.DataFrame({"ts": ts, "open": close, "high": close * 1.01,
                            "low": close * 0.99, "close": close,
                            "volume": np.abs(rng.randn(N)) + 1})
    funding = rng.randn(N) * 0.0004
    premium = rng.randn(N) * 0.001
    return candles, funding, premium


def _per_bar_scores(candles, profile, extras_arrays):
    """Score every bar the way the live engine does: one MarketContext per bar."""
    engine = ConfluenceEngine(build_signals(profile), profile)
    out = []
    for i in range(len(candles)):
        extras = {
            key: pd.DataFrame({"ts": candles["ts"].iloc[: i + 1],
                               "value": arr[: i + 1]})
            for key, arr in extras_arrays.items()
        }
        ctx = MarketContext(candles=candles.iloc[: i + 1], extras=extras)
        out.append(engine.evaluate(ctx).score)
    return np.array(out)


def test_funding_signal_matches_the_vectorized_branch(frames):
    candles, funding, _ = frames
    profile = StrategyProfile(symbol="BTC/USD", signals={
        "funding_mr": {"weight": 1.0, "high_thresh": 0.0005, "low_thresh": -0.0001}})
    fast = _signal_scores(candles, profile, None, extras={"funding_8h": funding})
    slow = _per_bar_scores(candles, profile, {"funding_8h": funding})
    np.testing.assert_allclose(fast, slow, atol=1e-12)


def test_premium_signal_matches_the_vectorized_branch(frames):
    candles, _, premium = frames
    profile = StrategyProfile(symbol="BTC/USD", signals={
        "premium_flow": {"weight": 1.0, "lookback": LOOKBACK, "band": 2.0}})
    fast = _signal_scores(candles, profile, None, extras={"cb_premium": premium})
    slow = _per_bar_scores(candles, profile, {"cb_premium": premium})
    np.testing.assert_allclose(fast, slow, atol=1e-12)


def test_a_blended_profile_matches_bar_for_bar(frames):
    candles, funding, premium = frames
    profile = StrategyProfile(symbol="BTC/USD", signals={
        "ema_trend": {"weight": 0.5, "fast": 8, "slow": 21, "band": 0.01},
        "funding_mr": {"weight": 0.3},
        "premium_flow": {"weight": 0.2, "lookback": LOOKBACK, "band": 2.0},
    })
    extras = {"funding_8h": funding, "cb_premium": premium}
    fast = _signal_scores(candles, profile, None, extras=extras)
    slow = _per_bar_scores(candles, profile, extras)
    # EMA warmup NaNs are handled identically on both paths; compare everything.
    np.testing.assert_allclose(fast, slow, atol=1e-12)
```

- [ ] **Step 2: Run the test**

Run: `.venv/bin/python -m pytest tests/test_lab_signal_parity.py -q`
Expected: 3 passed.

If a comparison fails, the discrepancy is real — reconcile `lab/strategy_backtest.py` with the signal class it mirrors. Most likely causes: pandas `rolling(...).std()` uses `ddof=1` while a hand-rolled version uses `ddof=0`, or the vectorized branch treats a NaN differently from the class's `no_data` path.

- [ ] **Step 3: Commit**

```bash
git add tests/test_lab_signal_parity.py
git commit -m "test: pin lab vectorized scoring to the live signal classes"
git push origin core-engine
```

---

## Phase 4 — Run the research

### Task 10: 4h EMA trend research runner (spec §6a)

**Files:**
- Create: `lab/research_ema_4h.py`
- Test: none (this is an analysis script; its machinery is covered by Tasks 1–3 and 9)

**Interfaces:**
- Consumes: `lab.research_data.{load, resample}`, `lab.walkforward.{walk_forward, promotion_verdict}`.
- Produces: `EMA_GRID`, `base_profile(symbol) -> StrategyProfile`, `main()` printing a per-cost-tier table plus the 60 bps verdict.

- [ ] **Step 1: Refresh the research archive**

`/tmp` is ephemeral. Re-run the backfill (idempotent, ~8 min; skip if `/tmp/swingbot-bt/candles.db` already covers 2022-01-01 → today):

```bash
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m swingbot.backfill_cli \
  --exchange coinbase --symbols "BTC/USD,ETH/USD" --timeframes 15m --start 2022-01-01
```
Expected: `[backfill] BTC/USD 15m: ~156000 bars` and the same for ETH/USD.

- [ ] **Step 2: Write the runner**

Create `lab/research_ema_4h.py`:

```python
"""Walk-forward validation of the 4h EMA trend signal (spec 6a).

Why 4h: the 2026-06-22 study found 15m has no gross edge at all because median
ATR/price (0.29% BTC) is below the 0.6% round trip. Resampling to 4h raises it to
~1.37%, and 4h EMA was the only configuration with a pulse (PF 1.17 BTC gross).
That study was a single in-sample fit, though - this one selects parameters on
training data only and grades on untouched out-of-sample quarters.

The verdict is graded at 60 bps (Alpaca's real round trip). The 0/10/25 bps
columns are diagnostic: they show HOW cost-fragile the edge is, not whether to
deploy it.

Run:
    SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.research_ema_4h
"""
from __future__ import annotations

from lab.research_data import load, resample
from lab.walkforward import promotion_verdict, walk_forward
from swingbot.profile import StrategyProfile
from swingbot.types import Regime

COSTS = [0.0, 0.0010, 0.0025, 0.0060]
GATE_COST = 0.0060

# 27 combinations. Deliberately coarse: a fine grid over 12 training quarters
# would fit noise, and each extra knob costs out-of-sample reliability.
EMA_GRID = [
    {"ema_trend.fast": f, "ema_trend.slow": s, "entry_threshold": t}
    for f in (8, 13, 21)
    for s in (34, 55, 89)
    for t in (0.50, 0.65, 0.80)
]


def base_profile(symbol: str) -> StrategyProfile:
    return StrategyProfile(
        symbol=symbol,
        timeframe="4h",
        kind="research",
        label="ema-4h",
        signals={"ema_trend": {"weight": 1.0, "fast": 21, "slow": 55, "band": 0.001}},
        entry_threshold=0.65,
        regime_ma_period=200,
        allowed_regimes=(Regime.UPTREND, Regime.NEUTRAL),
        atr_period=14,
        bracket_mode="atr", stop_atr_mult=1.5, take_profit_atr_mult=3.0,
        risk_per_trade=0.0075, max_hold_bars=48,
        daily_loss_limit_pct=0.03, max_consecutive_losses=3, cooldown_minutes=45,
    )


def main() -> None:
    for symbol in ("BTC/USD", "ETH/USD"):
        df = resample(load(symbol, "15m"), "4h")
        print(f"\n=== {symbol} 4h: {len(df)} bars "
              f"{df['ts'].iloc[0]} -> {df['ts'].iloc[-1]} ===")
        for cost in COSTS:
            result = walk_forward(df, base_profile(symbol), EMA_GRID,
                                  round_trip=cost, train_days=365,
                                  test_days=90, step_days=90)
            v = promotion_verdict(result)
            tag = "  <-- GATE" if cost == GATE_COST else ""
            print(f"  {int(cost * 1e4):>3} bps | windows {len(result.windows):>2} "
                  f"| trades {v.n_trades:>4} | net {v.net_return_pct:>7.2f}% "
                  f"| PF {v.profit_factor:>5.2f} "
                  f"| +windows {v.positive_window_frac:>5.0%} "
                  f"| {v.decision}{tag}")
            if cost == GATE_COST:
                print(f"        verdict: {v.reason}")
                print("        chosen params per window: "
                      + ", ".join(str(w.combo) for w in result.windows))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run it and capture the output**

```bash
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.research_ema_4h \
  | tee /tmp/swingbot-bt/ema_4h.txt
```
Expected: a table per symbol with a PROMOTE/REJECT line at 60 bps. Record the numbers verbatim — Task 13 quotes them.

- [ ] **Step 4: Note the Kronos confirmation question**

Spec §6a names Kronos as a confirmation filter on the EMA signal. The 2026-06-22 study already tested exactly this on 4h with GPU-precomputed forecasts and found **EMA+Kronos ≈ EMA-core** (n 369 vs 370 on BTC; +1pt on ETH, inside noise) because the 0.30 confluence term is saturated and rarely flips an entry.

Re-running it costs ~32 min of GPU inference per symbol and needs the container. Only do so if `/tmp/swingbot-bt/k_btc_4h.csv` and `k_eth_4h.csv` still exist from that session:

```bash
ls -la /tmp/swingbot-bt/k_*_4h.csv
```

If they exist, add a Kronos-confluence variant to the grid and re-run. If they do not (expected — `/tmp` is ephemeral), do **not** regenerate: record in Task 13 that the 2026-06-22 finding stands and the Kronos confluence term was not re-tested. Do not report a Kronos result you did not run.

- [ ] **Step 5: Commit**

```bash
git add lab/research_ema_4h.py
git commit -m "feat(lab): 4h EMA trend walk-forward research runner"
git push origin core-engine
```

---

### Task 11: Funding-rate research runner (spec §6b)

**Files:**
- Create: `lab/research_funding.py`

**Interfaces:**
- Consumes: `lab.funding_ingest` (Task 6), `lab.research_data.{load, resample, attach_extra}`, `lab.walkforward`, `SeriesStore`.
- Produces: `FUNDING_GRID`, `overlay_profile(symbol)`, `standalone_profile(symbol)`, `main()`.

Funding history starts 2023-05-12, so this runner uses **270-day training windows** rather than 365 — with 365 the ~38 months of data yield too few out-of-sample quarters to judge consistency. This is stated in the output so the shorter fit is never mistaken for the EMA runner's.

- [ ] **Step 1: Ingest the funding series**

```bash
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.funding_ingest
```
Expected: `[funding] wrote N rows; coverage {'min_ts': ..., 'max_ts': ..., 'count': N}` with the min stamp around 2023-05-12 and roughly 28,000 hourly-stamped 8h-equivalent rows.

If the count is under 5,000, the venue truncated the history — stop and record that funding research is data-blocked in Task 13 rather than running on a stub.

- [ ] **Step 2: Write the runner**

Create `lab/research_funding.py`:

```python
"""Walk-forward validation of funding-rate mean reversion (spec 6b).

Two hypotheses are tested separately, because they fail differently:

  overlay    - funding as a veto on the 4h EMA trend entry. If the edge is real,
               it shows up as the SAME trend trades minus the ones taken into
               crowded longs.
  standalone - funding as the only signal. Long-only, so this is "buy when perps
               are crowded short", with the regime gate still applied.

The bot trades Alpaca SPOT and cannot short, so funding is a timing filter, not a
tradeable instrument (spec 6b note). Data is Hyperliquid hourly funding summed to
8h-equivalents, from 2023-05-12 - shorter than the price history, hence the
270-day training windows.

Run (after lab.funding_ingest):
    SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.research_funding
"""
from __future__ import annotations

import os

from lab.research_data import attach_extra, load, resample
from lab.research_ema_4h import COSTS, GATE_COST, base_profile
from lab.walkforward import apply_combo, promotion_verdict, walk_forward
from swingbot.data.series_store import SeriesStore
from swingbot.profile import StrategyProfile
from swingbot.types import Regime

TRAIN_DAYS = 270

FUNDING_GRID = [
    {"funding_mr.high_thresh": hi, "funding_mr.low_thresh": lo, "entry_threshold": t}
    for hi in (0.0003, 0.0005, 0.0010)
    for lo in (-0.0001, -0.0005)
    for t in (0.50, 0.65)
]


def overlay_profile(symbol: str) -> StrategyProfile:
    """4h EMA trend with funding as a weighted veto term."""
    # apply_combo({}) returns a deep-enough copy that mutating the nested signal
    # dicts here cannot leak back into base_profile's literal.
    profile = apply_combo(base_profile(symbol), {"label": "ema+funding-overlay"})
    profile.signals["ema_trend"]["weight"] = 0.7
    profile.signals["funding_mr"] = {
        "weight": 0.3, "high_thresh": 0.0005, "low_thresh": -0.0001}
    return profile


def standalone_profile(symbol: str) -> StrategyProfile:
    return StrategyProfile(
        symbol=symbol, timeframe="4h", kind="research", label="funding-standalone",
        signals={"funding_mr": {"weight": 1.0,
                                "high_thresh": 0.0005, "low_thresh": -0.0001}},
        entry_threshold=0.65, regime_ma_period=200,
        allowed_regimes=(Regime.UPTREND, Regime.NEUTRAL),
        atr_period=14, bracket_mode="atr", stop_atr_mult=1.5, take_profit_atr_mult=3.0,
        risk_per_trade=0.0075, max_hold_bars=48,
        daily_loss_limit_pct=0.03, max_consecutive_losses=3, cooldown_minutes=45,
    )


def main() -> None:
    data_dir = os.environ.get("SWINGBOT_DATA_DIR", "/tmp/swingbot-bt")
    store = SeriesStore(os.path.join(data_dir, "series.db"))
    funding = store.get_df("funding_8h", "BTC/USD")
    if funding.empty:
        raise SystemExit("no funding_8h series: run `python -m lab.funding_ingest` first")
    print(f"funding_8h: {len(funding)} rows "
          f"{funding['ts'].iloc[0]} -> {funding['ts'].iloc[-1]}")
    print(f"training windows are {TRAIN_DAYS}d (funding history is shorter than price)")

    for symbol in ("BTC/USD", "ETH/USD"):
        # Funding is a BTC-perp reading used as a market-wide crowding gauge, so
        # the same series is attached to both symbols. Stated here because it is
        # a modelling choice, not an oversight.
        df = attach_extra(resample(load(symbol, "15m"), "4h"), "funding_8h", funding)
        df = df[df["ts"] >= funding["ts"].iloc[0]].reset_index(drop=True)
        print(f"\n=== {symbol} 4h: {len(df)} bars from {df['ts'].iloc[0]} ===")
        for label, profile in (("overlay", overlay_profile(symbol)),
                               ("standalone", standalone_profile(symbol))):
            print(f"  -- {label} --")
            for cost in COSTS:
                result = walk_forward(df, profile, FUNDING_GRID, round_trip=cost,
                                      train_days=TRAIN_DAYS, test_days=90, step_days=90)
                v = promotion_verdict(result)
                tag = "  <-- GATE" if cost == GATE_COST else ""
                print(f"    {int(cost * 1e4):>3} bps | windows {len(result.windows):>2} "
                      f"| trades {v.n_trades:>4} | net {v.net_return_pct:>7.2f}% "
                      f"| PF {v.profit_factor:>5.2f} "
                      f"| +windows {v.positive_window_frac:>5.0%} "
                      f"| {v.decision}{tag}")
                if cost == GATE_COST:
                    print(f"          verdict: {v.reason}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run it and capture the output**

```bash
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.research_funding \
  | tee /tmp/swingbot-bt/funding.txt
```

- [ ] **Step 4: Commit**

```bash
git add lab/research_funding.py
git commit -m "feat(lab): funding mean-reversion walk-forward research runner"
git push origin core-engine
```

---

### Task 12: Premium-flow research runner (spec §6c substitute)

**Files:**
- Create: `lab/research_premium.py`

**Interfaces:**
- Consumes: `lab.premium_ingest` (Task 6), `lab.research_data`, `lab.walkforward`, `lab.research_ema_4h.base_profile`.
- Produces: `PREMIUM_GRID`, `overlay_profile(symbol)`, `standalone_profile(symbol)`, `main()`.

- [ ] **Step 1: Ingest the premium series**

```bash
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.premium_ingest
```
Expected: `[premium] wrote N rows` with N around 9,000 (4h bars from 2022-01-01) and coverage starting 2022.

- [ ] **Step 2: Write the runner**

Create `lab/research_premium.py`:

```python
"""Walk-forward validation of the Coinbase-premium flow signal (spec 6c substitute).

Spec 6c specified on-chain exchange net flow with a +/-2 std-dev band. That metric
has no free data source, so the same hypothesis is tested through the Coinbase
premium, which proxies US spot demand pressure. The 2-std-dev band from the spec
carries over directly as the signal's `band` parameter.

As with funding, both an overlay (premium as a position filter on the 4h EMA
trend) and a standalone variant are tested.

Run (after lab.premium_ingest):
    SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.research_premium
"""
from __future__ import annotations

import os

from lab.research_data import attach_extra, load, resample
from lab.research_ema_4h import COSTS, GATE_COST, base_profile
from lab.walkforward import apply_combo, promotion_verdict, walk_forward
from swingbot.data.series_store import SeriesStore
from swingbot.profile import StrategyProfile
from swingbot.types import Regime

# lookback in 4h bars: 30d, 60d, 90d. band follows spec 6c's +/-2 std dev, with
# 1.5 and 2.5 as sensitivity checks.
PREMIUM_GRID = [
    {"premium_flow.lookback": lb, "premium_flow.band": band, "entry_threshold": t}
    for lb in (180, 360, 540)
    for band in (1.5, 2.0, 2.5)
    for t in (0.50, 0.65)
]


def overlay_profile(symbol: str) -> StrategyProfile:
    profile = apply_combo(base_profile(symbol), {"label": "ema+premium-overlay"})
    profile.signals["ema_trend"]["weight"] = 0.7
    profile.signals["premium_flow"] = {"weight": 0.3, "lookback": 180, "band": 2.0}
    return profile


def standalone_profile(symbol: str) -> StrategyProfile:
    return StrategyProfile(
        symbol=symbol, timeframe="4h", kind="research", label="premium-standalone",
        signals={"premium_flow": {"weight": 1.0, "lookback": 180, "band": 2.0}},
        entry_threshold=0.65, regime_ma_period=200,
        allowed_regimes=(Regime.UPTREND, Regime.NEUTRAL),
        atr_period=14, bracket_mode="atr", stop_atr_mult=1.5, take_profit_atr_mult=3.0,
        risk_per_trade=0.0075, max_hold_bars=48,
        daily_loss_limit_pct=0.03, max_consecutive_losses=3, cooldown_minutes=45,
    )


def main() -> None:
    data_dir = os.environ.get("SWINGBOT_DATA_DIR", "/tmp/swingbot-bt")
    store = SeriesStore(os.path.join(data_dir, "series.db"))
    premium = store.get_df("cb_premium", "BTC/USD")
    if premium.empty:
        raise SystemExit("no cb_premium series: run `python -m lab.premium_ingest` first")
    print(f"cb_premium: {len(premium)} rows "
          f"{premium['ts'].iloc[0]} -> {premium['ts'].iloc[-1]}")

    for symbol in ("BTC/USD", "ETH/USD"):
        # The premium is a BTC-venue spread used as a market-wide US-demand gauge,
        # so the same series is attached to both symbols (same choice as funding).
        df = attach_extra(resample(load(symbol, "15m"), "4h"), "cb_premium", premium)
        print(f"\n=== {symbol} 4h: {len(df)} bars from {df['ts'].iloc[0]} ===")
        for label, profile in (("overlay", overlay_profile(symbol)),
                               ("standalone", standalone_profile(symbol))):
            print(f"  -- {label} --")
            for cost in COSTS:
                result = walk_forward(df, profile, PREMIUM_GRID, round_trip=cost,
                                      train_days=365, test_days=90, step_days=90)
                v = promotion_verdict(result)
                tag = "  <-- GATE" if cost == GATE_COST else ""
                print(f"    {int(cost * 1e4):>3} bps | windows {len(result.windows):>2} "
                      f"| trades {v.n_trades:>4} | net {v.net_return_pct:>7.2f}% "
                      f"| PF {v.profit_factor:>5.2f} "
                      f"| +windows {v.positive_window_frac:>5.0%} "
                      f"| {v.decision}{tag}")
                if cost == GATE_COST:
                    print(f"          verdict: {v.reason}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run it and capture the output**

```bash
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.research_premium \
  | tee /tmp/swingbot-bt/premium.txt
```

- [ ] **Step 4: Commit**

```bash
git add lab/research_premium.py
git commit -m "feat(lab): Coinbase-premium walk-forward research runner"
git push origin core-engine
```

---

### Task 13: Findings document and promotion decision

**Files:**
- Create: `docs/SIGNAL_RESEARCH_FINDINGS.md`

This task converts three console outputs into the record that Phase 5 is gated on. **Transcribe the numbers actually produced in Tasks 10–12. Do not estimate, round to a nicer figure, or reuse the 2026-06-22 numbers.** If a runner failed or a series was data-blocked, say so explicitly.

- [ ] **Step 1: Write the findings document**

Create `docs/SIGNAL_RESEARCH_FINDINGS.md` using this structure, filling every `<...>` from the captured output in `/tmp/swingbot-bt/{ema_4h,funding,premium}.txt`:

```markdown
# Signal research findings — walk-forward validation

**Date:** <run date>
**Spec:** `docs/superpowers/specs/2026-07-22-thermostat-rebuild-design.md` §6, §8 items 6–7
**Plan:** `docs/superpowers/plans/2026-07-26-signal-research-walk-forward.md`
**Verdict:** <one line: which signals PROMOTE, which REJECT>

## Method

Rolling walk-forward: parameters are chosen on each training window and traded
through the following untouched quarter. Only out-of-sample trades are graded.
All backtests run through `run_backtest_fast`, which is bit-for-bit identical to
production `run_backtest`, and the vectorized scoring is pinned to the live
`Signal` classes by `tests/test_lab_signal_parity.py`.

**Promotion gate (all four must hold, evaluated at 60 bps):**
- ≥ 30 out-of-sample trades
- net return > 0
- profit factor ≥ 1.10
- ≥ 50% of test windows net positive

60 bps is Alpaca's real round trip (0.25% fee + 0.05% slippage per side). The
0/10/25 bps columns show cost fragility and are **not** pass conditions.

## Data

| series | source | granularity | coverage |
|---|---|---|---|
| BTC/USD, ETH/USD OHLCV | Coinbase via `swingbot.backfill_cli` | 15m → resampled 4h | <first> → <last>, <n> bars |
| `funding_8h` | Hyperliquid `BTC/USDC:USDC` via ccxt | hourly → trailing 8h sum | <first> → <last>, <n> rows |
| `cb_premium` | Coinbase BTC/USD vs OKX BTC/USDT | 4h | <first> → <last>, <n> rows |

Sources rejected during this work, and why: Binance HTTP 451 (geo-block);
binance.us spot-only, no perpetuals so no funding rates; Bybit CloudFront 403;
OKX funding history capped at ~97 days; Glassnode/CryptoQuant exchange net flow
is paid-tier only, which is why spec §6c's on-chain metric was substituted with
the Coinbase premium (approved 2026-07-26).

## 6a — 4h EMA trend

<paste the per-symbol table>

**Verdict: <PROMOTE|REJECT>.** <reason string from the gate>

Kronos confirmation: <either the re-run result, or: "not re-tested this session —
the cached 4h forecasts were lost with /tmp. The 2026-06-22 GPU finding stands:
EMA+Kronos is within noise of EMA-core (n 369 vs 370 on BTC), so the confluence
term is inert.">

## 6b — Funding-rate mean reversion

<paste the overlay and standalone tables>

**Verdict: <PROMOTE|REJECT>.** <reason>

## 6c substitute — Coinbase premium flow

<paste the overlay and standalone tables>

**Verdict: <PROMOTE|REJECT>.** <reason>

## Decision

<Which signals proceed to Phase 5 promotion, and which do not. If none pass,
state that plainly: the live bot stays Kronos-only and Phase 5 is not executed.>

## Reproduce

```bash
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m swingbot.backfill_cli \
  --exchange coinbase --symbols "BTC/USD,ETH/USD" --timeframes 15m --start 2022-01-01
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.funding_ingest
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.premium_ingest
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.research_ema_4h
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.research_funding
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.research_premium
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/SIGNAL_RESEARCH_FINDINGS.md
git commit -m "docs: walk-forward signal research findings and promotion verdicts"
git push origin core-engine
```

---

## Phase 5 — Promotion

> **GATE — read before starting Task 14.**
>
> Execute Phase 5 **only if `docs/SIGNAL_RESEARCH_FINDINGS.md` records at least one
> `PROMOTE` verdict at 60 bps.**
>
> If every verdict is REJECT: do not build the fusion layer or the live series
> poller. Tick Tasks 14–16 as **N/A — no signal passed the gate**, jump to Task 17,
> and record the outcome there. This is a legitimate result, not a failure — the
> 2026-06-22 study reached the same conclusion for the 15m TA set, and shipping an
> unvalidated signal is exactly what the gate exists to prevent.

### Task 14: Regime-aware signal fusion

**Files:**
- Create: `src/swingbot/fusion.py`
- Test: `tests/test_fusion.py`

**Interfaces:**
- Produces: `FUSION_WEIGHTS: dict[Regime, dict[str, float]]`; `fuse_weights(profile_signals: dict, regime: Regime) -> dict[str, float]` returning a signal-name → weight mapping normalized to sum 1.0 over the signals actually present in the profile.

Spec §6 "Signal Fusion" defines the mapping: uptrend → EMA trend primary with on-chain (here premium) as a modifier; downtrend → funding filter primary with EMA for timing; neutral → funding filter only.

- [ ] **Step 1: Write the failing test**

Create `tests/test_fusion.py`:

```python
import pytest

from swingbot.fusion import fuse_weights
from swingbot.types import Regime


def test_uptrend_makes_trend_primary():
    w = fuse_weights({"ema_trend": {}, "premium_flow": {}, "funding_mr": {}},
                     Regime.UPTREND)
    assert w["ema_trend"] > w["premium_flow"]
    assert w["ema_trend"] > w["funding_mr"]


def test_downtrend_makes_funding_primary():
    w = fuse_weights({"ema_trend": {}, "premium_flow": {}, "funding_mr": {}},
                     Regime.DOWNTREND)
    assert w["funding_mr"] > w["ema_trend"]


def test_neutral_leans_on_the_funding_filter():
    w = fuse_weights({"ema_trend": {}, "funding_mr": {}}, Regime.NEUTRAL)
    assert w["funding_mr"] > w["ema_trend"]


def test_weights_always_sum_to_one():
    for regime in Regime:
        w = fuse_weights({"ema_trend": {}, "premium_flow": {}, "funding_mr": {}}, regime)
        assert sum(w.values()) == pytest.approx(1.0)


def test_absent_signals_are_dropped_and_the_rest_renormalize():
    w = fuse_weights({"ema_trend": {}}, Regime.UPTREND)
    assert w == {"ema_trend": 1.0}


def test_an_unfused_signal_keeps_an_equal_share():
    """A signal with no fusion opinion (e.g. kronos_forecast) is not silenced."""
    w = fuse_weights({"ema_trend": {}, "kronos_forecast": {}}, Regime.UPTREND)
    assert w["kronos_forecast"] > 0
    assert sum(w.values()) == pytest.approx(1.0)


def test_a_profile_with_no_signals_returns_nothing():
    assert fuse_weights({}, Regime.UPTREND) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_fusion.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.fusion'`

- [ ] **Step 3: Write the implementation**

Create `src/swingbot/fusion.py`:

```python
from __future__ import annotations

from swingbot.types import Regime

# Spec 6 "Signal Fusion": which signal leads in which regime.
#   uptrend   - trend signal primary, flow as a position-size modifier
#   downtrend - funding filter primary, trend only for timing
#   neutral   - conservative: lean on the funding filter
# Relative shares only; they are renormalized over the signals a profile has.
FUSION_WEIGHTS: dict[Regime, dict[str, float]] = {
    Regime.UPTREND:   {"ema_trend": 0.60, "premium_flow": 0.25, "funding_mr": 0.15},
    Regime.DOWNTREND: {"ema_trend": 0.25, "premium_flow": 0.20, "funding_mr": 0.55},
    Regime.NEUTRAL:   {"ema_trend": 0.20, "premium_flow": 0.25, "funding_mr": 0.55},
}

# Share given to a signal the fusion table has no opinion about (e.g.
# kronos_forecast). Zeroing it would silently disable a configured signal.
_DEFAULT_SHARE = 0.25


def fuse_weights(profile_signals: dict, regime: Regime) -> dict[str, float]:
    """Regime-aware weights over the signals a profile actually configures.

    Returns a name -> weight mapping summing to 1.0. Signals absent from the
    profile are dropped and the remainder renormalized, so a coin trading only
    one signal still gets a full-weight score rather than a scaled-down one.
    """
    if not profile_signals:
        return {}
    table = FUSION_WEIGHTS[regime]
    raw = {name: table.get(name, _DEFAULT_SHARE) for name in profile_signals}
    total = sum(raw.values())
    if total <= 0:
        share = 1.0 / len(raw)
        return {name: share for name in raw}
    return {name: value / total for name, value in raw.items()}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_fusion.py -q`
Expected: 7 passed

- [ ] **Step 5: Run the gate and rebuild the container**

```bash
.venv/bin/python -m pytest -q && .venv/bin/ruff check src/
docker compose build swingbot && docker compose up -d swingbot
```

- [ ] **Step 6: Commit**

```bash
git add src/swingbot/fusion.py tests/test_fusion.py
git commit -m "feat: regime-aware signal fusion weights"
git push origin core-engine
```

---

### Task 15: Live series poller and `extras` wiring

**Files:**
- Modify: `src/swingbot/orchestrator.py:149-156`, `src/swingbot/webmain.py`
- Create: `src/swingbot/data/series_poller.py`
- Test: `tests/test_series_poller.py`

**Interfaces:**
- Consumes: `SeriesStore` (Task 4), `lab.funding_ingest.fetch_funding`/`to_8h_equivalent` — **these move into `src/swingbot/data/series_poller.py` rather than being imported from `lab/`**, because `lab/` is not packaged into the Docker image. Update `lab/funding_ingest.py` to import them from the new module so there is exactly one implementation.
- Produces: `SeriesPoller(store, exchange, series_specs)` with `refresh(now) -> dict[str, int]` and `context_extras(symbol, as_of) -> dict[str, pd.DataFrame]`.
- Orchestrator: `MarketContext(candles=df, benchmark=benchmark, extras=self._extras(now))` where `_extras` returns `{}` when no poller is configured.

- [ ] **Step 1: Write the failing test**

Create `tests/test_series_poller.py`:

```python
import pandas as pd

from swingbot.data.series_poller import SeriesPoller
from swingbot.data.series_store import SeriesStore


class FakePerp:
    def __init__(self, rows):
        self.rows = rows

    def fetch_funding_rate_history(self, symbol, since=None, limit=None):
        out = [r for r in self.rows if since is None or r["timestamp"] >= since]
        return out[: (limit or len(out))]


def _rows(n, start_ms=1_700_000_000_000):
    return [{"timestamp": start_ms + i * 3_600_000, "fundingRate": 0.0001}
            for i in range(n)]


def test_refresh_writes_the_series_into_the_store(tmp_path):
    store = SeriesStore(str(tmp_path / "s.db"))
    poller = SeriesPoller(store, FakePerp(_rows(24)), symbol="BTC/USD")
    written = poller.refresh(pd.Timestamp("2023-11-15", tz="UTC"))
    assert written["funding_8h"] > 0
    assert store.coverage("funding_8h", "BTC/USD")["count"] > 0


def test_refresh_is_idempotent_and_does_not_duplicate_rows(tmp_path):
    store = SeriesStore(str(tmp_path / "s.db"))
    poller = SeriesPoller(store, FakePerp(_rows(24)), symbol="BTC/USD")
    now = pd.Timestamp("2023-11-15", tz="UTC")
    poller.refresh(now)
    before = store.coverage("funding_8h", "BTC/USD")["count"]
    poller.refresh(now)
    assert store.coverage("funding_8h", "BTC/USD")["count"] == before


def test_refresh_never_raises_when_the_venue_is_down(tmp_path):
    class Broken:
        def fetch_funding_rate_history(self, *a, **k):
            raise ConnectionError("venue down")

    poller = SeriesPoller(SeriesStore(str(tmp_path / "s.db")), Broken(), symbol="BTC/USD")
    assert poller.refresh(pd.Timestamp("2023-11-15", tz="UTC")) == {"funding_8h": 0}


def test_context_extras_truncates_at_the_as_of_timestamp(tmp_path):
    store = SeriesStore(str(tmp_path / "s.db"))
    store.upsert("funding_8h", "BTC/USD", [(100, 0.1), (200, 0.2), (300, 0.3)])
    poller = SeriesPoller(store, FakePerp([]), symbol="BTC/USD")
    extras = poller.context_extras(
        "BTC/USD", pd.Timestamp(200, unit="s", tz="UTC"))
    assert extras["funding_8h"]["value"].tolist() == [0.1, 0.2]


def test_context_extras_on_an_empty_store_returns_empty_frames(tmp_path):
    poller = SeriesPoller(SeriesStore(str(tmp_path / "s.db")), FakePerp([]),
                          symbol="BTC/USD")
    extras = poller.context_extras("BTC/USD", pd.Timestamp.now(tz="UTC"))
    assert extras["funding_8h"].empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_series_poller.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.data.series_poller'`

- [ ] **Step 3: Move the funding helpers into `src/` and write the poller**

Create `src/swingbot/data/series_poller.py`. Move `HOUR_MS`, `WINDOW_HOURS`, `fetch_funding` and `to_8h_equivalent` here **verbatim** from `lab/funding_ingest.py` (they are unchanged), then add:

```python
class SeriesPoller:
    """Keeps non-price series fresh for the live decision loop.

    Runs inside the supervisor tick. Every failure path is swallowed: a
    third-party funding feed going down must degrade the signal to its neutral
    0.5 score, never take the trading loop with it.
    """

    def __init__(self, store, exchange, *, symbol: str = "BTC/USD",
                 perp_symbol: str = "BTC/USDC:USDC", lookback_days: int = 30):
        self.store = store
        self.exchange = exchange
        self.symbol = symbol
        self.perp_symbol = perp_symbol
        self.lookback_days = lookback_days

    def refresh(self, now) -> dict[str, int]:
        """Top up the funding series up to `now`. Returns rows written per series."""
        try:
            end_ms = int(now.timestamp() * 1000)
            cov = self.store.coverage("funding_8h", self.symbol)
            if cov["count"]:
                since_ms = cov["max_ts"] * 1000 - WINDOW_HOURS * HOUR_MS
            else:
                since_ms = end_ms - self.lookback_days * 24 * HOUR_MS
            hourly = fetch_funding(self.exchange, self.perp_symbol, since_ms, end_ms)
            written = self.store.upsert("funding_8h", self.symbol,
                                        to_8h_equivalent(hourly))
            return {"funding_8h": written}
        except Exception:
            return {"funding_8h": 0}

    def context_extras(self, symbol: str, as_of) -> dict:
        """Series truncated to readings at or before `as_of` - no lookahead."""
        end_ts = int(as_of.timestamp())
        return {"funding_8h": self.store.get_df("funding_8h", self.symbol,
                                                end_ts=end_ts)}
```

Then edit `lab/funding_ingest.py` to re-export rather than redefine, so the two paths cannot drift:

```python
from swingbot.data.series_poller import HOUR_MS, WINDOW_HOURS, fetch_funding, to_8h_equivalent  # noqa: F401
```
(delete the moved definitions from `lab/funding_ingest.py`; keep `ingest` and `main` there).

- [ ] **Step 4: Wire `extras` into the orchestrator**

In `src/swingbot/orchestrator.py`, add a `series_poller=None` keyword to `__init__` (store as `self.series_poller`), add the helper, and pass extras into the context.

Add to `__init__`'s signature after `portfolio_on_close=None`:
```python
                 series_poller=None):
```
and in the body:
```python
        self.series_poller = series_poller            # optional; None => extras {}
```

Add the helper method:
```python
    def _extras(self, as_of) -> dict:
        """Non-price series for the signals. Never fails the tick."""
        if self.series_poller is None:
            return {}
        try:
            return self.series_poller.context_extras(self.profile.symbol, as_of)
        except Exception:
            return {}
```

Change the context construction at `orchestrator.py:156`:
```python
        ctx = MarketContext(candles=df, benchmark=benchmark,
                            extras=self._extras(df["ts"].iloc[-1]))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_series_poller.py tests/test_lab_ingest.py -q`
Expected: 5 + 9 passed

- [ ] **Step 6: Run the gate and rebuild the container**

```bash
.venv/bin/python -m pytest -q && .venv/bin/ruff check src/
docker compose build swingbot && docker compose up -d swingbot
```
Expected: full suite green; container healthy. The orchestrator's `series_poller` defaults to `None`, so every existing construction site is unaffected.

- [ ] **Step 7: Commit**

```bash
git add src/swingbot/data/series_poller.py src/swingbot/orchestrator.py lab/funding_ingest.py tests/test_series_poller.py
git commit -m "feat: live series poller feeding signal extras into the decision loop"
git push origin core-engine
```

---

### Task 16: Promote the validated signal to a live paper strategy

**Files:**
- Modify: `src/swingbot/kronos_preset.py` (add a sibling preset builder), `src/swingbot/webmain.py` (construct the `SeriesPoller`)
- Test: `tests/test_promoted_preset.py`

**Interfaces:**
- Produces: `swingbot.kronos_preset.promoted_profile(symbol) -> dict` — the exact parameter set that passed the gate, as recorded in `docs/SIGNAL_RESEARCH_FINDINGS.md`.

Fill in the signal names, weights, and parameters from the **most frequently chosen combination across the passing windows** (printed by Task 10's runner). Do not invent values.

- [ ] **Step 1: Write the failing test**

Create `tests/test_promoted_preset.py`:

```python
from swingbot.confluence import build_signals
from swingbot.profile import StrategyProfile
from swingbot.kronos_preset import promoted_profile


def test_promoted_profile_builds_a_valid_strategy_profile():
    profile = StrategyProfile.from_dict(promoted_profile("BTC/USD"))
    assert profile.symbol == "BTC/USD"
    assert profile.timeframe == "4h"
    assert build_signals(profile)          # every signal name resolves in the registry


def test_promoted_profile_is_labelled_as_walk_forward_validated():
    d = promoted_profile("BTC/USD")
    assert d["kind"] == "validated"
    assert "walk-forward" in d["label"].lower()


def test_promoted_profile_keeps_the_real_cost_model():
    profile = StrategyProfile.from_dict(promoted_profile("BTC/USD"))
    assert profile.fee_rate == 0.0025
    assert profile.slippage_rate == 0.0005
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_promoted_preset.py -q`
Expected: FAIL with `ImportError: cannot import name 'promoted_profile'`

- [ ] **Step 3: Add the preset**

Append to `src/swingbot/kronos_preset.py`:

```python
def promoted_profile(symbol: str) -> dict:
    """The signal configuration that passed walk-forward validation at 60 bps.

    Parameters are the modal choice across the passing out-of-sample windows -
    see docs/SIGNAL_RESEARCH_FINDINGS.md for the evidence. Unlike
    kronos_bracket_profile (a frequency demo that is NOT expected to be
    profitable), this one earned its place: it cleared trade count, net return,
    profit factor and per-window consistency on data it was never fitted to.
    """
    return {
        "symbol": symbol,
        "timeframe": "4h",
        "kind": "validated",
        "label": "walk-forward validated",
        "signals": {
            # <-- fill from the findings doc, e.g.:
            # "ema_trend": {"weight": 1.0, "fast": 13, "slow": 55, "band": 0.001},
        },
        "entry_threshold": 0.65,          # <-- modal value from the findings doc
        "regime_ma_period": 200,
        "atr_period": 14,
        "bracket_mode": "atr",
        "stop_atr_mult": 1.5,
        "take_profit_atr_mult": 3.0,
        "risk_per_trade": 0.0075,
        "max_hold_bars": 48,
        "max_concurrent": 1,
    }
```

- [ ] **Step 4: Construct the poller in `webmain`**

**Skip this step entirely if the promoted signal uses neither `funding_mr` nor `premium_flow`** (e.g. a pure 4h EMA promotion needs no external series) — note the skip in the commit message.

Otherwise, in `src/swingbot/webmain.py` add the imports:

```python
from swingbot.data.series_poller import SeriesPoller
from swingbot.data.series_store import SeriesStore
```

and insert after the `runtime_state = RuntimeStateStore(...)` line at `webmain.py:38`:

```python
    # Funding feed for promoted signals. Built defensively: if ccxt or the venue
    # is unavailable the poller is simply absent, signals score their neutral
    # 0.5, and the loop trades on price alone rather than failing to start.
    try:
        import ccxt
        series_poller = SeriesPoller(
            SeriesStore(os.path.join(DATA_DIR, "series.db")),
            ccxt.hyperliquid({"enableRateLimit": True}))
    except Exception as exc:
        print(f"[swingbot-web] series poller disabled ({type(exc).__name__}: {exc})")
        series_poller = None
```

then pass `series_poller=series_poller` into the `PortfolioSupervisor(...)` construction, and have the supervisor forward it to each `Orchestrator` it builds and call `series_poller.refresh(now)` once per tick before the per-strategy loop. Locate the supervisor's orchestrator construction and tick loop with:

```bash
grep -n "Orchestrator(" src/swingbot/supervisor.py
grep -n "def tick_all" src/swingbot/supervisor.py
```

Add a supervisor test alongside the existing supervisor tests asserting that a refresh failure does not abort the tick.

- [ ] **Step 5: Run tests, gate, and rebuild**

```bash
.venv/bin/python -m pytest -q && .venv/bin/ruff check src/
docker compose build swingbot && docker compose up -d swingbot
```

- [ ] **Step 6: Live-verify with read-only calls only**

```bash
curl -s localhost:8000/api/health/ready
curl -s localhost:8000/api/strategies | head -40
curl -s "localhost:8000/api/decisions?limit=20"
```
Expected: ready 200; the promoted strategy appears with `kind: "validated"`; the decision feed shows it evaluating at each bar close.

**Do not issue any `PUT`/`POST`/`DELETE` against the live instance** — a probe `PUT` previously clobbered the stored Alpaca credentials. Arming the strategy is the user's call, not part of this task.

- [ ] **Step 7: Commit**

```bash
git add src/swingbot/kronos_preset.py src/swingbot/webmain.py tests/test_promoted_preset.py
git commit -m "feat: promote walk-forward validated signal to a live paper preset"
git push origin core-engine
```

---

### Task 17: Update the roadmap

**Files:**
- Modify: `docs/ROADMAP_STATUS.md:11` (insert a new LATEST SESSION block above the 2026-07-22 one), `docs/ROADMAP_STATUS.md:170-182` (rewrite NEXT ACTION)

- [ ] **Step 1: Write the session record**

Insert a new `## ▶ LATEST SESSION (<date>) — Signal Research & Walk-Forward Promotion` section directly beneath the `**Last updated:**` line, covering:
- what shipped (harness, ingress, two signal classes, fusion if built);
- the data sources used and the ones ruled out, with the reasons;
- the verdict per signal at 60 bps, quoting the actual numbers;
- whether Phase 5 executed or was skipped by the gate;
- the final gate result (`pytest` counts, ruff, container health).

Update `**Last updated:**` to the run date.

- [ ] **Step 2: Rewrite NEXT ACTION**

Replace the current `## ▶ NEXT ACTION` block (which points at this plan) with whichever applies:

- **If a signal was promoted:** forward-paper-validate it — arm it on one coin, run for N weeks, compare realized fills against the walk-forward expectation.
- **If nothing passed:** the 6-primitive TA set plus funding and premium-flow are exhausted at 4h under real costs. Name the remaining avenues honestly — a lower-fee venue changes the arithmetic more than any parameter does; a genuinely different edge source (order-flow, cross-venue basis, event-driven) is the other direction. Do not queue another parameter sweep over signals already rejected.

- [ ] **Step 3: Commit**

```bash
git add docs/ROADMAP_STATUS.md
git commit -m "docs: roadmap status after signal research walk-forward"
git push origin core-engine
```

---

## Notes for the executing engineer

- **The gate is the point.** The 2026-06-22 study found the 4h EMA edge is breakeven at 25 bps and negative at 60 bps. There is a real chance every verdict is REJECT. That is a successful outcome of this plan, not a failure of it — the harness, the ingress, and the two signal classes are durable regardless, and a REJECT saves the account. Do not relax `promotion_verdict`'s thresholds to manufacture a PROMOTE.
- **Never edit the parameters and re-run until something passes.** Each grid is fixed before the walk-forward runs. Re-running with a widened grid after seeing out-of-sample results turns the test set into a training set and destroys the only guarantee this plan provides.
- **`/tmp` is ephemeral.** After a host reboot, re-run the backfill and both ingest scripts before any research runner.
- **Never write to `~/.swingbot/`** or issue mutating HTTP calls against the running container.
