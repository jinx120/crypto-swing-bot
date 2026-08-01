# Phase 2 — Deep Exit-Geometry Findings

**Date:** 2026-08-01
**Spec:** `docs/superpowers/specs/2026-07-31-hold-period-exit-geometry-design.md` §6
**Plan:** `docs/superpowers/plans/2026-08-01-phase-2-deep-exit-geometry.md`
**Runner:** `lab/research_exit_geometry_deep.py` · **Raw log:** `/tmp/phase2-deep-run.log`
**Predecessor:** `docs/HOLD_PERIOD_FINDINGS.md` (Phase 1, 2026-07-31)

---

## Summary

Phase 2 asked one question: **was Phase 1's 36–43% positive-window fraction small-sample noise, or a
real inconsistency?** It re-ran Phase 1's identical configuration — same frozen signal parameters,
same 18-combo exit grid, same 13-tier cost ladder, same 365/90/90 windows, all *imported* from the
Phase 1 runner rather than retyped — over Coinbase history from 2015-07-20 (BTC) and 2016-05-18
(ETH). That is **40 and 37 out-of-sample quarters across three market cycles**, up from 14 spanning
one and a half.

**Three findings, in order of importance:**

**1. The live circuit breaker makes the entire result undeployable as configured.** This is measured
here for the first time. The 3-consecutive-loss kill switch trips **2016-10-19** on BTC and
**2017-06-21** on ETH, and because nothing in `RiskManager` ever clears it, the halt is terminal:
**97% of out-of-sample trades are blocked on both symbols** (9 of 350 kept on BTC, 10 of 312 on ETH).
The 3% daily-loss breaker never trips on either symbol. Whatever the window fraction says, the live
strategy as configured would have stopped trading in year one and never resumed.

**2. Deep history splits the two symbols.** At the unchanged 60 bps gate:

| config | windows | trades | net | PF | +windows | promotion gate |
|---|---|---|---|---|---|---|
| `ema-4h` BTC/USD | 40 | 350 | +0.76% | 1.32 | **45%** | **REJECT** (window fraction) |
| `ema-4h` ETH/USD | 37 | 312 | +1.06% | 1.32 | **59%** | **PROMOTE** |

**ETH/USD is the first configuration in this project's history to pass `promotion_verdict` at 60 bps.**
BTC lands at 45%, inside the pre-registered 43–50% band.

**3. The edge is much more cost-robust than Phase 1 could see.** Breakeven round-trip cost is **150
bps on both symbols** — up from 90 and 70 in Phase 1, and against the 60 bps we actually pay. PF at
the gate is 1.32 on both, on 3.5× and 2.5× the Phase 1 trade counts.

**The gate was not relaxed and the grid was not widened.** `promotion_verdict` keeps `min_trades=30`,
`min_pf=1.10`, `min_positive_window_frac=0.5`; `min_train_trades=20` is untouched; the interpretation
bands below were fixed in the plan before the run.

---

## Archive continuity

Phase 1 ran on Coinbase's **USDT-quoted** market; the deep archive is **USD-quoted**. This is not a
cosmetic difference — the USD→USDT quote rewrite in `CcxtProvider` is exactly why every prior archive
in this project silently began at 2022-01-01, since Coinbase's USDT market returns zero rows before
then. `lab/deep_backfill.py` disables that rewrite; `lab/research_data.series_agreement` measures
whether the two series describe the same market before any deep number is set beside a Phase 1 number.

```
BTC/USD overlap 10038 median 3.73 bps max 153.3 bps
ETH/USD overlap 10037 median 4.01 bps max 143.9 bps
```

**Pre-registered threshold: median ≤ 50 bps and overlap ≥ 9,000 bars per symbol. Both symbols PASS**,
with a median under 4.1 bps against a 50 bps ceiling and ~10,038 overlapping 4h bars against a 9,000
floor. The ~150 bps maximum is a handful of isolated bars; the pre-registered statistic is the median.
Comparisons between Phase 1 and Phase 2 numbers are therefore supported.

