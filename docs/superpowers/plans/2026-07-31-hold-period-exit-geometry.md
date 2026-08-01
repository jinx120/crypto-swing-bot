# Hold-Period / Exit-Geometry Study Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine whether varying exit geometry — the one axis no prior crypto-swing-bot study
ever gridded — raises any candidate signal's breakeven round-trip cost to the 60 bps we actually pay.

**Architecture:** Three additions to the existing `lab/walkforward.py` harness (breakeven-cost
location, grid-eligibility instrumentation, exit-reason diagnostics + a phase-gate verdict), then one
new research runner that grids 18 exit-geometry combinations against frozen signal parameters across
4 configurations. Pure research code in `lab/`; no `src/` behaviour changes; the live bot is untouched.

**Tech Stack:** Python 3.12, pandas, pytest, the validated `run_backtest_fast` harness,
`.venv/bin/python`.

## Global Constraints

- **The 60 bps promotion gate is not relaxed.** `promotion_verdict()` keeps `min_trades=30`,
  `min_pf=1.10`, `min_positive_window_frac=0.5`. Do not edit that function's thresholds or behaviour.
- **`min_train_trades=20` is not relaxed.** Starvation is instrumented, never tuned away.
- **Grids are fixed before the run.** No widening a grid after seeing results. No adding a parameter
  level because a result was close.
- **Signal parameters are frozen at declared base-profile defaults**: EMA `fast 21 / slow 55 /
  band 0.001 / entry_threshold 0.65`; premium `lookback 180 / band 2.0 / entry_threshold 0.65`.
- **Data dir:** every research command runs with `SWINGBOT_DATA_DIR=/tmp/swingbot-bt`. Never write to
  `~/.swingbot/`.
- **Never issue mutating HTTP calls against the live container.**
- **Docker rebuild policy:** `docker compose build swingbot && docker compose up -d swingbot` after
  any code change under `crypto-swing-bot/`, unconditionally.
- **Python invocation:** `.venv/bin/python` from the repo root. Tests: `.venv/bin/python -m pytest`.

---

### Task 1: Restore the research archive

`/tmp` is ephemeral and was cleared by a reboot; the 15m archive and the premium series both need
rebuilding before any runner can execute. No test cycle — this is an environment prerequisite whose
deliverable is verified by a data assertion.

**Files:**
- No source changes. Produces `/tmp/swingbot-bt/candles.db` and the premium series.

**Interfaces:**
- Consumes: nothing.
- Produces: `/tmp/swingbot-bt/candles.db` containing Coinbase 15m BTC/USD and ETH/USD from
  2022-01-01; a `cb_premium` series readable by `lab/research_premium.py`'s loader.

- [ ] **Step 1: Backfill Coinbase 15m OHLCV**

```bash
cd /home/redji/crypto-swing-bot
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m swingbot.backfill_cli \
  --exchange coinbase --symbols BTC/USD,ETH/USD --timeframes 15m --start 2022-01-01
```

Takes roughly 8 minutes. Coinbase rate-limits, so transient pauses are normal.

- [ ] **Step 2: Verify bar counts**

```bash
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -c "
from lab.strategy_backtest import load
for sym in ('BTC/USD', 'ETH/USD'):
    df = load(sym, '15m')
    print(sym, len(df), df['ts'].iloc[0], '->', df['ts'].iloc[-1])
"
```

Expected: roughly 158,000+ bars per symbol, starting 2022-01-01. Fewer than 150,000 means the
backfill was truncated — re-run Step 1 before continuing.

- [ ] **Step 3: Rebuild the Coinbase premium series**

```bash
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.premium_ingest
```

- [ ] **Step 4: Verify the premium series**

```bash
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -c "
from swingbot.data.series_store import SeriesStore
import os
s = SeriesStore(os.path.join('/tmp/swingbot-bt', 'series.db'))
rows = s.read('cb_premium')
print('cb_premium rows:', len(rows), rows[0][0] if rows else None, '->', rows[-1][0] if rows else None)
"
```

Expected: ~10,000 rows from 2022-01-01. If `SeriesStore.read` has a different signature, read
`src/swingbot/data/series_store.py` and adapt the call — the assertion to satisfy is "roughly 10k
premium rows spanning 2022-01-01 to now".

- [ ] **Step 5: Commit nothing**

This task produces no tracked files. `/tmp/swingbot-bt` is deliberately outside the repo. Confirm
with `git status --short` that the tree is still clean, then proceed.

---

### Task 2: `breakeven_cost()` — locate where PF crosses 1.0

