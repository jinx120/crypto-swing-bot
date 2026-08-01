# Phase 2 — Deep Exit-Geometry Study Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decide whether Phase 1's 36–43% positive-window fraction was small-sample noise or a real
inconsistency, by re-running the identical exit-geometry configuration over ~40 out-of-sample
quarters spanning three market cycles instead of 14 spanning one and a half — and measure, for the
first time, whether the live circuit breakers permit the widened geometry at all.

**Architecture:** A deep Coinbase backfill into its own archive (`lab/deep_backfill.py`), a pure
post-hoc circuit-breaker replay (`lab/breakers.py`), and two runners — the primary deep 4h study
(`lab/research_exit_geometry_deep.py`) and the secondary daily study
(`lab/research_exit_geometry_daily.py`). Both import the grid and cost ladder from the Phase 1 runner
rather than retyping them, so the configuration cannot drift. Pure research code in `lab/`; no `src/`
behaviour changes; the live bot is untouched.

**Tech Stack:** Python 3.12, pandas, ccxt, pytest, the validated `run_backtest_fast` harness,
`.venv/bin/python`.

## Global Constraints

- **The 60 bps promotion gate is not relaxed.** `promotion_verdict()` keeps `min_trades=30`,
  `min_pf=1.10`, `min_positive_window_frac=0.5`. Do not edit that function's thresholds or behaviour.
- **`min_train_trades=20` is not relaxed.** Starvation is instrumented, never tuned away.
- **Grids are fixed before the run.** The exit grid, the cost ladder, and the interpretation bands in
  "Pre-registered interpretation" below are all fixed by this plan. No widening after seeing results.
- **Signal parameters stay frozen** at `lab.research_ema_4h.base_profile`'s declared defaults:
  EMA `fast 21 / slow 55 / band 0.001 / entry_threshold 0.65`, `regime_ma_period 200`,
  `atr_period 14`, `risk_per_trade 0.0075`, `allowed_regimes (UPTREND, NEUTRAL)`.
- **Two archives, two data dirs.** Phase 1's USDT-quoted 2022+ archive stays at
  `/tmp/swingbot-bt`; the USD-quoted deep archive is `/tmp/swingbot-deep`. Every deep command runs
  with `SWINGBOT_DATA_DIR=/tmp/swingbot-deep`. **Never write to `~/.swingbot/`.**
- **Never issue mutating HTTP calls against the live container.** Read-only verification only.
- **Docker rebuild policy:** `docker compose build swingbot && docker compose up -d swingbot` after
  any code change under `crypto-swing-bot/`, unconditionally.
- **Python invocation:** `.venv/bin/python` from the repo root. Tests: `.venv/bin/python -m pytest`.

---

## Deviations from spec §6, and why

The spec (`docs/superpowers/specs/2026-07-31-hold-period-exit-geometry-design.md` §6) sketched Phase 2
as "backfill Coinbase daily, re-run the grid at 1d, grade at 60 bps." Three facts probed live on
2026-08-01 change that shape. All three are recorded here so the deviation is auditable.

**1. The deep archive needs a quote-map override, or it silently stops at 2022.**
`backfill_cli` builds `ArchiveConfig(quote_map=None)`, which `CcxtProvider` turns into the default
`{"USD": "USDT"}` — so `--symbols BTC/USD --exchange coinbase` has always fetched Coinbase's
**BTC/USDT** market. That market returns **0 rows before 2022-01-01**, which is exactly why every
prior archive starts there. The **USD** markets reach **2015-07-20** (BTC) and **2016-05-18** (ETH),
at 1h and 1d alike. The CLI cannot express "no quote mapping", hence `lab/deep_backfill.py` (Task 1).
Because the deep series is USD-quoted and Phase 1's was USDT-quoted, Task 2 checks the two describe
the same market before any comparison is drawn between them.

**2. The primary study stays at 4h; 1d cannot answer Phase 2's question.** Phase 2 exists to decide
whether 36–43% positive windows was noise. At 1d a 365-day training slice holds **365 bars instead
of 2,190** — roughly a sixth of the trades — which drops most combos under the untouchable
`min_train_trades=20` and starves selection by construction. Worse, a 90-day test window would carry
roughly 1.5 trades, making the per-window statistic *noisier* than the 14-window record it is meant
to adjudicate. Since 1h reaches 2015, resampling **1h → 4h** delivers §6's actual prize — ~40 (BTC)
and ~37 (ETH) out-of-sample quarters across three cycles — with Phase 1's exact bar size, signal
definition, ATR scale, hold length and trade density. That comparability is the whole point.

**3. The daily arm is retained, as a different question.** §6's literal daily study is still run
(Task 6), but framed honestly: it asks whether an even longer horizon amortises the fixed 60 bps
further, not whether Phase 1 was consistent. Its hold levels are rescaled to the calendar equivalents
of the 4h grid (48 bars @4h = 8 days; 120 bars @4h = 20 days), and its `train_days` is chosen by a
**pre-registered rule over trade counts only** — never P&L — so no hindsight enters.

**4. The circuit-breaker task needs new code, not another run.** `run_backtest_fast` explicitly does
not apply `cooldown_minutes`, `daily_loss_limit_pct` or `max_consecutive_losses` (its own docstring,
`lab/strategy_backtest.py:9-12`), so Phase 1 measured an edge the live strategy may never realise.
And `swingbot.risk.RiskManager` never clears `kill_switch_active` — `start_day` resets the daily
counters but not the switch, and only an explicit manual resume (`service.py:106`) turns it off. A
trip is therefore **terminal for the record**. With stops widened to 3.5× ATR against an unchanged
3% daily limit and a 3-loss streak limit, this is plausibly the binding constraint on the whole
result. Task 3 builds the replay that measures it.

---

## Pre-registered interpretation

Fixed **before** the run, graded at 60 bps on the deep out-of-sample record. `promotion_verdict` is
the arbiter of promotion; these bands only say what the positive-window fraction *means*:

| deep positive-window fraction | reading |
|---|---|
| ≥ 50% (and PF ≥ 1.10, net > 0, ≥ 30 trades) | promotion gate **PASSES** — Phase 1's shortfall was small-sample noise |
| 43–50% | consistent with Phase 1; the edge is real but genuinely sub-threshold |
| < 43% | the inconsistency is real, not sample noise; the exit-geometry track closes |

A `median_eligible_combos < 3` or `end_of_data` share > 15% still reports **INCONCLUSIVE** via
`phase_gate_verdict`, in either direction — an untestable run must not masquerade as a result.

**The breaker finding is reported alongside, and can override.** If the live breakers halt the
strategy terminally early in the record, no positive-window fraction is deployable, and the findings
must say so plainly rather than leading with the unconstrained number.

---

## File structure

| file | responsibility |
|---|---|
| `lab/deep_backfill.py` (new) | Build the USD-quoted deep archive; owns the quote-map override and the per-symbol inception dates |
| `lab/research_data.py` (modify) | Gains `series_agreement()` — pure two-frame close comparison |
| `lab/breakers.py` (new) | Pure `apply_breakers()` replay of the live kill-switch semantics over a trade record |
| `lab/research_exit_geometry_deep.py` (new) | Primary study: 4h, ~40 windows, Phase 1 config, + breaker report |
| `lab/research_exit_geometry_daily.py` (new) | Secondary study: 1d, calendar-rescaled holds, pre-registered `train_days` selection |
| `lab/research_exit_geometry.py` (unchanged) | Phase 1 runner; both new runners import `EXIT_GRID`/`COSTS`/`BASELINE_COMBO` from it so the configuration cannot drift |
| `tests/test_lab_deep_backfill.py` (new) | Pins the quote-map trap and the inception dates |
| `tests/test_lab_breakers.py` (new) | Kill-switch semantics, including that a trip is terminal |
| `tests/test_lab_walkforward.py` (modify) | `series_agreement` and `select_train_days` unit tests |
| `docs/PHASE2_DEEP_FINDINGS.md` (new) | The deliverable |