**Deep archive depth** (193,648 bars fetched; no series begins at 2022-01-01, confirming the rewrite
was disabled):

```
BTC/USD  1h    96650 bars  2015-07-20 21:00:00+00:00 -> 2026-08-01 05:00:00+00:00
BTC/USD  1d     4031 bars  2015-07-20 00:00:00+00:00 -> 2026-08-01 00:00:00+00:00
ETH/USD  1h    89241 bars  2016-05-18 00:00:00+00:00 -> 2026-08-01 05:00:00+00:00
ETH/USD  1d     3726 bars  2016-05-18 00:00:00+00:00 -> 2026-08-01 00:00:00+00:00
```

---

## Results

### `ema-4h` BTC/USD — deep, 40 out-of-sample quarters

```
=== ema-4h BTC/USD 4h deep: 24172 bars 2015-07-20 20:00:00+00:00 -> 2026-08-01 04:00:00+00:00 ===
      0 bps | windows  40 | trades   380 | net    1.21% | PF  1.61 | +windows  62% | PROMOTE
     10 bps | windows  40 | trades   376 | net    1.13% | PF  1.55 | +windows  57% | PROMOTE
     25 bps | windows  40 | trades   363 | net    1.02% | PF  1.47 | +windows  52% | PROMOTE
     50 bps | windows  40 | trades   351 | net    0.85% | PF  1.37 | +windows  50% | PROMOTE
     55 bps | windows  40 | trades   351 | net    0.80% | PF  1.34 | +windows  48% | REJECT
     60 bps | windows  40 | trades   350 | net    0.76% | PF  1.32 | +windows  45% | REJECT  <-- GATE
     65 bps | windows  40 | trades   337 | net    0.71% | PF  1.30 | +windows  45% | REJECT
     70 bps | windows  40 | trades   334 | net    0.67% | PF  1.27 | +windows  42% | REJECT
     80 bps | windows  40 | trades   334 | net    0.57% | PF  1.23 | +windows  42% | REJECT
     90 bps | windows  40 | trades   334 | net    0.47% | PF  1.18 | +windows  42% | REJECT
    100 bps | windows  40 | trades   328 | net    0.42% | PF  1.16 | +windows  45% | REJECT
    120 bps | windows  40 | trades   318 | net    0.29% | PF  1.10 | +windows  45% | REJECT
    150 bps | windows  40 | trades   300 | net    0.03% | PF  1.01 | +windows  45% | REJECT
  breakeven: 150 bps
  median eligible combos/window: 18.0 (of 18)
  exit reasons @ gate: {'stop': 168, 'take_profit': 105, 'time_cap': 59, 'end_of_data': 18}
  end_of_data share: 5.1%
  baseline combo selected in 0/40 windows
  positive windows, full record: 45% over 40 windows
  positive windows, 2022+ only: 35% over 17 windows (Phase 1 measured 43% over 14)
  breakers[live 3%/3-streak]: kept 9/350 (97% blocked) | first halt 2016-10-19T12:00:00+00:00 | 3 consecutive losses | PF kept 0.83
  breakers[daily-loss only]: kept 350/350 (0% blocked) | first halt never | no trip | PF kept 1.32
  PHASE GATE: PROMOTE - breakeven 150 bps reaches the 60 bps gate
  PROMOTION GATE: REJECT - only 45% of windows positive (need >= 50%)
```

Both validity guards pass: median eligible combos **18.0 of 18** (no selection starvation) and
`end_of_data` truncation **5.1%** against the 15% ceiling. The baseline combo (1.5 / 3.0 / 48) was in
the grid and was selected in **0 of 40** windows — the same result Phase 1 reported over 14.