**Files:**
- Modify: `lab/walkforward.py` (add function after `profit_factor`, around line 121)
- Test: `tests/test_lab_walkforward.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `breakeven_cost(pf_by_cost: dict[float, float]) -> float | None`. Input maps round-trip
  cost **as a rate** (0.0060 == 60 bps) to profit factor. Returns the crossing cost as a rate, or
  `None` when there is no gross edge.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_lab_walkforward.py`:

```python
def test_breakeven_cost_returns_last_tier_before_pf_drops_below_one():
    pf = {0.0: 1.30, 0.0025: 1.15, 0.0050: 1.02, 0.0060: 0.97, 0.0080: 0.90}
    assert breakeven_cost(pf) == 0.0050


def test_breakeven_cost_includes_a_tier_sitting_exactly_at_one():
    pf = {0.0: 1.20, 0.0050: 1.00, 0.0060: 0.95}
    assert breakeven_cost(pf) == 0.0050


def test_breakeven_cost_returns_highest_tier_when_pf_never_drops_below_one():
    pf = {0.0: 1.40, 0.0050: 1.25, 0.0080: 1.10}
    assert breakeven_cost(pf) == 0.0080


def test_breakeven_cost_is_none_when_there_is_no_gross_edge():
    pf = {0.0: 0.95, 0.0050: 0.80}
    assert breakeven_cost(pf) is None


def test_breakeven_cost_takes_the_first_downward_crossing_not_a_later_rebound():
    # A noisy curve that dips below 1.0 and pops back above it must not report
    # the rebound tier - that would overstate the cost the signal survives.
    pf = {0.0: 1.30, 0.0025: 1.10, 0.0050: 0.98, 0.0060: 1.04, 0.0080: 0.70}
    assert breakeven_cost(pf) == 0.0025


def test_breakeven_cost_of_an_empty_sweep_is_none():
    assert breakeven_cost({}) is None
```

Add `breakeven_cost` to the existing `from lab.walkforward import (...)` block at the top of the file.

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_lab_walkforward.py -k breakeven -v
```

Expected: FAIL — `ImportError: cannot import name 'breakeven_cost'`.

- [ ] **Step 3: Implement**

Add to `lab/walkforward.py` immediately after `profit_factor`:

```python
def breakeven_cost(pf_by_cost: dict[float, float]) -> float | None:
    """Round-trip cost at which profit factor crosses 1.0, as a rate.

    Returns the largest swept cost `c` such that PF >= 1.0 at `c` AND at every
    swept tier below `c` - the FIRST downward crossing. Deliberately not "the
    highest tier with PF >= 1.0": on a noisy curve a single tier rebounding above
    1.0 further out would overstate the cost the signal actually survives.

    Returns None when PF is already below 1.0 at the cheapest swept tier, i.e.
    there is no gross edge to charge cost against.
    """
    survived = None
    for cost in sorted(pf_by_cost):
        if pf_by_cost[cost] < 1.0:
            break
        survived = cost
    return survived
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_lab_walkforward.py -k breakeven -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add lab/walkforward.py tests/test_lab_walkforward.py
git commit -m "feat(lab): breakeven_cost locates the first downward PF crossing"
```

---

### Task 3: Instrument grid eligibility

`walk_forward` silently skips combos with fewer than `min_train_trades` training trades. Longer holds
mean fewer trades, and the filter culls precisely the combos that trade least — so the surviving set
skews toward whichever exits close fastest. Uninstrumented, a study designed to test long holds could
quietly re-select for short ones and report a negative result for the wrong reason.

**Files:**
- Modify: `lab/walkforward.py` (`WindowResult`, `WalkForwardResult`, `walk_forward`)
- Test: `tests/test_lab_walkforward.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `WindowResult.n_eligible_combos: int` (defaults to `0`);
  `WalkForwardResult.median_eligible_combos -> float` property.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_lab_walkforward.py`:

```python
def test_window_result_defaults_eligible_combos_to_zero():
    # Existing constructions in this file omit the new field; they must keep working.
    wr = WindowResult(window=Window(_ts("2022-01-01"), _ts("2022-02-01"),
                                    _ts("2022-02-01"), _ts("2022-03-01")),
                      combo={}, train_pf=1.0, trades=[], net_pnl=0.0)
    assert wr.n_eligible_combos == 0


def test_median_eligible_combos_across_windows():
    result = _result([[1.0], [1.0], [1.0]])
    counted = [dataclasses.replace(w, n_eligible_combos=n)
               for w, n in zip(result.windows, [1, 5, 9])]
    result = dataclasses.replace(result, windows=counted)
    assert result.median_eligible_combos == 5.0