---

### Task 1: Build the deep USD-quoted archive

The default `USD → USDT` quote rewrite caps Coinbase history at 2022-01-01. This task adds the one
module that disables it and produces 11 years of 1h and 1d bars.

**Files:**
- Create: `lab/deep_backfill.py`
- Test: `tests/test_lab_deep_backfill.py`

**Interfaces:**
- Consumes: `swingbot.data.backfill.ArchiveConfig` / `Backfiller`,
  `swingbot.data.ccxt_provider.CcxtProvider`, `swingbot.data.store.CandleStore`.
- Produces: `HISTORY_START: dict[str, str]`, `TIMEFRAMES: list[str]`,
  `deep_config(symbol: str) -> ArchiveConfig`, `main() -> None`, and the archive
  `/tmp/swingbot-deep/candles.db` holding `BTC/USD` and `ETH/USD` at `1h` and `1d`.

- [x] **Step 1: Write the failing tests**

Create `tests/test_lab_deep_backfill.py`:

```python
from lab.deep_backfill import HISTORY_START, TIMEFRAMES, deep_config
from swingbot.data.ccxt_provider import CcxtProvider


def test_deep_config_disables_the_usd_to_usdt_rewrite():
    cfg = deep_config("BTC/USD")
    assert cfg.quote_map == {}
    provider = CcxtProvider(exchange_id=cfg.exchange, quote_map=cfg.quote_map)
    assert provider.map_symbol("BTC/USD") == "BTC/USD"


def test_the_default_quote_map_would_have_rewritten_to_usdt():
    # Pins the trap this module exists to avoid. Coinbase's USDT market returns
    # nothing before 2022-01-01, which is why every prior archive starts there.
    assert CcxtProvider(exchange_id="coinbase").map_symbol("BTC/USD") == "BTC/USDT"


def test_deep_config_starts_at_each_market_s_inception():
    assert deep_config("BTC/USD").history_start == "2015-07-20"
    assert deep_config("ETH/USD").history_start == "2016-05-18"


def test_deep_config_fetches_both_research_timeframes():
    assert deep_config("BTC/USD").timeframes == ["1h", "1d"]
    assert deep_config("BTC/USD").exchange == "coinbase"


def test_history_start_covers_exactly_the_two_studied_symbols():
    assert set(HISTORY_START) == {"BTC/USD", "ETH/USD"}
    assert TIMEFRAMES == ["1h", "1d"]
```

- [x] **Step 2: Run tests to verify they fail**

```bash
cd /home/redji/crypto-swing-bot
.venv/bin/python -m pytest tests/test_lab_deep_backfill.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'lab.deep_backfill'`.

- [x] **Step 3: Implement**

Create `lab/deep_backfill.py`:

```python
"""Deep Coinbase backfill for the Phase 2 exit-geometry study.

Why this exists instead of `python -m swingbot.backfill_cli`: the CLI builds an
ArchiveConfig with `quote_map=None`, which CcxtProvider turns into its default
{"USD": "USDT"} - so `--symbols BTC/USD --exchange coinbase` has always fetched
Coinbase's BTC/USDT market. That market returns ZERO rows before 2022-01-01,
which is exactly why every prior archive starts there. The USD-quoted markets
reach 2015-07-20 (BTC) and 2016-05-18 (ETH). The CLI has no flag to express "no
quote mapping", so the deep archive is built here.

Writes to its own data dir so the USD-quoted deep series never mixes with the
USDT-quoted 2022+ archive under the same symbol key.

Run:
    SWINGBOT_DATA_DIR=/tmp/swingbot-deep .venv/bin/python -m lab.deep_backfill
"""
from __future__ import annotations

import os

from swingbot.data.backfill import ArchiveConfig, Backfiller
from swingbot.data.ccxt_provider import CcxtProvider
from swingbot.data.store import CandleStore

DATA_DIR = os.environ.get("SWINGBOT_DATA_DIR", "/tmp/swingbot-deep")

# Coinbase USD-market inception, probed live 2026-08-01. Asking for earlier just
# returns nothing, so these are limits of the venue, not preferences.
HISTORY_START = {"BTC/USD": "2015-07-20", "ETH/USD": "2016-05-18"}

# 1h is the study resolution (resampled to 4h); 1d is the secondary arm. Both are
# fetched in one pass because the second costs ~4k bars on top of ~96k.
TIMEFRAMES = ["1h", "1d"]


def deep_config(symbol: str) -> ArchiveConfig:
    """One symbol's deep-archive config.

    `quote_map={}` is the whole point: it disables the USD->USDT rewrite that
    silently caps Coinbase history at 2022-01-01.
    """
    return ArchiveConfig(
        exchange="coinbase",
        symbols=[symbol],
        timeframes=list(TIMEFRAMES),
        history_start=HISTORY_START[symbol],
        quote_map={},
    )


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    store = CandleStore(os.path.join(DATA_DIR, "candles.db"))
    total = 0
    for symbol in HISTORY_START:
        cfg = deep_config(symbol)
        provider = CcxtProvider(exchange_id=cfg.exchange, quote_map=cfg.quote_map)
        # Backfiller is coverage-driven and idempotent: a re-run fills only the
        # gaps, so an interrupted fetch is safe to resume by re-running.
        total += Backfiller(store, provider=provider).run(cfg)
    print(f"[deep-backfill] {total} new bars into {DATA_DIR}")


if __name__ == "__main__":
    main()
```

- [x] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_lab_deep_backfill.py -v
```

Expected: 5 passed.

- [x] **Step 5: Run the backfill**

Roughly 96k hourly BTC bars and 89k ETH bars at ~300 per request, rate-limited by ccxt. Expect
5–15 minutes. Run it in the background and poll the log rather than blocking.

```bash
cd /home/redji/crypto-swing-bot
SWINGBOT_DATA_DIR=/tmp/swingbot-deep .venv/bin/python -m lab.deep_backfill \
  2>&1 | tee /tmp/deep-backfill.log
```

- [x] **Step 6: Verify depth and bar counts**

```bash
SWINGBOT_DATA_DIR=/tmp/swingbot-deep .venv/bin/python -c "
from lab.research_data import load
for sym in ('BTC/USD', 'ETH/USD'):
    for tf in ('1h', '1d'):
        df = load(sym, tf)
        print(f'{sym:8} {tf:3} {len(df):7d} bars  {df[\"ts\"].iloc[0]} -> {df[\"ts\"].iloc[-1]}')