Selection concentrated on wide take-profits and long holds: `take_profit_atr_mult` 9.0 in **28 of 40**
windows and 6.0 in 9 more (3.0 in only 3); `max_hold_bars` 120 in **28 of 40**; `stop_atr_mult` 3.5 in
21 and 2.5 in 17, with the baseline 1.5 in only 2. This reproduces Phase 1's finding that take-profit
width is the operative lever.

### `ema-4h` ETH/USD — deep, 37 out-of-sample quarters

```
=== ema-4h ETH/USD 4h deep: 22338 bars 2016-05-18 00:00:00+00:00 -> 2026-08-01 04:00:00+00:00 ===
      0 bps | windows  37 | trades   312 | net    1.64% | PF  1.57 | +windows  70% | PROMOTE
     10 bps | windows  37 | trades   312 | net    1.54% | PF  1.52 | +windows  70% | PROMOTE
     25 bps | windows  37 | trades   309 | net    1.40% | PF  1.46 | +windows  70% | PROMOTE
     50 bps | windows  37 | trades   315 | net    1.13% | PF  1.35 | +windows  62% | PROMOTE
     55 bps | windows  37 | trades   315 | net    1.08% | PF  1.33 | +windows  62% | PROMOTE
     60 bps | windows  37 | trades   312 | net    1.06% | PF  1.32 | +windows  59% | PROMOTE  <-- GATE
     65 bps | windows  37 | trades   304 | net    1.04% | PF  1.32 | +windows  59% | PROMOTE
     70 bps | windows  37 | trades   303 | net    0.96% | PF  1.29 | +windows  59% | PROMOTE
     80 bps | windows  37 | trades   299 | net    0.88% | PF  1.26 | +windows  57% | PROMOTE
     90 bps | windows  37 | trades   297 | net    0.80% | PF  1.23 | +windows  54% | PROMOTE
    100 bps | windows  37 | trades   290 | net    0.81% | PF  1.22 | +windows  54% | PROMOTE
    120 bps | windows  37 | trades   284 | net    0.63% | PF  1.17 | +windows  54% | PROMOTE
    150 bps | windows  37 | trades   284 | net    0.33% | PF  1.08 | +windows  51% | REJECT
  breakeven: 150 bps
  median eligible combos/window: 18.0 (of 18)
  exit reasons @ gate: {'take_profit': 85, 'stop': 168, 'time_cap': 37, 'end_of_data': 22}
  end_of_data share: 7.1%
  baseline combo selected in 0/37 windows
  positive windows, full record: 59% over 37 windows
  positive windows, 2022+ only: 44% over 18 windows (Phase 1 measured 43% over 14)
  breakers[live 3%/3-streak]: kept 10/312 (97% blocked) | first halt 2017-06-21T16:00:00+00:00 | 3 consecutive losses | PF kept 3.15
  breakers[daily-loss only]: kept 312/312 (0% blocked) | first halt never | no trip | PF kept 1.32
  PHASE GATE: PROMOTE - breakeven 150 bps reaches the 60 bps gate
  PROMOTION GATE: PROMOTE - passed all walk-forward criteria
```

Validity guards pass identically: **18.0 of 18** eligible combos, `end_of_data` **7.1%** against the
15% ceiling. Baseline combo selected in **0 of 37** windows.

ETH clears the promotion gate at every cost tier from 0 through 120 bps, and only fails at 150 —
which is where the cost ladder ends and where PF has fallen to 1.08.

Selection is more concentrated than BTC's: `take_profit_atr_mult` 9.0 in **31 of 37** windows,
`max_hold_bars` 120 in **26 of 37**, `stop_atr_mult` 3.5 in 24. The two symbols agree on which corner
of the grid works.

---

## Was 36–43% noise?

**Pre-registered bands, fixed in the plan before the run:**

| deep positive-window fraction | reading |
|---|---|
| ≥ 50% (and PF ≥ 1.10, net > 0, ≥ 30 trades) | promotion gate PASSES — Phase 1's shortfall was small-sample noise |
| 43–50% | consistent with Phase 1; the edge is real but genuinely sub-threshold |
| < 43% | the inconsistency is real, not sample noise; the exit-geometry track closes |