def test_median_eligible_combos_of_no_windows_is_zero():
    result = WalkForwardResult(label="x", symbol="BTC/USD", windows=[], oos_trades=[])
    assert result.median_eligible_combos == 0.0
```

Add `dataclasses` to the test file's imports, and add `WindowResult` and `WalkForwardResult` to the
`from lab.walkforward import (...)` block.

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_lab_walkforward.py -k eligible -v
```

Expected: FAIL — `TypeError: WindowResult.__init__() got an unexpected keyword argument` or
`AttributeError: 'WalkForwardResult' object has no attribute 'median_eligible_combos'`.

- [ ] **Step 3: Implement**

In `lab/walkforward.py`, add `import statistics` to the imports. Then:

```python
@dataclass(frozen=True)
class WindowResult:
    window: Window
    combo: dict
    train_pf: float
    trades: list
    net_pnl: float
    n_eligible_combos: int = 0
```

```python
@dataclass(frozen=True)
class WalkForwardResult:
    label: str
    symbol: str
    windows: list[WindowResult]
    oos_trades: list

    @property
    def median_eligible_combos(self) -> float:
        """Median count of grid combos that cleared min_train_trades per window.

        A low value means selection was starved - the harness had almost nothing
        to choose between - which invalidates a verdict rather than supporting one.
        """
        if not self.windows:
            return 0.0
        return float(statistics.median(w.n_eligible_combos for w in self.windows))
```

In `walk_forward`, count eligible combos inside the window loop and pass the count through:

```python
    for window in windows:
        train_df = _slice(df, window.train_start, window.train_end, warmup)
        best_combo, best_pf = None, float("-inf")
        n_eligible = 0
        for combo in grid:
            trades = _run(train_df, apply_combo(costed, combo), benchmark_df, starting_equity)
            trades = [t for t in trades if t.entry_ts >= window.train_start]
            if len(trades) < min_train_trades:
                continue
            n_eligible += 1
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
            trades=test_trades, net_pnl=sum(t.pnl for t in test_trades),
            n_eligible_combos=n_eligible))
```

- [ ] **Step 4: Run the full walkforward suite**

```bash
.venv/bin/python -m pytest tests/test_lab_walkforward.py -v
```

Expected: all pass, including the pre-existing tests — the new field defaults so nothing breaks.

- [ ] **Step 5: Commit**

```bash
git add lab/walkforward.py tests/test_lab_walkforward.py
git commit -m "feat(lab): instrument grid eligibility per walk-forward window"
```

---

### Task 4: Exit-reason diagnostics and the phase-gate verdict

`Trade.exit_reason` is already populated by the real `SimulatedBroker`; the enum is
`STOP | TAKE_PROFIT | TIME_CAP | END_OF_DATA`. Two things need surfacing: the distribution (does the
hold ceiling ever bind?) and specifically the `END_OF_DATA` share, which measures a truncation bias
that grows with hold length — 90-day test windows against a 20-day max hold leave a tail in which new
positions cannot develop before being force-closed.

**Files:**
- Modify: `lab/walkforward.py` (`Verdict`, `WalkForwardResult`, add `phase_gate_verdict`)
- Test: `tests/test_lab_walkforward.py`

**Interfaces:**
- Consumes: `breakeven_cost` (Task 2), `WalkForwardResult.median_eligible_combos` (Task 3).
- Produces: `WalkForwardResult.exit_reason_counts() -> dict[str, int]`;
  `WalkForwardResult.end_of_data_frac -> float` property;
  `Verdict` gains `breakeven_bps: float | None = None`,
  `median_eligible_combos: float | None = None`, `end_of_data_frac: float | None = None`;
  `phase_gate_verdict(result, breakeven, *, min_breakeven=0.0060, min_median_eligible=3,
  max_end_of_data_frac=0.15) -> Verdict` with `decision` in `{"PROMOTE", "REJECT", "INCONCLUSIVE"}`.

`promotion_verdict` is NOT modified. The phase gate is a separate decision from the promotion gate,
and the promotion gate is a global constraint.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_lab_walkforward.py`:

```python
class _FakeExitTrade(_FakeTrade):
    def __init__(self, entry_ts, pnl, exit_reason, entry_price=100.0, qty=1.0):
        super().__init__(entry_ts, pnl, entry_price, qty)
        self.exit_reason = exit_reason