"
```

Expected, approximately:

```
BTC/USD  1h    96000+ bars  2015-07-20 ... -> 2026-08-01 ...
BTC/USD  1d     4000+ bars  2015-07-20 ...
ETH/USD  1h    89000+ bars  2016-05-18 ...
ETH/USD  1d     3700+ bars  2016-05-18 ...
```

If any series starts at **2022-01-01** the quote map was not disabled — the run fetched the USDT
market. Stop and fix `deep_config` before continuing; every downstream number depends on this.
If a series is short but starts correctly, the fetch was interrupted: re-run Step 5, which resumes.

- [x] **Step 7: Commit**

```bash
git add lab/deep_backfill.py tests/test_lab_deep_backfill.py
git commit -m "feat(lab): deep Coinbase backfill without the USD->USDT quote rewrite"
```

---

### Task 2: Verify the deep archive is the same market as Phase 1's

Phase 1 ran on Coinbase **BTC/USDT**; the deep archive is **BTC/USD**. Before any deep number is
compared to a Phase 1 number, the two series must be shown to describe the same market over their
overlap. This is a validity check, and its threshold is pre-registered here.

**Files:**
- Modify: `lab/research_data.py` (add `series_agreement` after `resample`)
- Test: `tests/test_lab_walkforward.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `series_agreement(a: pd.DataFrame, b: pd.DataFrame) -> dict` with keys
  `n_overlap: int`, `median_rel_diff: float`, `max_rel_diff: float`.

- [x] **Step 1: Write the failing tests**

Append to `tests/test_lab_walkforward.py`:

```python
def _frame(closes, start="2022-01-01"):
    ts = pd.date_range(start, periods=len(closes), freq="4h", tz="UTC")
    return pd.DataFrame({"ts": ts, "close": [float(c) for c in closes]})


def test_series_agreement_of_identical_frames_is_zero():
    frame = _frame([100.0, 101.0, 102.0])
    out = series_agreement(frame, frame)
    assert out["n_overlap"] == 3
    assert out["median_rel_diff"] == 0.0
    assert out["max_rel_diff"] == 0.0


def test_series_agreement_reports_a_relative_offset():
    out = series_agreement(_frame([101.0, 202.0]), _frame([100.0, 200.0]))
    assert out["n_overlap"] == 2
    assert out["median_rel_diff"] == pytest.approx(0.01)


def test_series_agreement_takes_the_max_not_just_the_median():
    out = series_agreement(_frame([100.0, 100.0, 110.0]), _frame([100.0, 100.0, 100.0]))
    assert out["median_rel_diff"] == 0.0
    assert out["max_rel_diff"] == pytest.approx(0.10)


def test_series_agreement_of_disjoint_frames_reports_no_overlap():
    out = series_agreement(_frame([100.0], start="2022-01-01"),
                           _frame([100.0], start="2023-01-01"))
    assert out["n_overlap"] == 0
    assert out["median_rel_diff"] != out["median_rel_diff"]   # NaN
```

Add `import pytest` and `from lab.research_data import series_agreement` to the file's imports if
they are not already present (`pandas as pd` already is).