**The two symbols land in different bands, and the bands are not re-drawn to hide that.**

- **ETH/USD: 59% — the ≥50% band.** Phase 1's shortfall on ETH was small-sample noise. On 37 quarters
  the configuration clears every promotion condition: PF 1.32 ≥ 1.10, net +1.06% > 0, 312 trades ≥ 30,
  59% ≥ 50%.
- **BTC/USD: 45% — the 43–50% band.** The edge is real (PF 1.32, breakeven 150 bps, 40 quarters) but
  genuinely sub-threshold on consistency. Tripling the sample did not move BTC across the line; it
  moved it from 43% over 14 windows to 45% over 40, which is the same answer with far more confidence
  behind it. This is *not* the "<43%, close the track" outcome, but it is not a pass either.

Neither symbol's reading is INCONCLUSIVE: `median_eligible_combos` is 18.0 (bar: ≥ 3) and
`end_of_data` is 5.1%/7.1% (ceiling: 15%) on both, so `phase_gate_verdict` returns PROMOTE for both.

---

## Does 2022+ reproduce Phase 1?

The deep record restricted to Phase 1's own window, which separates "more history changed the answer"
from "a different venue changed the answer":

| symbol | deep, 2022+ sub-record | Phase 1 | full deep record |
|---|---|---|---|
| BTC/USD | 35% over 17 windows | 43% over 14 | 45% over 40 |
| ETH/USD | 44% over 18 windows | 43% over 14 | 59% over 37 |

**ETH reproduces Phase 1 almost exactly** (44% vs 43%), so its jump to 59% on the full record is
attributable to history, not to the venue or resolution change. That is the clean case.

**BTC's sub-record reads 35% against Phase 1's 43%** — an 8-point gap over a comparable number of
windows. Some of this is the sub-record spanning 17 windows rather than 14, and some is the
USD-vs-USDT venue difference, which the continuity check bounds at ~3.7 bps median but does not
eliminate at the level of individual window outcomes. **BTC's full-record claims should therefore be
read with that qualification**: the deep record and Phase 1 agree on direction and magnitude, but
BTC's per-window outcomes are not identically reproducible across the two archives.

---

## Do the live breakers permit this?

**No. This dominates everything above.**

`run_backtest_fast` applies no circuit breakers at all — its own docstring says so
(`lab/strategy_backtest.py:9-12`) — so every result in this project, Phase 1 included, has described
a strategy with its risk controls switched off. `lab/breakers.py` replays them post-hoc for the first
time.

| symbol | first halt | reason | kept | blocked | PF of kept |
|---|---|---|---|---|---|
| BTC/USD | 2016-10-19T12:00:00+00:00 | 3 consecutive losses | 9 / 350 | **97%** | 0.83 |
| ETH/USD | 2017-06-21T16:00:00+00:00 | 3 consecutive losses | 10 / 312 | **97%** | 3.15 |

**The binding constraint is the 3-consecutive-loss streak limit, not the 3% daily loss limit.** With
`max_consecutive_losses` raised out of reach, the daily-loss breaker **never trips on either symbol**
across the entire 10–11 year record, and the full 350 / 312 trade record survives at PF 1.32. The
widened stops (2.5–3.5× ATR) that make this edge work do not produce large enough single-day realized
losses to reach 3% of equity — but they do produce losing streaks, and the selected geometry stops out
often (168 stops on each symbol at the gate, the largest single exit reason).

The halt is terminal because `RiskManager` never clears `kill_switch_active`: `start_day` resets the
daily counters but not the switch, and only an explicit manual resume (`service.py:106`) turns it off.
So the strategy stops in year one of an eleven-year record and never restarts. **The headline
positive-window fractions — including ETH's 59% PROMOTE — are not realisable by the live strategy as
currently configured.** The `PF kept` figures (0.83 and 3.15) are computed on 9 and 10 trades and
should not be read as estimates of anything.