def _exit_result(reasons, eligible=9):
    trades = [_FakeExitTrade(_ts("2022-06-01"), 1.0, r) for r in reasons]
    window = Window(_ts("2022-01-01"), _ts("2023-01-01"),
                    _ts("2023-01-01"), _ts("2023-04-01"))
    wr = WindowResult(window=window, combo={}, train_pf=1.2, trades=trades,
                      net_pnl=float(len(trades)), n_eligible_combos=eligible)
    return WalkForwardResult(label="exit-geom", symbol="BTC/USD",
                             windows=[wr], oos_trades=trades)


def test_exit_reason_counts_tallies_every_reason():
    result = _exit_result(["take_profit", "take_profit", "stop", "time_cap", "end_of_data"])
    assert result.exit_reason_counts() == {
        "take_profit": 2, "stop": 1, "time_cap": 1, "end_of_data": 1}


def test_exit_reason_counts_sum_to_the_trade_count():
    result = _exit_result(["stop"] * 7 + ["take_profit"] * 3)
    assert sum(result.exit_reason_counts().values()) == len(result.oos_trades)


def test_end_of_data_frac_measures_boundary_truncation():
    result = _exit_result(["end_of_data"] * 2 + ["take_profit"] * 8)
    assert result.end_of_data_frac == 0.2


def test_end_of_data_frac_of_no_trades_is_zero():
    result = WalkForwardResult(label="x", symbol="BTC/USD", windows=[], oos_trades=[])
    assert result.end_of_data_frac == 0.0


def test_phase_gate_promotes_when_breakeven_reaches_the_real_cost():
    result = _exit_result(["take_profit"] * 10)
    v = phase_gate_verdict(result, 0.0060)
    assert v.decision == "PROMOTE"
    assert v.breakeven_bps == 60.0


def test_phase_gate_rejects_when_breakeven_falls_short():
    result = _exit_result(["take_profit"] * 10)
    v = phase_gate_verdict(result, 0.0044)
    assert v.decision == "REJECT"
    assert "44" in v.reason


def test_phase_gate_rejects_when_there_is_no_gross_edge_at_all():
    result = _exit_result(["stop"] * 10)
    v = phase_gate_verdict(result, None)
    assert v.decision == "REJECT"
    assert v.breakeven_bps is None


def test_phase_gate_is_inconclusive_when_selection_was_starved():
    # Only 2 combos eligible per window: the harness had nothing to choose from,
    # so neither a pass nor a fail is meaningful.
    result = _exit_result(["take_profit"] * 10, eligible=2)
    v = phase_gate_verdict(result, 0.0080)
    assert v.decision == "INCONCLUSIVE"
    assert "eligible" in v.reason


def test_phase_gate_is_inconclusive_when_truncation_dominates():
    # 30% of trades force-closed at the window boundary: long-hold combos are
    # biased by truncation, not measured on their exits.
    result = _exit_result(["end_of_data"] * 3 + ["take_profit"] * 7)
    v = phase_gate_verdict(result, 0.0080)
    assert v.decision == "INCONCLUSIVE"
    assert "end_of_data" in v.reason


def test_phase_gate_validity_beats_a_failing_breakeven():
    # An invalid run is not gradeable in EITHER direction - it must not be
    # reported as REJECT, which would wrongly close the track.
    result = _exit_result(["end_of_data"] * 5 + ["take_profit"] * 5, eligible=1)
    v = phase_gate_verdict(result, 0.0010)
    assert v.decision == "INCONCLUSIVE"
```

Add `phase_gate_verdict` to the `from lab.walkforward import (...)` block.

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_lab_walkforward.py -k "exit_reason or end_of_data or phase_gate" -v
```

Expected: FAIL — `ImportError: cannot import name 'phase_gate_verdict'`.

- [ ] **Step 3: Implement**

Add the two members to `WalkForwardResult` (alongside `median_eligible_combos` from Task 3):

```python
    def exit_reason_counts(self) -> dict[str, int]:
        """Tally of terminating reasons across the out-of-sample record.

        Answers whether the hold ceiling ever binds: if `time_cap` is near zero,
        raising max_hold_bars further cannot change anything.
        """
        counts: dict[str, int] = {}
        for trade in self.oos_trades:
            reason = getattr(trade.exit_reason, "value", trade.exit_reason)
            key = str(reason)
            counts[key] = counts.get(key, 0) + 1
        return counts

    @property
    def end_of_data_frac(self) -> float:
        """Share of trades force-closed at a test-window boundary.

        This is a truncation bias that GROWS with hold length - the variable under
        test - so a long-hold result carried by it is an artefact, not an edge.
        """
        if not self.oos_trades:
            return 0.0
        return self.exit_reason_counts().get("end_of_data", 0) / len(self.oos_trades)
```