- [x] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_lab_walkforward.py -k series_agreement -v
```

Expected: FAIL — `ImportError: cannot import name 'series_agreement'`.

- [x] **Step 3: Implement**

Add to `lab/research_data.py`, immediately after `resample`:

```python
def series_agreement(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    """Compare two OHLCV frames on the timestamps they share.

    Phase 1 ran on Coinbase's USDT-quoted market and the deep archive is
    USD-quoted, so before a deep result is set beside a Phase 1 result the two
    series must be shown to describe the same market. Returns the overlap size
    and the median / max absolute relative close difference; NaN differences when
    there is no overlap at all, which is itself the answer.
    """
    merged = a[["ts", "close"]].merge(b[["ts", "close"]], on="ts", suffixes=("_a", "_b"))
    if merged.empty:
        return {"n_overlap": 0, "median_rel_diff": float("nan"),
                "max_rel_diff": float("nan")}
    rel = (merged["close_a"] - merged["close_b"]).abs() / merged["close_b"]
    return {"n_overlap": int(len(merged)),
            "median_rel_diff": float(rel.median()),
            "max_rel_diff": float(rel.max())}
```

- [x] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_lab_walkforward.py -k series_agreement -v
```

Expected: 4 passed.

- [x] **Step 5: Run the real comparison and record the numbers**

Both archives must be read, so this reads two data dirs in one process.

```bash
cd /home/redji/crypto-swing-bot
.venv/bin/python -c "
import os, sqlite3
import pandas as pd
from lab.research_data import resample, series_agreement

def read(data_dir, symbol, tf):
    con = sqlite3.connect(os.path.join(data_dir, 'candles.db'))
    df = pd.read_sql_query('select ts, open, high, low, close, volume from bars '
                           'where symbol=? and timeframe=? order by ts',
                           con, params=(symbol, tf))
    con.close()
    df['ts'] = pd.to_datetime(df['ts'], unit='s', utc=True)
    return df

for sym in ('BTC/USD', 'ETH/USD'):
    old = resample(read('/tmp/swingbot-bt', sym, '15m'), '4h')      # USDT-quoted, 2022+
    new = resample(read('/tmp/swingbot-deep', sym, '1h'), '4h')     # USD-quoted, deep
    out = series_agreement(new, old)
    print(sym, 'overlap', out['n_overlap'],
          'median', round(out['median_rel_diff'] * 10_000, 2), 'bps',
          'max', round(out['max_rel_diff'] * 10_000, 1), 'bps')
"
```

**Pre-registered threshold:** `median_rel_diff` must be **≤ 50 bps (0.005)** and `n_overlap` must be
at least 9,000 bars for each symbol. Coinbase's USD and USDT books normally track within a few bps.
If the median exceeds 50 bps, the deep archive is **not** the same instrument Phase 1 measured —
stop, record the numbers, and raise it before running the study; do not silently compare the two.

Record both symbols' output verbatim; it goes into the findings document in Task 5.

- [x] **Step 6: Commit**

```bash
git add lab/research_data.py tests/test_lab_walkforward.py
git commit -m "feat(lab): series_agreement for cross-venue archive continuity"
```

---

### Task 3: Circuit-breaker replay

`run_backtest_fast` applies no breakers at all (`lab/strategy_backtest.py:9-12`), so every result to
date describes a strategy with its risk controls switched off. `RiskManager` trips a kill switch on
3 consecutive losses or a 3% realized daily loss, and **nothing clears it automatically** — only an
explicit manual resume does. With Phase 1's selected stops as wide as 3.5× ATR against an unchanged
3% daily limit, this is plausibly the binding constraint on the entire result.

**Files:**
- Create: `lab/breakers.py`
- Test: `tests/test_lab_breakers.py`

**Interfaces:**
- Consumes: nothing (pure; operates on any object with `entry_ts`, `exit_ts`, `pnl`).
- Produces: `BreakerReport` (frozen dataclass: `kept: list`, `blocked: list`,
  `halted_at`, `halt_reason: str`, plus `n_kept`, `n_blocked`, `blocked_frac` properties) and
  `apply_breakers(trades, *, starting_equity=1000.0, daily_loss_limit_pct=0.03,
  max_consecutive_losses=3) -> BreakerReport`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_lab_breakers.py`:

```python
import pandas as pd

from lab.breakers import apply_breakers


class _T:
    """Minimal stand-in for swingbot.journal.Trade: the replay reads only these."""

    def __init__(self, entry, pnl, exit=None):
        self.entry_ts = pd.Timestamp(entry, tz="UTC")
        self.exit_ts = pd.Timestamp(exit or entry, tz="UTC")
        self.pnl = float(pnl)


def test_no_trades_produces_an_empty_report():
    report = apply_breakers([])
    assert report.kept == [] and report.blocked == []
    assert report.halted_at is None
    assert report.blocked_frac == 0.0


def test_a_clean_record_keeps_every_trade():
    trades = [_T(f"2022-01-{d:02d}", 5.0) for d in range(1, 6)]
    report = apply_breakers(trades)
    assert report.n_kept == 5 and report.n_blocked == 0
    assert report.halt_reason == ""


def test_three_consecutive_losses_trip_the_kill_switch():
    trades = [_T("2022-01-01", -1.0), _T("2022-01-02", -1.0), _T("2022-01-03", -1.0),
              _T("2022-01-04", 50.0)]
    report = apply_breakers(trades)
    assert report.n_kept == 3 and report.n_blocked == 1
    assert report.halted_at == pd.Timestamp("2022-01-03", tz="UTC")
    assert "consecutive losses" in report.halt_reason


def test_a_win_resets_the_consecutive_loss_counter():
    trades = [_T("2022-01-01", -1.0), _T("2022-01-02", -1.0), _T("2022-01-03", 1.0),
              _T("2022-01-04", -1.0), _T("2022-01-05", -1.0), _T("2022-01-06", 1.0)]
    report = apply_breakers(trades)
    assert report.n_blocked == 0


def test_the_kill_switch_is_terminal_and_never_auto_resets():
    # RiskManager.start_day resets the daily counters but NOT the switch, and only
    # an explicit manual resume clears it - so months of later trades stay blocked.
    trades = [_T("2022-01-01", -1.0), _T("2022-01-02", -1.0), _T("2022-01-03", -1.0)]
    trades += [_T(f"2022-06-{d:02d}", 20.0) for d in range(1, 11)]
    report = apply_breakers(trades)
    assert report.n_kept == 3 and report.n_blocked == 10
    assert report.blocked_frac == 10 / 13


def test_the_daily_loss_limit_trips_within_a_single_day():
    # Two -2% days' worth of loss inside one UTC day against a 3% limit.
    trades = [_T("2022-01-01T00:00", -20.0, exit="2022-01-01T04:00"),
              _T("2022-01-01T08:00", -20.0, exit="2022-01-01T12:00"),
              _T("2022-01-02T00:00", 50.0)]
    report = apply_breakers(trades, starting_equity=1000.0)
    assert report.n_kept == 2 and report.n_blocked == 1
    assert "daily loss" in report.halt_reason


def test_the_same_losses_spread_across_days_do_not_trip_the_daily_limit():
    trades = [_T("2022-01-01", -20.0), _T("2022-01-03", -20.0), _T("2022-01-05", 5.0)]
    report = apply_breakers(trades, starting_equity=1000.0)
    assert report.n_blocked == 0
    assert report.halted_at is None


def test_breakers_can_be_disabled_to_isolate_one_of_them():
    # Raising max_consecutive_losses out of reach isolates the daily-loss breaker.
    trades = [_T("2022-01-01", -1.0), _T("2022-01-02", -1.0), _T("2022-01-03", -1.0),
              _T("2022-01-04", 50.0)]
    report = apply_breakers(trades, max_consecutive_losses=10**9)
    assert report.n_blocked == 0


def test_a_multi_day_hold_rolls_the_day_at_its_exit():
    # A position opened before midnight and closed days later realises its loss on
    # the EXIT day, which is the day the live loop's start_day tick has moved to.
    trades = [_T("2022-01-01T00:00", -20.0, exit="2022-01-01T20:00"),
              _T("2022-01-01T22:00", -20.0, exit="2022-01-09T00:00"),
              _T("2022-01-09T04:00", 5.0)]
    report = apply_breakers(trades, starting_equity=1000.0)
    assert report.n_blocked == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_lab_breakers.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'lab.breakers'`.

- [ ] **Step 3: Implement**

Create `lab/breakers.py`:

```python
"""Post-hoc circuit-breaker replay over a research trade record.

`run_backtest_fast` is a pure entry/exit replay: its own docstring records that
it does NOT apply the live-only breakers. Every result to date therefore
describes a strategy with its risk controls switched off - and Phase 1 selected
stops as wide as 3.5x ATR against an UNCHANGED 3% daily loss limit, so the
breakers may bind far harder at the selected geometry than at baseline.

Faithful to `swingbot.risk.RiskManager`:
- a UTC day change resets realized_pnl_today, consecutive_losses and
  day_start_equity (`start_day`, called every tick),
- `max_consecutive_losses` losing trades in a row trip the kill switch,
- realized loss on the day reaching -daily_loss_limit_pct * day_start_equity
  trips it,
- and NOTHING clears the kill switch automatically. `start_day` resets the
  counters but not the switch; only an explicit manual resume does
  (`service.py:106`). A trip is terminal for the remainder of the record.

Three deliberate approximations, stated because they bound the result:
1. Suppressing an entry cannot create trades. A real strategy freed of a blocked
   position might have entered somewhere this record never saw, so the surviving
   record is a LOWER bound on activity, not an exact re-simulation.
2. A multi-day hold realises its pnl on its exit day, which is the day the live
   loop's own tick has already rolled to; the new day therefore opens at the
   pre-trade equity.
3. `cooldown_minutes` (45) is not modelled: it is shorter than one 4h bar, so it
   can never block the following entry at this resolution.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BreakerReport:
    kept: list
    blocked: list
    halted_at: object | None
    halt_reason: str

    @property
    def n_kept(self) -> int:
        return len(self.kept)

    @property
    def n_blocked(self) -> int:
        return len(self.blocked)

    @property
    def blocked_frac(self) -> float:
        total = self.n_kept + self.n_blocked
        return self.n_blocked / total if total else 0.0


def apply_breakers(trades, *, starting_equity: float = 1000.0,
                   daily_loss_limit_pct: float = 0.03,
                   max_consecutive_losses: int = 3) -> BreakerReport:
    """Replay `trades` in entry order under the live kill-switch semantics.

    Returns which trades would have survived, which the breakers would have
    suppressed, and when (and why) the switch tripped.
    """
    kept: list = []
    blocked: list = []
    equity = starting_equity
    day: str | None = None
    day_start_equity = starting_equity
    realized_today = 0.0
    consecutive = 0
    halted_at, halt_reason = None, ""

    for trade in sorted(trades, key=lambda t: t.entry_ts):
        entry_day = trade.entry_ts.strftime("%Y-%m-%d")
        if entry_day != day:
            day, realized_today, consecutive = entry_day, 0.0, 0
            day_start_equity = equity
        if halted_at is not None:
            blocked.append(trade)
            continue
        kept.append(trade)

        exit_day = trade.exit_ts.strftime("%Y-%m-%d")
        if exit_day != day:
            day, realized_today, consecutive = exit_day, 0.0, 0
            day_start_equity = equity          # pre-trade: the tick rolled first
        equity += trade.pnl
        realized_today += trade.pnl
        consecutive = consecutive + 1 if trade.pnl < 0 else 0

        # Order matches RiskManager._maybe_trip_kill_switch: streak first.
        if consecutive >= max_consecutive_losses:
            halted_at = trade.exit_ts
            halt_reason = f"{consecutive} consecutive losses"
        elif day_start_equity > 0 and \
                realized_today <= -daily_loss_limit_pct * day_start_equity:
            halted_at = trade.exit_ts
            halt_reason = (f"daily loss {realized_today:.2f} <= limit "
                           f"{-daily_loss_limit_pct * day_start_equity:.2f}")

    return BreakerReport(kept=kept, blocked=blocked,
                         halted_at=halted_at, halt_reason=halt_reason)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_lab_breakers.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add lab/breakers.py tests/test_lab_breakers.py
git commit -m "feat(lab): post-hoc circuit-breaker replay of the live kill switch"
```

---

### Task 4: The deep 4h research runner

**Files:**
- Create: `lab/research_exit_geometry_deep.py`
- Test: none. Research runners in this repo carry no unit tests — their correctness rests on the
  tested harness beneath them and on `tests/test_lab_signal_parity.py` pinning lab scoring to the
  live `Signal` classes. Follow that established pattern.

**Interfaces:**
- Consumes: `EXIT_GRID`, `COSTS`, `GATE_COST`, `BASELINE_COMBO` imported from
  `lab.research_exit_geometry` (imported, never retyped, so Phase 1 and Phase 2 cannot drift);
  `base_profile` from `lab.research_ema_4h`; `load`/`resample` from `lab.research_data`;
  `walk_forward`, `promotion_verdict`, `phase_gate_verdict`, `breakeven_cost`, `profit_factor` from
  `lab.walkforward`; `apply_breakers` from `lab.breakers` (Task 3).
- Produces: a runnable module printing, per symbol, the cost-tier table, breakeven, eligibility, exit
  reasons, the 2022+ sub-record, the per-window selected combos, both verdicts, and the breaker report.

- [ ] **Step 1: Write the runner**

Create `lab/research_exit_geometry_deep.py`:

```python
"""Phase 2 - deep exit-geometry study over ~11 years of 4h bars.

Phase 1 (docs/HOLD_PERIOD_FINDINGS.md) showed the exit lever is large: breakeven
moved from 18-44 bps to 70-90, and every configuration cleared the 60 bps we pay.
What it could NOT show is whether the edge is CONSISTENT - 14 quarters spanning
one and a half cycles put the positive-window fraction at 36-43% against the 50%
the promotion gate requires, and 14 windows cannot separate "genuinely
inconsistent" from "small sample".

This runner re-runs the IDENTICAL configuration - same frozen signal parameters,
same 18-combo exit grid, same 13-tier cost ladder, same train 365 / test 90 /
step 90 windows, all imported rather than retyped - over Coinbase history from
2015-07-20 (BTC) and 2016-05-18 (ETH). That is roughly 40 and 37 out-of-sample
quarters across three market cycles.

Resolution stays 4h (resampled from the 1h deep backfill) rather than moving to
1d as spec section 6 sketched: at 1d a 365-day training slice holds 365 bars
instead of 2,190, roughly a sixth of the trades, which drops most combos under
the untouchable min_train_trades=20 and starves selection by construction. The
daily arm is a separate question, run by lab/research_exit_geometry_daily.py.

The breaker report is new and may matter more than the headline. Every prior
result ran with the live risk controls switched off; see lab/breakers.py.

Run:
    SWINGBOT_DATA_DIR=/tmp/swingbot-deep .venv/bin/python -m lab.research_exit_geometry_deep
"""
from __future__ import annotations

import pandas as pd

from lab.breakers import apply_breakers
from lab.research_data import load, resample
from lab.research_ema_4h import base_profile
from lab.research_exit_geometry import BASELINE_COMBO, COSTS, EXIT_GRID, GATE_COST
from lab.walkforward import (breakeven_cost, phase_gate_verdict, profit_factor,
                             promotion_verdict, walk_forward)

# The window at which Phase 1's archive begins. Restricting the deep record to it
# reproduces Phase 1's sample, which is how we tell "more history changed the
# answer" apart from "a different venue changed the answer".
PHASE1_START = pd.Timestamp("2022-01-01", tz="UTC")

# Live strategy breaker settings, unchanged from base_profile.
DAILY_LOSS_LIMIT_PCT = 0.03
MAX_CONSECUTIVE_LOSSES = 3


def _breaker_line(label: str, report, total_trades: int) -> str:
    when = report.halted_at.isoformat() if report.halted_at is not None else "never"
    return (f"  breakers[{label}]: kept {report.n_kept}/{total_trades} "
            f"({report.blocked_frac:.0%} blocked) | first halt {when} "
            f"| {report.halt_reason or 'no trip'} "
            f"| PF kept {profit_factor(report.kept):.2f}")


def main() -> None:
    for symbol in ("BTC/USD", "ETH/USD"):
        df = resample(load(symbol, "1h"), "4h")
        print(f"\n=== ema-4h {symbol} 4h deep: {len(df)} bars "
              f"{df['ts'].iloc[0]} -> {df['ts'].iloc[-1]} ===", flush=True)

        pf_by_cost: dict[float, float] = {}
        graded = None
        for cost in COSTS:
            result = walk_forward(df, base_profile(symbol), EXIT_GRID, round_trip=cost,
                                  train_days=365, test_days=90, step_days=90)
            verdict = promotion_verdict(result)
            pf_by_cost[cost] = verdict.profit_factor
            if cost == GATE_COST:
                graded = result
            marker = "  <-- GATE" if cost == GATE_COST else ""
            print(f"  {cost * 10_000:5.0f} bps | windows {len(result.windows):3d} "
                  f"| trades {verdict.n_trades:5d} | net {verdict.net_return_pct:7.2f}% "
                  f"| PF {verdict.profit_factor:5.2f} "
                  f"| +windows {verdict.positive_window_frac:4.0%} "
                  f"| {verdict.decision}{marker}", flush=True)

        breakeven = breakeven_cost(pf_by_cost)
        gate = phase_gate_verdict(graded, breakeven)
        promotion = promotion_verdict(graded)
        be_txt = f"{breakeven * 10_000:.0f} bps" if breakeven is not None else "none"
        n_baseline = sum(1 for w in graded.windows if w.combo == BASELINE_COMBO)

        modern = [w for w in graded.windows if w.window.test_start >= PHASE1_START]
        modern_frac = (sum(1 for w in modern if w.net_pnl > 0) / len(modern)
                       if modern else 0.0)

        print(f"  breakeven: {be_txt}")
        print(f"  median eligible combos/window: {graded.median_eligible_combos:.1f} "
              f"(of {len(EXIT_GRID)})")
        print(f"  exit reasons @ gate: {graded.exit_reason_counts()}")
        print(f"  end_of_data share: {graded.end_of_data_frac:.1%}")
        print(f"  baseline combo selected in {n_baseline}/{len(graded.windows)} windows")
        print(f"  positive windows, full record: {promotion.positive_window_frac:.0%} "
              f"over {len(graded.windows)} windows")
        print(f"  positive windows, 2022+ only: {modern_frac:.0%} over {len(modern)} "
              f"windows (Phase 1 measured 43% over 14)")
        print(f"  selected combos: " + ", ".join(str(w.combo) for w in graded.windows))

        total = len(graded.oos_trades)
        live = apply_breakers(graded.oos_trades,
                              daily_loss_limit_pct=DAILY_LOSS_LIMIT_PCT,
                              max_consecutive_losses=MAX_CONSECUTIVE_LOSSES)
        daily_only = apply_breakers(graded.oos_trades,
                                    daily_loss_limit_pct=DAILY_LOSS_LIMIT_PCT,
                                    max_consecutive_losses=10 ** 9)
        print(_breaker_line("live 3%/3-streak", live, total))
        print(_breaker_line("daily-loss only", daily_only, total))

        print(f"  PHASE GATE: {gate.decision} - {gate.reason}")
        print(f"  PROMOTION GATE: {promotion.decision} - {promotion.reason}", flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the configuration is byte-identical to Phase 1's**

```bash
cd /home/redji/crypto-swing-bot
SWINGBOT_DATA_DIR=/tmp/swingbot-deep .venv/bin/python -c "
from lab.research_exit_geometry import EXIT_GRID as G1, COSTS as C1
from lab.research_exit_geometry_deep import EXIT_GRID as G2, COSTS as C2, PHASE1_START
print('grid identical:', G1 is G2, len(G2))
print('costs identical:', C1 is C2, len(C2))
print('phase1 start:', PHASE1_START)
"
```

Expected: `grid identical: True 18`, `costs identical: True 13`. Both must be `True` — they are
imported, not copied, precisely so nobody can edit one and not the other.

- [ ] **Step 3: Smoke-test one symbol on a short slice**

Confirm the wiring end to end before committing to the long run.

```bash
SWINGBOT_DATA_DIR=/tmp/swingbot-deep timeout 900 .venv/bin/python -c "
from lab.breakers import apply_breakers
from lab.research_data import load, resample
from lab.research_ema_4h import base_profile
from lab.research_exit_geometry import EXIT_GRID
from lab.walkforward import walk_forward, promotion_verdict
df = resample(load('BTC/USD', '1h'), '4h')
df = df[df['ts'] < '2018-01-01'].reset_index(drop=True)
r = walk_forward(df, base_profile('BTC/USD'), EXIT_GRID, round_trip=0.0060)
v = promotion_verdict(r)
print('bars', len(df), 'windows', len(r.windows), 'trades', v.n_trades,
      'PF', round(v.profit_factor, 3))
print('median eligible', r.median_eligible_combos, 'exits', r.exit_reason_counts())
b = apply_breakers(r.oos_trades)
print('breakers kept', b.n_kept, 'of', len(r.oos_trades), 'halt', b.halt_reason)
"
```

Expected: roughly 5,000+ bars, a handful of windows, a non-zero trade count, a populated exit-reason
dict, and a breaker line. If `median eligible` is 0 the grid is being filtered out entirely — stop
and investigate before running the full study.

- [ ] **Step 4: Lint**

```bash
.venv/bin/python -m ruff check lab/research_exit_geometry_deep.py lab/breakers.py \
  lab/deep_backfill.py lab/research_data.py
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add lab/research_exit_geometry_deep.py
git commit -m "feat(lab): deep 4h exit-geometry runner with breaker interaction"
```

---

### Task 5: Run the deep study and write the findings

**Files:**
- Create: `docs/PHASE2_DEEP_FINDINGS.md`

**Interfaces:**
- Consumes: `lab/research_exit_geometry_deep.py` (Task 4), the Task 2 continuity numbers.
- Produces: the findings document and an explicit verdict against the pre-registered interpretation
  bands at the top of this plan.

- [ ] **Step 1: Run the full deep study**

Roughly 2 symbols × 13 cost tiers × 18 combos × ~40 windows. Phase 1's comparable load took about
14 minutes; expect 20–40 here. Run it in the background and poll the log rather than blocking.

```bash
cd /home/redji/crypto-swing-bot
SWINGBOT_DATA_DIR=/tmp/swingbot-deep .venv/bin/python -m lab.research_exit_geometry_deep \
  2>&1 | tee /tmp/phase2-deep-run.log
```

- [ ] **Step 2: Write the findings document**

Create `docs/PHASE2_DEEP_FINDINGS.md` following the structure of `docs/HOLD_PERIOD_FINDINGS.md`.
It MUST contain, for each of the two configurations:

- the full cost-tier table exactly as printed by the runner
- window count, breakeven cost in bps, median eligible combos (of 18)
- the exit-reason distribution at the gate and the `end_of_data` share
- positive-window fraction on the **full** record and on the **2022+ sub-record**, next to Phase 1's
  43% over 14 windows
- how many windows selected the baseline combo `(1.5, 3.0, 48)`
- both verdicts (`phase_gate_verdict` and `promotion_verdict`) with their reasons
- both breaker lines: live `3% / 3-streak`, and daily-loss-only

Plus these sections:

- **Archive continuity** — the Task 2 Step 5 numbers for both symbols, and the statement that the
  deep archive is USD-quoted while Phase 1's was USDT-quoted, with the measured median difference in
  bps. If the pre-registered 50 bps threshold was breached, say so and treat every Phase 1
  comparison as unsupported.
- **Was 36–43% noise?** — the direct answer, stated against the pre-registered bands (≥50% /
  43–50% / <43%) declared before the run. Name the band the result landed in. Do not re-draw them.
- **Does 2022+ reproduce Phase 1?** — the sub-record fraction against Phase 1's 43%. A large gap
  here means venue or resolution changed the measurement, not history, and every full-record claim
  must be qualified accordingly.
- **Do the live breakers permit this?** — the first-halt timestamp and blocked fraction. If the
  switch trips terminally early in the record, state plainly that the headline edge is not
  realisable by the live strategy as configured, and that this dominates the window-fraction result.
  Repeat the three approximations from `lab/breakers.py`'s docstring so the number is read correctly.
- **Decision** — whether the promotion gate passed, and the next action that follows.

- [ ] **Step 3: Verify the document reports what the run produced**

Re-read `/tmp/phase2-deep-run.log` next to the written document and confirm every number in the
document appears in the log. Do not round, restate, or soften a verdict.

- [ ] **Step 4: Commit**

```bash
git add docs/PHASE2_DEEP_FINDINGS.md
git commit -m "docs: Phase 2 deep exit-geometry findings"
```

---

### Task 6: The daily arm

Spec §6's literal daily study, run as its own question — does an even longer horizon amortise the
fixed 60 bps further? — not as the consistency test, which Task 5 owns. Its `train_days` is chosen
by a rule over **trade counts only**, so no result can influence the choice.

**Files:**
- Create: `lab/research_exit_geometry_daily.py`
- Test: `tests/test_lab_walkforward.py` (the `select_train_days` rule is pure and gets unit tests)

**Interfaces:**
- Consumes: `COSTS`, `GATE_COST` from `lab.research_exit_geometry`; `base_profile` from
  `lab.research_ema_4h`; `walk_forward`, `promotion_verdict`, `phase_gate_verdict`,
  `breakeven_cost` from `lab.walkforward`; `apply_breakers` from `lab.breakers`.
- Produces: `DAILY_EXIT_GRID: list[dict]` (18 combos, holds rescaled to 8/20 bars),
  `TRAIN_DAYS_CANDIDATES: list[int]`, `daily_profile(symbol: str) -> StrategyProfile`,
  `select_train_days(probe: list[tuple[int, float]], *, min_median_eligible: int = 3) -> int | None`,
  `main() -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_lab_walkforward.py`:

```python
def test_select_train_days_takes_the_smallest_candidate_that_clears_the_bar():
    probe = [(365, 0.0), (730, 1.0), (1095, 5.0), (1460, 9.0)]
    assert select_train_days(probe) == 1095


def test_select_train_days_is_none_when_no_candidate_clears_the_bar():
    # Not a negative result: the daily study is structurally untestable.
    assert select_train_days([(365, 0.0), (730, 1.0), (1095, 2.0)]) is None


def test_select_train_days_ignores_candidate_order():
    probe = [(1460, 9.0), (365, 3.0), (730, 8.0)]
    assert select_train_days(probe) == 365


def test_select_train_days_honours_a_custom_bar():
    probe = [(365, 2.0), (730, 4.0)]
    assert select_train_days(probe, min_median_eligible=5) is None
    assert select_train_days(probe, min_median_eligible=2) == 365
```

Add `from lab.research_exit_geometry_daily import select_train_days` to the imports.

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_lab_walkforward.py -k select_train_days -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'lab.research_exit_geometry_daily'`.

- [ ] **Step 3: Implement**

Create `lab/research_exit_geometry_daily.py`:

```python
"""Phase 2 secondary arm - the exit grid at daily resolution.

This is spec section 6's literal daily study, kept because it asks a real
question the 4h study cannot: daily ATR is several times wider than 4h ATR, so a
fixed 60 bps round trip is a much smaller fraction of the move captured. If the
binding constraint really is cost relative to move size, a daily horizon should
amortise it further still.

It is NOT the consistency test. At 1d a 90-day test window carries on the order
of one or two trades, so its per-window statistic is noisier than the 14-window
record Phase 1 produced - which is exactly why the primary study stayed at 4h.

Two adaptations, both pre-registered before the run:

1. Hold levels are rescaled to the CALENDAR equivalents of the 4h grid: 48 bars
   at 4h is 8 days, 120 bars is 20 days. Carrying 48 and 120 over as bar counts
   would mean 48- and 120-DAY holds against a 90-day test window, which would
   force end_of_data truncation past the 15% validity ceiling by construction.
2. `train_days` is selected by `select_train_days` from a probe of ELIGIBILITY
   COUNTS ONLY - how many grid combos clear the untouchable min_train_trades=20.
   No profit factor, net return or window fraction enters the choice, so it
   cannot import hindsight. If no candidate clears the bar the arm reports
   INCONCLUSIVE and does not run: structurally untestable, not negative.

Run:
    SWINGBOT_DATA_DIR=/tmp/swingbot-deep .venv/bin/python -m lab.research_exit_geometry_daily
"""
from __future__ import annotations

import dataclasses

from lab.breakers import apply_breakers
from lab.research_data import load
from lab.research_ema_4h import base_profile
from lab.research_exit_geometry import COSTS, GATE_COST
from lab.walkforward import (breakeven_cost, phase_gate_verdict, profit_factor,
                             promotion_verdict, walk_forward)

# Same stop/take-profit multiples as Phase 1; holds rescaled to calendar days.
DAILY_EXIT_GRID = [
    {"stop_atr_mult": s, "take_profit_atr_mult": tp, "max_hold_bars": h}
    for s in (1.5, 2.5, 3.5)
    for tp in (3.0, 6.0, 9.0)
    for h in (8, 20)
]

TRAIN_DAYS_CANDIDATES = [365, 730, 1095, 1460]
MIN_MEDIAN_ELIGIBLE = 3


def select_train_days(probe: list[tuple[int, float]], *,
                      min_median_eligible: int = MIN_MEDIAN_ELIGIBLE) -> int | None:
    """Smallest train_days whose median eligible-combo count clears the bar.

    Reads ONLY trade-count eligibility, never P&L, so the choice cannot import
    hindsight. Returns None when nothing clears it - which means the daily study
    is structurally untestable rather than negative.
    """
    for train_days, median_eligible in sorted(probe):
        if median_eligible >= min_median_eligible:
            return train_days
    return None


def daily_profile(symbol: str):
    """Phase 1's frozen signal parameters, relabelled for daily bars.

    Only metadata changes. `_warmup_bars` and the hold cap both read the DATA's
    bar spacing, not `profile.timeframe`, so leaving it at "4h" would change no
    behaviour - but it would stamp "ema-4h" on every daily verdict, which is
    exactly the kind of mislabel that outlives the session that made it.
    """
    return dataclasses.replace(base_profile(symbol), timeframe="1d", label="ema-1d")


def _probe(df, profile) -> list[tuple[int, float]]:
    """Eligibility only: how many combos clear min_train_trades per window."""
    probe: list[tuple[int, float]] = []
    for train_days in TRAIN_DAYS_CANDIDATES:
        result = walk_forward(df, profile, DAILY_EXIT_GRID, round_trip=GATE_COST,
                              train_days=train_days, test_days=90, step_days=90)
        probe.append((train_days, result.median_eligible_combos))
        print(f"  probe train_days={train_days:5d} | windows {len(result.windows):3d} "
              f"| median eligible {result.median_eligible_combos:.1f} "
              f"(of {len(DAILY_EXIT_GRID)})", flush=True)
    return probe


def main() -> None:
    for symbol in ("BTC/USD", "ETH/USD"):
        df = load(symbol, "1d")
        profile = daily_profile(symbol)
        print(f"\n=== ema-1d {symbol}: {len(df)} bars "
              f"{df['ts'].iloc[0]} -> {df['ts'].iloc[-1]} ===", flush=True)

        train_days = select_train_days(_probe(df, profile))
        if train_days is None:
            print(f"  INCONCLUSIVE - no train_days in {TRAIN_DAYS_CANDIDATES} reaches "
                  f"a median of {MIN_MEDIAN_ELIGIBLE} eligible combos per window; "
                  f"the daily arm is structurally untestable at min_train_trades=20",
                  flush=True)
            continue
        print(f"  selected train_days={train_days} (smallest clearing the "
              f"eligibility bar)", flush=True)

        pf_by_cost: dict[float, float] = {}
        graded = None
        for cost in COSTS:
            result = walk_forward(df, profile, DAILY_EXIT_GRID, round_trip=cost,
                                  train_days=train_days, test_days=90, step_days=90)
            verdict = promotion_verdict(result)
            pf_by_cost[cost] = verdict.profit_factor
            if cost == GATE_COST:
                graded = result
            marker = "  <-- GATE" if cost == GATE_COST else ""
            print(f"  {cost * 10_000:5.0f} bps | windows {len(result.windows):3d} "
                  f"| trades {verdict.n_trades:5d} | net {verdict.net_return_pct:7.2f}% "
                  f"| PF {verdict.profit_factor:5.2f} "
                  f"| +windows {verdict.positive_window_frac:4.0%} "
                  f"| {verdict.decision}{marker}", flush=True)

        breakeven = breakeven_cost(pf_by_cost)
        gate = phase_gate_verdict(graded, breakeven)
        promotion = promotion_verdict(graded)
        be_txt = f"{breakeven * 10_000:.0f} bps" if breakeven is not None else "none"
        report = apply_breakers(graded.oos_trades)
        when = report.halted_at.isoformat() if report.halted_at is not None else "never"

        print(f"  breakeven: {be_txt}")
        print(f"  median eligible combos/window: {graded.median_eligible_combos:.1f} "
              f"(of {len(DAILY_EXIT_GRID)})")
        print(f"  exit reasons @ gate: {graded.exit_reason_counts()}")
        print(f"  end_of_data share: {graded.end_of_data_frac:.1%}")
        print(f"  selected combos: " + ", ".join(str(w.combo) for w in graded.windows))
        print(f"  breakers[live 3%/3-streak]: kept {report.n_kept}/"
              f"{len(graded.oos_trades)} ({report.blocked_frac:.0%} blocked) "
              f"| first halt {when} | {report.halt_reason or 'no trip'} "
              f"| PF kept {profit_factor(report.kept):.2f}")
        print(f"  PHASE GATE: {gate.decision} - {gate.reason}")
        print(f"  PROMOTION GATE: {promotion.decision} - {promotion.reason}", flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_lab_walkforward.py -k select_train_days -v
.venv/bin/python -m ruff check lab/research_exit_geometry_daily.py
```

Expected: 4 passed, ruff clean.

- [ ] **Step 5: Run the daily arm**

Daily bars are ~4k per symbol, so this is far cheaper than the 4h study — expect a few minutes.

```bash
cd /home/redji/crypto-swing-bot
SWINGBOT_DATA_DIR=/tmp/swingbot-deep .venv/bin/python -m lab.research_exit_geometry_daily \
  2>&1 | tee /tmp/phase2-daily-run.log
```

- [ ] **Step 6: Append the daily arm to the findings**

Add a `## Secondary arm — daily resolution` section to `docs/PHASE2_DEEP_FINDINGS.md` containing,
per symbol: the eligibility probe table (all four `train_days` candidates with their median eligible
counts), the selected `train_days` **or** the INCONCLUSIVE statement, and — when it ran — the full
cost-tier table, breakeven, exit reasons, `end_of_data` share, both verdicts, and the breaker line.

State explicitly that the hold levels were rescaled to 8/20 bars before the run and why, and that
this arm tests cost amortisation at a longer horizon, not Phase 1's consistency question.

- [ ] **Step 7: Commit**

```bash
git add lab/research_exit_geometry_daily.py tests/test_lab_walkforward.py \
  docs/PHASE2_DEEP_FINDINGS.md
git commit -m "feat(lab): daily exit-geometry arm with pre-registered train_days selection"
```

---

### Task 7: Gate, rebuild, and update the roadmap

**Files:**
- Modify: `docs/ROADMAP_STATUS.md`

**Interfaces:**
- Consumes: everything above.
- Produces: a clean gate, a verified-unharmed live bot, and a roadmap whose NEXT ACTION reflects the
  outcome.

- [ ] **Step 1: Run the full backend gate**

```bash
cd /home/redji/crypto-swing-bot
.venv/bin/python -m pytest -q 2>&1 | tail -5
.venv/bin/python -m ruff check .
```

Expected: pytest green at or above the 616 passed / 5 skipped baseline, plus this plan's new tests
(5 deep-backfill, 9 breakers, 4 series-agreement, 4 select-train-days ⇒ **638 passed, 5 skipped**);
ruff clean.

- [ ] **Step 2: Rebuild and restart the container**

Required by the standing Docker policy for any change under `crypto-swing-bot/`, even though `lab/`
is not packaged into the image.

```bash
docker compose build swingbot && docker compose up -d swingbot
```

- [ ] **Step 3: Verify the live bot is unharmed**

Read-only calls only — never mutate the live container.

```bash
curl -s localhost:8000/api/health/ready
curl -s localhost:8000/api/coins
```

Expected: `ready:true` and the armed Kronos strategies listed. This study touched no `src/`
behaviour, so the live bot must be exactly as it was.

- [ ] **Step 4: Update the roadmap**

Add a new `▶ LATEST SESSION (2026-08-01)` section at the top of `docs/ROADMAP_STATUS.md` recording:
the deep window counts, the full-record and 2022+ positive-window fractions against Phase 1's 43%,
which pre-registered band the result landed in, the breakeven, the breaker finding (first-halt
timestamp and blocked fraction), the daily arm's outcome, and — importantly — the two archive facts
future sessions will otherwise re-discover the hard way: that `backfill_cli` maps USD→USDT and so
caps Coinbase history at 2022 unless `quote_map={}` is passed, and that `run_backtest_fast` applies
no circuit breakers.

Then rewrite `▶ NEXT ACTION` to reflect the real state:

- **If the promotion gate passed and the breakers permit it:** NEXT ACTION is BRAINSTORM a
  deployment spec — how a research configuration becomes an armed strategy alongside the live
  Kronos-only paper trader, with the breaker settings the study showed are required.
- **If the promotion gate passed but the breakers halt the record terminally:** NEXT ACTION is
  BRAINSTORM the breaker-compatible variant — the edge is real but unreachable under
  `max_consecutive_losses=3` with a permanent kill switch, which is a risk-policy question
  (auto-reset cadence, streak limit, position sizing against a wider stop), not a signal question.
- **If the result landed below 43%:** NEXT ACTION is BRAINSTORM, and the entry must state that exit
  geometry is now exhausted alongside the signal grids, leaving the two untried avenues from the
  2026-07-26 entry — lowering cost per round trip (which requires a fill model first, since assuming
  limit orders fill is optimistic through adverse selection) and a genuinely different edge source
  (order-flow imbalance, cross-venue basis, event-driven).
- **If either run reported INCONCLUSIVE:** NEXT ACTION states which validity condition failed and
  what would have to change to test it, and explicitly does **not** close the track.

- [ ] **Step 5: Commit**

```bash
git add docs/ROADMAP_STATUS.md
git commit -m "docs: roadmap status after the Phase 2 deep exit-geometry study"
```

---

## Self-Review

**Spec coverage:**

| spec section | task |
|---|---|
| §6.1 backfill deep Coinbase history | Task 1 (`lab/deep_backfill.py`), with the quote-map fix §6 did not anticipate |
| §6.2 re-run the winning config's exit grid | Task 4 at 4h (primary), Task 6 at 1d (secondary) — grid imported from Phase 1, not retyped |
| §6.3 grade at the unchanged 60 bps gate | Tasks 4 and 6 (`promotion_verdict` untouched, `GATE_COST` imported) |
| §6 "~38 windows across three cycles" | Task 4 — ~40 (BTC) / ~37 (ETH); the 1d route could not deliver this under `min_train_trades=20`, see Deviations |
| §6 premium/EMA asymmetry | Honoured: the study is `ema-4h` only. `premium-standalone` needs OKX spot, which paginates keyless only from 2022, so it gains no depth and is out of scope |
| §3.4 breaker interaction "first thing Phase 2 should examine" | Task 3 (`lab/breakers.py`) + reported in Tasks 4 and 6 |
| §7 testing | Tasks 1–3, 6 test steps; Task 7 Step 1 full gate; `tests/test_lab_signal_parity.py` untouched |
| §9 deliverable | Tasks 5 and 6 (`docs/PHASE2_DEEP_FINDINGS.md`) + Task 7 (roadmap) |

**Known deviations from §6, all argued in "Deviations from spec §6" above:** primary resolution is
4h rather than 1d; the daily arm is retained but reframed and its holds rescaled to 8/20 bars; the
backfill needs `quote_map={}`; the breaker measurement needed new code because `run_backtest_fast`
models no breakers.

**Type consistency:** `COSTS`, `GATE_COST`, `EXIT_GRID` and `BASELINE_COMBO` are **imported** from
`lab.research_exit_geometry` by both new runners — Task 4 Step 2 asserts identity by `is`, so the
Phase 1 and Phase 2 configurations cannot drift. Costs are rates throughout (0.0060 == 60 bps);
`breakeven_cost` takes and returns a rate and only `Verdict.breakeven_bps` is in bps.
`apply_breakers` reads only `entry_ts`, `exit_ts`, `pnl`, which `swingbot.journal.Trade` supplies and
the test fake mirrors. `series_agreement` returns `n_overlap` / `median_rel_diff` / `max_rel_diff`,
the same keys Task 2 Step 5 prints. `select_train_days` takes `list[tuple[int, float]]` — exactly
what `_probe` returns.

**Placeholder scan:** no TBD/TODO; every code step carries the actual code; every verification step
names the concrete expected output and what to do when it is not met (Task 1 Step 6 names the
2022-01-01 symptom of a mis-set quote map; Task 2 Step 5 names the 50 bps pre-registered threshold;
Task 4 Step 3 names the `median eligible == 0` stop condition).