**Three approximations bound this measurement** (from `lab/breakers.py`'s docstring, repeated so the
number is read correctly):

1. Suppressing an entry cannot create trades. A real strategy freed of a blocked position might have
   entered somewhere this record never saw, so the surviving record is a **lower bound** on activity,
   not an exact re-simulation.
2. A multi-day hold realises its P&L on its exit day, which is the day the live loop's own tick has
   already rolled to; the new day therefore opens at the pre-trade equity.
3. `cooldown_minutes` (45) is not modelled: it is shorter than one 4h bar, so it can never block the
   following entry at this resolution.

None of these approximations plausibly rescue the result. A 3-loss streak inside 350 trades over
eleven years is close to certain under any sequencing, and the replay confirms it happens within
roughly fifteen months on both symbols.

---

## Decision

**The promotion gate passes on `ema-4h` ETH/USD and fails on `ema-4h` BTC/USD — and neither is
deployable without a change to the circuit-breaker configuration.**

What Phase 2 settled:

- Phase 1's 36–43% was **noise on ETH** (59% over 37 quarters) and **a real sub-threshold reading on
  BTC** (45% over 40 quarters). The question Phase 2 existed to answer is answered, per symbol.
- The exit-geometry lever is larger and far more cost-robust than Phase 1 could measure: breakeven
  **150 bps** on both symbols against a 60 bps cost, on 2.5–3.5× the trade count.
- The baseline exit geometry (1.5 / 3.0 / 48) was selected in **0 of 77** windows across both symbols.
  It is not a defensible default and should not survive as one.

**The next action is not a promotion.** It is the breaker question, which is now the binding
constraint and which no prior study measured: `max_consecutive_losses=3` is incompatible with an exit
geometry whose largest single exit reason is the stop (168 of 350 exits on BTC, 168 of 312 on ETH —
roughly half). A stop-heavy profile at that rate will hit a 3-loss streak with near certainty, and the
current kill switch treats that as terminal rather than as a pause.

That is a **live-strategy risk-configuration question, not a research question**, and it should be
specified deliberately rather than tuned to make this result pass. Two distinct things are entangled
in it and want separating: the streak threshold itself, and the fact that a trip never auto-clears.
Note also that no such change may be reverse-engineered from these numbers without re-opening the same
hindsight problem the frozen gate exists to prevent.

**Not re-opened:** the 6 TA primitives (2026-06-22), funding mean reversion, and signal-parameter
grids. Signal parameters remain frozen.

**The live bot is untouched.** All Phase 2 code is research-only under `lab/`; no `src/` behaviour
changed, and the running container remains the Kronos-only paper trader.

---

## Secondary arm — daily resolution

**This arm asks a different question from everything above.** It is spec §6's literal daily study,
and it tests **whether an even longer horizon amortises the fixed 60 bps further** — daily ATR is
several times wider than 4h ATR, so a fixed round-trip cost is a much smaller fraction of the move
captured. It is **not** the consistency test; Phase 1's consistency question is answered by the 4h
study above. At 1d a 90-day test window carries on the order of one or two trades, which makes its
per-window statistic *noisier* than the 14-window record Phase 1 produced — which is exactly why the
primary study stayed at 4h.

**Two adaptations, both pre-registered in the plan before the run:**

1. **Hold levels were rescaled to the calendar equivalents of the 4h grid** — 48 bars at 4h is 8 days,
   120 bars is 20 days, so `max_hold_bars ∈ {8, 20}`. Carrying 48 and 120 over as bar counts would
   have meant 48- and 120-*day* holds against a 90-day test window, forcing `end_of_data` truncation
   past the 15% validity ceiling by construction. Stop and take-profit multiples are unchanged from
   Phase 1, so the grid is still 18 combos.