Extend `Verdict` with three optional diagnostic fields:

```python
@dataclass(frozen=True)
class Verdict:
    label: str
    symbol: str
    decision: str          # "PROMOTE" | "REJECT" | "INCONCLUSIVE"
    reason: str
    n_trades: int
    net_return_pct: float
    profit_factor: float
    positive_window_frac: float
    breakeven_bps: float | None = None
    median_eligible_combos: float | None = None
    end_of_data_frac: float | None = None
```

Add `phase_gate_verdict` at the end of the module:

```python
def phase_gate_verdict(result: WalkForwardResult, breakeven: float | None, *,
                       min_breakeven: float = 0.0060,
                       min_median_eligible: int = 3,
                       max_end_of_data_frac: float = 0.15) -> Verdict:
    """Grade a config against the pre-registered Phase 1 -> Phase 2 gate.

    Two VALIDITY conditions are checked before the performance condition, and a
    failure of either reports INCONCLUSIVE rather than REJECT: an untestable run
    must never masquerade as a negative result and close the track.

    This is deliberately separate from `promotion_verdict`, which grades actual
    promotion at the untouched 60 bps gate.
    """
    trades = result.oos_trades
    n = len(trades)
    notional = sum(t.entry_price * t.qty for t in trades)
    net_pct = (sum(t.pnl for t in trades) / notional * 100.0) if notional else 0.0
    pf = profit_factor(trades)
    positive = sum(1 for w in result.windows if w.net_pnl > 0)
    frac = positive / len(result.windows) if result.windows else 0.0
    median_eligible = result.median_eligible_combos
    eod = result.end_of_data_frac
    breakeven_bps = breakeven * 10_000 if breakeven is not None else None

    def _verdict(decision: str, reason: str) -> Verdict:
        return Verdict(
            label=result.label, symbol=result.symbol, decision=decision, reason=reason,
            n_trades=n, net_return_pct=net_pct, profit_factor=pf,
            positive_window_frac=frac, breakeven_bps=breakeven_bps,
            median_eligible_combos=median_eligible, end_of_data_frac=eod)

    invalid = []
    if median_eligible < min_median_eligible:
        invalid.append(
            f"median {median_eligible:.1f} eligible combos per window "
            f"(need >= {min_median_eligible}); selection was starved")
    if eod > max_end_of_data_frac:
        invalid.append(
            f"end_of_data share {eod:.0%} exceeds {max_end_of_data_frac:.0%}; "
            f"result is driven by test-window truncation")
    if invalid:
        return _verdict("INCONCLUSIVE", "; ".join(invalid))

    if breakeven is None:
        return _verdict("REJECT", "no gross edge: PF below 1.0 at zero cost")
    if breakeven < min_breakeven:
        return _verdict(
            "REJECT",
            f"breakeven {breakeven_bps:.0f} bps below the "
            f"{min_breakeven * 10_000:.0f} bps gate")
    return _verdict(
        "PROMOTE",
        f"breakeven {breakeven_bps:.0f} bps reaches the "
        f"{min_breakeven * 10_000:.0f} bps gate")
```

- [ ] **Step 4: Run the full walkforward suite**

```bash
.venv/bin/python -m pytest tests/test_lab_walkforward.py -v
```

Expected: all pass, including every pre-existing test.

- [ ] **Step 5: Commit**

```bash
git add lab/walkforward.py tests/test_lab_walkforward.py
git commit -m "feat(lab): exit-reason diagnostics and pre-registered phase gate"
```

---

### Task 5: The exit-geometry research runner

**Files:**
- Create: `lab/research_exit_geometry.py`
- Test: none. Research runners in this repo (`research_ema_4h.py`, `research_funding.py`,
  `research_premium.py`) carry no unit tests — their correctness rests on the harness beneath them,
  which is tested, and on `tests/test_lab_signal_parity.py` pinning lab scoring to the live `Signal`
  classes. Follow that established pattern.

**Interfaces:**
- Consumes: `walk_forward`, `promotion_verdict`, `phase_gate_verdict`, `breakeven_cost`, `with_cost`
  (Tasks 2-4); `base_profile` from `lab.research_ema_4h`; `standalone_profile` from
  `lab.research_premium`; `load`, `resample`, `attach_extra` from `lab.research_data`.
- Produces: a runnable module printing per-config cost tables, breakeven, eligibility, exit-reason
  distribution, and both verdicts.

- [ ] **Step 1: Write the runner**

Create `lab/research_exit_geometry.py`:

```python
"""Exit-geometry walk-forward study.

Every prior crypto-swing-bot study held exit geometry constant at
stop_atr_mult 1.5 / take_profit_atr_mult 3.0 / max_hold_bars 48 and gridded only
signal parameters. This runner inverts that: signal parameters are frozen at the
base profiles' declared defaults and the 18-combo grid varies ONLY the exits.

The baseline combo (1.5 / 3.0 / 48) is a deliberate grid member. If walk-forward
keeps selecting it, that is direct evidence the exit lever is inert - a cleaner
null than "the widened variant lost", because the harness was free to pick either.

Graded against the pre-registered Phase 1 gate in
docs/superpowers/specs/2026-07-31-hold-period-exit-geometry-design.md:
breakeven >= 60 bps, median eligible combos >= 3, end_of_data share <= 15%.
"""
from __future__ import annotations

import os

from lab.research_data import attach_extra, load, resample
from lab.research_ema_4h import base_profile
from lab.research_premium import standalone_profile
from lab.walkforward import (breakeven_cost, phase_gate_verdict, profit_factor,
                             promotion_verdict, walk_forward)
from swingbot.data.series_store import SeriesStore

# Denser around the 60 bps gate than at the extremes: the gate only needs
# breakeven resolved near 60, and 0/10/25/60 are retained so the numbers stay
# directly comparable to the published SIGNAL_RESEARCH_FINDINGS.md tables.
COSTS = [0.0, 0.0010, 0.0025, 0.0050, 0.0055, 0.0060, 0.0065, 0.0070, 0.0080]
GATE_COST = 0.0060

# 18 combinations. The ONLY axis that varies. Baseline is (1.5, 3.0, 48).
EXIT_GRID = [
    {"stop_atr_mult": s, "take_profit_atr_mult": tp, "max_hold_bars": h}
    for s in (1.5, 2.5, 3.5)
    for tp in (3.0, 6.0, 9.0)
    for h in (48, 120)
]

DATA_DIR = os.environ.get("SWINGBOT_DATA_DIR", "/tmp/swingbot-bt")


def _premium_frame(df):
    """Attach the Coinbase premium series to 4h bars as x_cb_premium."""
    store = SeriesStore(os.path.join(DATA_DIR, "series.db"))
    import pandas as pd
    rows = store.read("cb_premium")
    series = pd.DataFrame(rows, columns=["ts", "value"])
    series["ts"] = pd.to_datetime(series["ts"], utc=True)
    return attach_extra(df, "cb_premium", series)


def _configs():
    """(label, symbol, profile_factory, needs_premium) for the 4 configurations."""
    for symbol in ("BTC/USD", "ETH/USD"):
        yield "ema-4h", symbol, base_profile, False
    for symbol in ("BTC/USD", "ETH/USD"):
        yield "premium-standalone", symbol, standalone_profile, True


def main() -> None:
    for label, symbol, factory, needs_premium in _configs():
        df = resample(load(symbol, "15m"), "4h")
        if needs_premium:
            df = _premium_frame(df)
        print(f"\n=== {label} {symbol} 4h: {len(df)} bars "
              f"{df['ts'].iloc[0]} -> {df['ts'].iloc[-1]} ===")

        pf_by_cost: dict[float, float] = {}
        graded = None
        for cost in COSTS:
            result = walk_forward(df, factory(symbol), EXIT_GRID, round_trip=cost,
                                  train_days=365, test_days=90, step_days=90)
            verdict = promotion_verdict(result)
            pf_by_cost[cost] = verdict.profit_factor
            if cost == GATE_COST:
                graded = result
            marker = "  <-- GATE" if cost == GATE_COST else ""
            print(f"  {cost * 10_000:5.0f} bps | windows {len(result.windows):2d} "
                  f"| trades {verdict.n_trades:4d} | net {verdict.net_return_pct:7.2f}% "
                  f"| PF {verdict.profit_factor:5.2f} "
                  f"| +windows {verdict.positive_window_frac:4.0%} "
                  f"| {verdict.decision}{marker}")

        breakeven = breakeven_cost(pf_by_cost)
        gate = phase_gate_verdict(graded, breakeven)
        be_txt = f"{breakeven * 10_000:.0f} bps" if breakeven is not None else "none"
        print(f"  breakeven: {be_txt}")
        print(f"  median eligible combos/window: {graded.median_eligible_combos:.1f} "
              f"(of {len(EXIT_GRID)})")
        print(f"  exit reasons @ gate: {graded.exit_reason_counts()}")
        print(f"  end_of_data share: {graded.end_of_data_frac:.1%}")
        print(f"  selected combos: "
              + ", ".join(str(w.combo) for w in graded.windows))
        print(f"  PHASE GATE: {gate.decision} - {gate.reason}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it imports and the grid is the intended size**

```bash
cd /home/redji/crypto-swing-bot
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -c "
from lab.research_exit_geometry import EXIT_GRID, COSTS
print('grid', len(EXIT_GRID), 'costs', len(COSTS))
print('baseline present:', {'stop_atr_mult': 1.5, 'take_profit_atr_mult': 3.0, 'max_hold_bars': 48} in EXIT_GRID)
"
```

Expected: `grid 18 costs 9` and `baseline present: True`.

- [ ] **Step 3: Smoke-test one config on a short slice**

Confirm the wiring works end to end before committing to a long run:

```bash
SWINGBOT_DATA_DIR=/tmp/swingbot-bt timeout 900 .venv/bin/python -c "
from lab.research_data import load, resample
from lab.research_ema_4h import base_profile
from lab.research_exit_geometry import EXIT_GRID
from lab.walkforward import walk_forward, promotion_verdict, phase_gate_verdict
df = resample(load('BTC/USD', '15m'), '4h')
df = df[df['ts'] < '2023-07-01'].reset_index(drop=True)
r = walk_forward(df, base_profile('BTC/USD'), EXIT_GRID, round_trip=0.0060)
v = promotion_verdict(r)
print('windows', len(r.windows), 'trades', v.n_trades, 'PF', round(v.profit_factor, 3))
print('median eligible', r.median_eligible_combos, 'exits', r.exit_reason_counts())
print('eod', round(r.end_of_data_frac, 3))
print(phase_gate_verdict(r, 0.0060).decision)
"
```

Expected: a small number of windows, a non-zero trade count, a populated exit-reason dict, and a
verdict string. If `median eligible` is 0 the grid is being filtered out entirely — stop and
investigate before running the full study.

- [ ] **Step 4: Lint**

```bash
.venv/bin/python -m ruff check lab/research_exit_geometry.py
```

Expected: clean. Move the `import pandas as pd` in `_premium_frame` to module scope if ruff objects.

- [ ] **Step 5: Commit**

```bash
git add lab/research_exit_geometry.py
git commit -m "feat(lab): exit-geometry walk-forward research runner"
```

---

### Task 6: Run the study and write the findings

**Files:**
- Create: `docs/HOLD_PERIOD_FINDINGS.md`

**Interfaces:**
- Consumes: `lab/research_exit_geometry.py` (Task 5).
- Produces: the findings document and a definitive pass/fail against the §5 phase gate.

- [ ] **Step 1: Run the full study**

```bash
cd /home/redji/crypto-swing-bot
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.research_exit_geometry \
  2>&1 | tee /tmp/exit-geometry-run.log