2. **`train_days` was selected by `select_train_days` from a probe of eligibility counts only** — how
   many grid combos clear the untouchable `min_train_trades=20`. No profit factor, net return or
   window fraction enters the choice, so it cannot import hindsight. The rule takes the smallest
   candidate whose median eligible count reaches 3.

### Eligibility probe and selection

| train_days | BTC windows | BTC median eligible (of 18) | ETH windows | ETH median eligible (of 18) |
|---|---|---|---|---|
| 365 | 33 | **13.0** | 28 | **11.0** |
| 730 | 36 | 18.0 | 33 | 18.0 |
| 1095 | 32 | 18.0 | 29 | 18.0 |
| 1460 | 28 | 18.0 | 25 | 18.0 |

**Selected `train_days=365` for both symbols** — the smallest candidate clearing the eligibility bar,
per the pre-registered rule. Neither symbol was INCONCLUSIVE: every candidate cleared the bar of 3,
so the rule reduced to its tie-break, which is "smallest".

### `ema-1d` BTC/USD

```
=== ema-1d BTC/USD: 4031 bars 2015-07-20 00:00:00+00:00 -> 2026-08-01 00:00:00+00:00 ===
      0 bps | windows  33 | trades   168 | net    1.74% | PF  1.61 | +windows  48% | REJECT
     10 bps | windows  33 | trades   167 | net    1.71% | PF  1.57 | +windows  48% | REJECT
     25 bps | windows  33 | trades   167 | net    1.56% | PF  1.51 | +windows  42% | REJECT
     50 bps | windows  33 | trades   167 | net    1.31% | PF  1.41 | +windows  33% | REJECT
     55 bps | windows  33 | trades   165 | net    1.29% | PF  1.41 | +windows  33% | REJECT
     60 bps | windows  33 | trades   165 | net    1.24% | PF  1.39 | +windows  33% | REJECT  <-- GATE
     65 bps | windows  33 | trades   165 | net    1.19% | PF  1.37 | +windows  33% | REJECT
     70 bps | windows  33 | trades   165 | net    1.14% | PF  1.35 | +windows  33% | REJECT
     80 bps | windows  33 | trades   165 | net    1.04% | PF  1.32 | +windows  33% | REJECT
     90 bps | windows  33 | trades   171 | net    0.76% | PF  1.22 | +windows  33% | REJECT
    100 bps | windows  33 | trades   171 | net    0.66% | PF  1.19 | +windows  33% | REJECT
    120 bps | windows  33 | trades   167 | net    0.48% | PF  1.13 | +windows  33% | REJECT
    150 bps | windows  33 | trades   167 | net    0.30% | PF  1.08 | +windows  33% | REJECT
  breakeven: 150 bps
  median eligible combos/window: 13.0 (of 18)
  exit reasons @ gate: {'time_cap': 87, 'stop': 50, 'end_of_data': 16, 'take_profit': 12}
  end_of_data share: 9.7%
  breakers[live 3%/3-streak]: kept 3/165 (98% blocked) | first halt 2016-08-02T00:00:00+00:00 | 3 consecutive losses | PF kept 0.00
  PHASE GATE: PROMOTE - breakeven 150 bps reaches the 60 bps gate
  PROMOTION GATE: REJECT - only 33% of windows positive (need >= 50%)
```

### `ema-1d` ETH/USD