```

Expect roughly 45-90 minutes (9 cost tiers × 18 combos × 14 windows × 4 configurations). Run it in
the background and poll the log rather than blocking.

- [ ] **Step 2: Write the findings document**

Create `docs/HOLD_PERIOD_FINDINGS.md` following the structure of
`docs/SIGNAL_RESEARCH_FINDINGS.md`. It MUST contain, for each of the 4 configurations:

- the full cost-tier table exactly as printed by the runner
- the breakeven cost in bps
- median eligible combos per window (out of 18)
- the exit-reason distribution at the gate, and the `end_of_data` share
- the per-window selected combos
- the phase-gate decision and reason

Plus these sections:

- **Baseline comparison** — a table of the four configs' prior breakevens (~36 / ~18 / ~44 / ~22 bps
  for EMA-BTC / EMA-ETH / premium-BTC / premium-ETH) against the new ones, so the lever's effect size
  is stated as a delta rather than an absolute.
- **Did the hold ceiling bind?** — the `time_cap` share per config. If near zero, state plainly that
  `max_hold_bars` was not the operative variable and that any effect came from the ATR multiples.
- **Was the baseline combo selected?** — count how many of the 14 windows chose
  `(1.5, 3.0, 48)`. High counts are direct evidence the lever is inert.
- **Decision** — an explicit statement of whether the §5 phase gate passed, and therefore whether
  Phase 2 executes. If it did not pass, say so plainly and state that the track closes.

- [ ] **Step 3: Verify the document reports what the run produced**

Re-read `/tmp/exit-geometry-run.log` next to the written document and confirm every number in the
document appears in the log. Do not round, restate, or soften a verdict.

- [ ] **Step 4: Commit**

```bash
git add docs/HOLD_PERIOD_FINDINGS.md
git commit -m "docs: exit-geometry walk-forward findings"
```

---

### Task 7: Gate, rebuild, and update the roadmap

**Files:**
- Modify: `docs/ROADMAP_STATUS.md`

**Interfaces:**
- Consumes: everything above.
- Produces: a clean gate and a roadmap whose NEXT ACTION reflects the outcome.

- [ ] **Step 1: Run the full backend gate**

```bash
cd /home/redji/crypto-swing-bot
.venv/bin/python -m pytest -q 2>&1 | tail -5
.venv/bin/python -m ruff check .
```

Expected: pytest green with at least the prior baseline of 597 passed / 5 skipped, plus the new
walkforward tests; ruff clean.

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

Expected: `ready:true` and the armed Kronos strategies listed. The live bot must be exactly as it was
— this study touched no `src/` behaviour.

- [ ] **Step 4: Update the roadmap**

Add a new `▶ LATEST SESSION (2026-07-31)` section at the top of `docs/ROADMAP_STATUS.md` recording:
the phase-gate outcome, the breakeven deltas against baseline, whether the baseline combo kept being
selected, and whether the hold ceiling bound. Then rewrite `▶ NEXT ACTION` to reflect the real state:

- **If the gate passed:** NEXT ACTION is EXECUTE Phase 2 — the deep daily backfill and re-run, noting
  the §6 asymmetry (Coinbase daily reaches ~2015 for the price-only EMA config, but the premium leg
  needs OKX which paginates only from 2022).
- **If the gate failed or was INCONCLUSIVE:** NEXT ACTION is BRAINSTORM, and the entry must state
  that exit geometry is now exhausted alongside the signal grids, leaving the two untried avenues
  from the 2026-07-26 entry — lowering cost per round trip (which requires a fill model first, since
  assuming limit orders fill is optimistic through adverse selection) and a genuinely different edge
  source.

- [ ] **Step 5: Commit**

```bash
git add docs/ROADMAP_STATUS.md
git commit -m "docs: roadmap status after the exit-geometry study"
```

---

## Self-Review

**Spec coverage:**

| spec section | task |
|---|---|
| §3.1 scope — 4 configs, exclusions | Task 5 (`_configs`) |
| §3.2 frozen signal params | Task 5 (uses `base_profile` / `standalone_profile` unmodified) |
| §3.3 18-combo exit grid, baseline included | Task 5 (`EXIT_GRID`), verified in Step 2 |
| §3.4 held-fixed params | Task 5 (grid touches only the three exit keys) |
| §3.5 unchanged walk-forward config | Task 5 (`train_days=365, test_days=90, step_days=90`) |
| §4.1 `breakeven_cost` | Task 2 |
| §4.2 eligibility instrumentation | Task 3 |
| §4.3 exit-reason + END_OF_DATA guard | Task 4 |
| §4.4 `INCONCLUSIVE` decision value | Task 4 |
| §5 pre-registered phase gate | Task 4 (`phase_gate_verdict`), applied in Task 5 |
| §6 Phase 2 conditional | Task 7 Step 4 (routed by outcome; not executed in this plan) |
| §7 testing | Tasks 2-4 test steps; Task 7 Step 1 full gate |
| §9 deliverable | Task 6 |

**Known deviation from the spec, deliberate:** §4.1 specified sweeping 0→100 bps in 5 bps steps (21
tiers). The runner uses a 9-tier ladder instead. Rationale: 21 tiers × 18 combos × 14 windows × 4
configs is ~22,000 backtests, roughly 14× the prior study's load, and the gate only needs breakeven
resolved near 60 bps. The ladder keeps 0/10/25/60 for continuity with the published tables and gives
±5 bps resolution across 50-70 bps where the decision is actually made. The spec is amended to match.

**Type consistency:** `breakeven_cost` takes and returns cost as a *rate* (0.0060), and
`phase_gate_verdict` converts to bps only for display in `Verdict.breakeven_bps`. `COSTS` and
`min_breakeven` are rates throughout. `exit_reason_counts()` keys are the `ExitReason` *values*
(lowercase `"take_profit"`, `"end_of_data"`), matching the enum definition in `src/swingbot/types.py`.

**Placeholder scan:** no TBD/TODO; every code step carries the actual code; Task 1 Step 4 names the
concrete fallback (read `series_store.py` and adapt) rather than leaving it vague.