```
=== ema-1d ETH/USD: 3726 bars 2016-05-18 00:00:00+00:00 -> 2026-08-01 00:00:00+00:00 ===
      0 bps | windows  28 | trades   143 | net    2.68% | PF  1.64 | +windows  46% | REJECT
     10 bps | windows  28 | trades   143 | net    2.57% | PF  1.61 | +windows  46% | REJECT
     25 bps | windows  28 | trades   143 | net    2.42% | PF  1.56 | +windows  46% | REJECT
     50 bps | windows  28 | trades   140 | net    2.23% | PF  1.50 | +windows  46% | REJECT
     55 bps | windows  28 | trades   139 | net    2.22% | PF  1.50 | +windows  46% | REJECT
     60 bps | windows  28 | trades   139 | net    2.17% | PF  1.49 | +windows  46% | REJECT  <-- GATE
     65 bps | windows  28 | trades   139 | net    2.12% | PF  1.48 | +windows  46% | REJECT
     70 bps | windows  28 | trades   139 | net    2.06% | PF  1.46 | +windows  46% | REJECT
     80 bps | windows  28 | trades   139 | net    1.96% | PF  1.43 | +windows  46% | REJECT
     90 bps | windows  28 | trades   139 | net    1.82% | PF  1.40 | +windows  46% | REJECT
    100 bps | windows  28 | trades   139 | net    1.71% | PF  1.37 | +windows  43% | REJECT
    120 bps | windows  28 | trades   136 | net    1.72% | PF  1.36 | +windows  43% | REJECT
    150 bps | windows  28 | trades   136 | net    1.41% | PF  1.29 | +windows  43% | REJECT
  breakeven: 150 bps
  median eligible combos/window: 11.0 (of 18)
  exit reasons @ gate: {'take_profit': 21, 'stop': 34, 'time_cap': 70, 'end_of_data': 14}
  end_of_data share: 10.1%
  breakers[live 3%/3-streak]: kept 11/139 (92% blocked) | first halt 2017-06-30T00:00:00+00:00 | 3 consecutive losses | PF kept 1.60
  PHASE GATE: PROMOTE - breakeven 150 bps reaches the 60 bps gate
  PROMOTION GATE: REJECT - only 46% of windows positive (need >= 50%)
```

### What the daily arm shows

**Cost amortisation does improve at the longer horizon — that part of the hypothesis holds.** At the
60 bps gate the daily arm posts *higher* profit factor and *much* higher net return per window than
the 4h study on both symbols:

| | 4h PF @ 60 bps | 1d PF @ 60 bps | 4h net | 1d net |
|---|---|---|---|---|
| BTC/USD | 1.32 | **1.39** | +0.76% | **+1.24%** |
| ETH/USD | 1.32 | **1.49** | +1.06% | **+2.17%** |

Cost erodes the daily edge more slowly too: ETH's PF falls only 1.64 → 1.49 across 0–60 bps at 1d,
against 1.57 → 1.32 at 4h. Wider daily ATR does make the fixed 60 bps a smaller fraction of the move.

**But both symbols REJECT, and on the same condition as BTC's 4h result — window consistency.** BTC
posts 33% positive windows and ETH 46%, against the 50% requirement. This is the predicted weakness
of the arm rather than a surprise: 165 and 139 trades spread over 33 and 28 windows is roughly 5 trades
per window, so per-window outcomes are dominated by a handful of trades each. The arm was run as a
cost question and it answered the cost question; its window statistic is too thin to overturn the 4h
study's, in either direction.

Both remain valid runs by the pre-registered guards — `end_of_data` 9.7% and 10.1% against the 15%
ceiling, median eligible 13.0 and 11.0 against the bar of 3 — so `phase_gate_verdict` returns PROMOTE
on breakeven for both, and the REJECT is a genuine promotion-gate outcome, not an untestable one.

Exit composition shifts as expected with the rescaled holds: `time_cap` becomes the largest exit
reason at 1d (87 of 165 on BTC, 70 of 139 on ETH), where `stop` was largest at 4h. The 8- and 20-day
caps bind more often than daily stops do.

**The breakers halt the daily arm too**, and earlier: first trip 2016-08-02 on BTC and 2017-06-30 on
ETH, blocking 98% and 92% of trades on the same 3-consecutive-loss rule. BTC's `PF kept 0.00` is
computed on 3 surviving trades and means only that none of them won. The breaker finding is the same
across all four configurations in this study.
