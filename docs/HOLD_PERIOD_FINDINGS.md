# Exit-Geometry Walk-Forward Findings

**Date:** 2026-07-31
**Spec:** `docs/superpowers/specs/2026-07-31-hold-period-exit-geometry-design.md`
**Runner:** `lab/research_exit_geometry.py` · **Raw log:** `/tmp/exit-geometry-run.log`
**Predecessor:** `docs/SIGNAL_RESEARCH_FINDINGS.md` ("promote nothing", 2026-07-26)

---

## Summary

**The phase gate PASSES on all four configurations.** Exit geometry — the one axis no prior study
ever varied — moves the breakeven round-trip cost by **+46 to +68 bps**, from a baseline range of
18–44 bps to **70–90 bps**. Every configuration now survives the 60 bps cost we actually pay.

**The promotion gate still REJECTs all four**, and on a single condition: out-of-sample window
consistency. Three of the four now clear profit factor, net return, and trade count at 60 bps, and
fail only the "≥50% of windows positive" requirement (they land at 36–43%). This is a real,
large effect that is not yet consistent enough to deploy.

All backtests run through `run_backtest_fast`, bit-for-bit identical to production `run_backtest`,
so exits, sizing and broker are the real ones. Data: Coinbase 15m resampled to 4h, 2022-01-01
onward, 10,038 bars. `cb_premium` 10,038 rows.

---

## What was varied, and what was not

Both prior studies fixed exit geometry at `stop_atr_mult 1.5 / take_profit_atr_mult 3.0 /
max_hold_bars 48` and gridded only signal parameters. This run inverts that exactly:

- **Signal parameters frozen** at declared base-profile defaults (EMA `fast 21 / slow 55 /
  band 0.001 / threshold 0.65`; premium `lookback 180 / band 2.0 / threshold 0.65`). Chosen a
  priori, before any results existed — the prior study recorded window-by-window selection as
  unstable, so there is no stable "most-selected" value to freeze at without importing hindsight.
- **18-combo exit grid** is the only thing that moves: `stop_atr_mult` ∈ {1.5, 2.5, 3.5} ×
  `take_profit_atr_mult` ∈ {3.0, 6.0, 9.0} × `max_hold_bars` ∈ {48, 120}.
- Windows unchanged: train 365d / test 90d / step 90d, `min_train_trades=20`, 14 quarters.

The baseline combo (1.5 / 3.0 / 48) was deliberately included in the grid so the harness could
select it. **It was selected in 0 of 14 windows on every configuration.**

---

## Results

### 6d-a — `ema-4h` BTC/USD

```
=== ema-4h BTC/USD 4h: 10038 bars 2022-01-01 00:00:00+00:00 -> 2026-08-01 00:00:00+00:00 ===
      0 bps | windows 14 | trades  159 | net    0.75% | PF  1.49 | +windows  57% | PROMOTE
     10 bps | windows 14 | trades  159 | net    0.65% | PF  1.41 | +windows  57% | PROMOTE
     25 bps | windows 14 | trades  149 | net    0.51% | PF  1.30 | +windows  43% | REJECT
     50 bps | windows 14 | trades  145 | net    0.32% | PF  1.16 | +windows  43% | REJECT
     55 bps | windows 14 | trades  140 | net    0.34% | PF  1.17 | +windows  43% | REJECT
     60 bps | windows 14 | trades  128 | net    0.31% | PF  1.15 | +windows  43% | REJECT  <-- GATE
     65 bps | windows 14 | trades  125 | net    0.26% | PF  1.12 | +windows  43% | REJECT
     70 bps | windows 14 | trades  125 | net    0.21% | PF  1.10 | +windows  43% | REJECT
     80 bps | windows 14 | trades  125 | net    0.11% | PF  1.05 | +windows  43% | REJECT
     90 bps | windows 14 | trades  125 | net    0.01% | PF  1.00 | +windows  43% | REJECT
    100 bps | windows 14 | trades  125 | net   -0.09% | PF  0.96 | +windows  43% | REJECT
    120 bps | windows 14 | trades  125 | net   -0.29% | PF  0.88 | +windows  43% | REJECT
    150 bps | windows 14 | trades  125 | net   -0.60% | PF  0.77 | +windows  21% | REJECT
  breakeven: 90 bps
  median eligible combos/window: 18.0 (of 18)
  exit reasons @ gate: {'take_profit': 36, 'stop': 63, 'end_of_data': 10, 'time_cap': 19}
  end_of_data share: 7.8%
  baseline combo selected in 0/14 windows
  PHASE GATE: PROMOTE - breakeven 90 bps reaches the 60 bps gate
```

### 6d-b — `ema-4h` ETH/USD

```
=== ema-4h ETH/USD 4h: 10037 bars 2022-01-01 00:00:00+00:00 -> 2026-07-31 20:00:00+00:00 ===
      0 bps | windows 14 | trades  132 | net    0.71% | PF  1.31 | +windows  43% | REJECT
     10 bps | windows 14 | trades  132 | net    0.61% | PF  1.26 | +windows  43% | REJECT
     25 bps | windows 14 | trades  129 | net    0.57% | PF  1.24 | +windows  43% | REJECT
     50 bps | windows 14 | trades  129 | net    0.32% | PF  1.12 | +windows  29% | REJECT
     55 bps | windows 14 | trades  126 | net    0.31% | PF  1.12 | +windows  36% | REJECT
     60 bps | windows 14 | trades  124 | net    0.19% | PF  1.07 | +windows  36% | REJECT  <-- GATE
     65 bps | windows 14 | trades  124 | net    0.14% | PF  1.05 | +windows  36% | REJECT
     70 bps | windows 14 | trades  124 | net    0.09% | PF  1.03 | +windows  36% | REJECT
     80 bps | windows 14 | trades  124 | net   -0.01% | PF  1.00 | +windows  29% | REJECT
     90 bps | windows 14 | trades  121 | net   -0.10% | PF  0.97 | +windows  29% | REJECT
    100 bps | windows 14 | trades  121 | net   -0.20% | PF  0.94 | +windows  29% | REJECT
    120 bps | windows 14 | trades  115 | net   -0.32% | PF  0.90 | +windows  29% | REJECT
    150 bps | windows 14 | trades  104 | net   -0.49% | PF  0.86 | +windows  36% | REJECT
  breakeven: 70 bps
  median eligible combos/window: 18.0 (of 18)
  exit reasons @ gate: {'stop': 78, 'take_profit': 20, 'time_cap': 19, 'end_of_data': 7}
  end_of_data share: 5.6%
  baseline combo selected in 0/14 windows
  PHASE GATE: PROMOTE - breakeven 70 bps reaches the 60 bps gate
```

### 6d-c — `premium-standalone` BTC/USD

```
=== premium-standalone BTC/USD 4h: 10038 bars 2022-01-01 00:00:00+00:00 -> 2026-08-01 00:00:00+00:00 ===
      0 bps | windows 14 | trades  185 | net    0.73% | PF  1.50 | +windows  57% | PROMOTE
     10 bps | windows 14 | trades  181 | net    0.64% | PF  1.41 | +windows  57% | PROMOTE
     25 bps | windows 14 | trades  175 | net    0.55% | PF  1.33 | +windows  57% | PROMOTE
     50 bps | windows 14 | trades  167 | net    0.34% | PF  1.18 | +windows  43% | REJECT
     55 bps | windows 14 | trades  167 | net    0.29% | PF  1.15 | +windows  43% | REJECT
     60 bps | windows 14 | trades  167 | net    0.24% | PF  1.13 | +windows  43% | REJECT  <-- GATE
     65 bps | windows 14 | trades  151 | net    0.26% | PF  1.13 | +windows  43% | REJECT
     70 bps | windows 14 | trades  151 | net    0.21% | PF  1.10 | +windows  43% | REJECT
     80 bps | windows 14 | trades  151 | net    0.11% | PF  1.05 | +windows  43% | REJECT
     90 bps | windows 14 | trades  151 | net    0.01% | PF  1.00 | +windows  43% | REJECT
    100 bps | windows 14 | trades  148 | net   -0.09% | PF  0.96 | +windows  43% | REJECT
    120 bps | windows 14 | trades  148 | net   -0.29% | PF  0.88 | +windows  36% | REJECT
    150 bps | windows 14 | trades  146 | net   -0.65% | PF  0.75 | +windows  36% | REJECT
  breakeven: 90 bps
  median eligible combos/window: 18.0 (of 18)
  exit reasons @ gate: {'take_profit': 46, 'stop': 93, 'end_of_data': 9, 'time_cap': 19}
  end_of_data share: 5.4%
  baseline combo selected in 0/14 windows
  PHASE GATE: PROMOTE - breakeven 90 bps reaches the 60 bps gate
```

### 6d-d — `premium-standalone` ETH/USD

```
=== premium-standalone ETH/USD 4h: 10037 bars 2022-01-01 00:00:00+00:00 -> 2026-07-31 20:00:00+00:00 ===
      0 bps | windows 14 | trades  136 | net    0.78% | PF  1.37 | +windows  50% | PROMOTE
     10 bps | windows 14 | trades  136 | net    0.68% | PF  1.31 | +windows  50% | PROMOTE
     25 bps | windows 14 | trades  127 | net    0.70% | PF  1.30 | +windows  43% | REJECT
     50 bps | windows 14 | trades  123 | net    0.53% | PF  1.20 | +windows  43% | REJECT
     55 bps | windows 14 | trades  123 | net    0.48% | PF  1.18 | +windows  43% | REJECT
     60 bps | windows 14 | trades  123 | net    0.43% | PF  1.16 | +windows  43% | REJECT  <-- GATE
     65 bps | windows 14 | trades  121 | net    0.29% | PF  1.10 | +windows  43% | REJECT
     70 bps | windows 14 | trades  121 | net    0.24% | PF  1.08 | +windows  43% | REJECT
     80 bps | windows 14 | trades  121 | net    0.14% | PF  1.05 | +windows  43% | REJECT
     90 bps | windows 14 | trades  121 | net    0.04% | PF  1.01 | +windows  43% | REJECT
    100 bps | windows 14 | trades  121 | net   -0.06% | PF  0.98 | +windows  43% | REJECT
    120 bps | windows 14 | trades  115 | net   -0.40% | PF  0.87 | +windows  36% | REJECT
    150 bps | windows 14 | trades  112 | net   -0.66% | PF  0.80 | +windows  36% | REJECT
  breakeven: 90 bps
  median eligible combos/window: 18.0 (of 18)
  exit reasons @ gate: {'take_profit': 25, 'stop': 72, 'time_cap': 17, 'end_of_data': 9}
  end_of_data share: 7.3%
  baseline combo selected in 0/14 windows
  PHASE GATE: PROMOTE - breakeven 90 bps reaches the 60 bps gate
```

---

## Baseline comparison — the effect size

Prior breakevens are interpolated from the published cost tiers in
`SIGNAL_RESEARCH_FINDINGS.md`; new breakevens are measured directly on a 13-tier ladder.

| configuration | baseline breakeven | new breakeven | Δ | baseline PF @ 60 | new PF @ 60 |
|---|---|---|---|---|---|
| `ema-4h` BTC/USD | ~36 bps | **90 bps** | +54 | 0.84 | **1.15** |
| `ema-4h` ETH/USD | ~18 bps | **70 bps** | +52 | 0.79 | **1.07** |
| `premium-standalone` BTC/USD | ~44 bps | **90 bps** | +46 | 0.88 | **1.13** |
| `premium-standalone` ETH/USD | ~22 bps | **90 bps** | +68 | 0.82 | **1.16** |

Every configuration goes from net negative at 60 bps to net positive. The effect is consistent in
sign and magnitude across two independent signals and two symbols, which is the strongest argument
that it is real rather than a lucky draw on one series.

**The gross edge also improved**, so this is not purely cost amortisation. `ema-4h` BTC/USD at zero
cost went from PF 1.28 (317 trades) to PF 1.49 (159 trades): wider take-profits capture more of each
move, not merely fewer fees per unit of profit.

---

## Which exit parameter did the work?

Distribution of selected values across all 14 windows per configuration:

| configuration | `stop_atr_mult` | `take_profit_atr_mult` | `max_hold_bars` |
|---|---|---|---|
| `ema-4h` BTC/USD | 1.5:1 · 2.5:5 · **3.5:8** | 3.0:1 · 6.0:4 · **9.0:9** | 48:5 · **120:9** |
| `ema-4h` ETH/USD | 1.5:3 · 2.5:5 · **3.5:6** | 6.0:2 · **9.0:12** | 48:5 · **120:9** |
| `premium-standalone` BTC/USD | 1.5:5 · **2.5:6** · 3.5:3 | 3.0:1 · **6.0:7** · 9.0:6 | 48:5 · **120:9** |
| `premium-standalone` ETH/USD | 1.5:3 · 2.5:4 · **3.5:7** | 6.0:4 · **9.0:10** | 48:3 · **120:11** |

**Take-profit width is the operative lever.** The baseline 3.0× was selected in just **2 of 56**
window-selections across the whole study; 9.0× took 37 of 56. Hold length is second — 120 bars
(20 days) chosen 38 of 56 against 48 bars (8 days) at 18 of 56. Stop width is the weakest of the
three: 3.5× leads at 24 of 56, but 1.5× still survives in 12, and `premium-standalone` BTC/USD
actually prefers the *middle* value.

### Did the hold ceiling bind?

Yes, but it is not the main channel. `time_cap` accounts for 19/128 (14.8%), 19/124 (15.3%),
19/167 (11.4%) and 17/123 (13.8%) of out-of-sample trades at the gate. So roughly one trade in seven
is terminated by the hold ceiling rather than by a bracket. That is enough to matter but far less
than the take-profit effect, which is consistent with the parameter distributions above.

---

## Validity checks — both pre-registered guards passed

| configuration | median eligible combos (of 18) | `end_of_data` share |
|---|---|---|
| `ema-4h` BTC/USD | 18.0 | 7.8% |
| `ema-4h` ETH/USD | 18.0 | 5.6% |
| `premium-standalone` BTC/USD | 18.0 | 5.4% |
| `premium-standalone` ETH/USD | 18.0 | 7.3% |

**Selection starvation: did not occur.** The concern was that `min_train_trades=20` culls the combos
that trade least, so at long holds the surviving set would skew back toward fast-closing exits and
the study would quietly re-select for short holds. Every window had all 18 combos eligible, so
selection was never constrained. The guard was not needed, but it was necessary to know that.

**Truncation bias: within tolerance.** `end_of_data` — positions force-closed at a 90-day test
window boundary — runs 5.4–7.8%, comfortably under the 15% pre-registered ceiling. Since this bias
grows with hold length and hold length is the variable under test, a high share would have made the
result uninterpretable. It did not.

---

## Caveats — what this result does not establish

1. **Window consistency is the binding failure and it is not marginal.** At 60 bps the four configs
   post 43% / 36% / 43% / 43% positive windows against a 50% requirement. Aggregate profitability
   is carried by a minority of quarters. Three of four configs fail the promotion gate on this
   condition *alone* (`ema-4h` ETH/USD also misses PF 1.10, at 1.07).
2. **Fewer trades means a thinner record.** Trade counts roughly halved (317 → 159 on `ema-4h`
   BTC/USD at zero cost). PF 1.15 on 128 trades across 14 windows carries materially more
   uncertainty than PF 0.84 on 317 did.
3. **14 windows spanning one and a half market cycles.** The out-of-sample record covers 2023-01
   onward only. This is exactly the weakness Phase 2's deep daily history is designed to address.
4. **Circuit breakers were held fixed** at `daily_loss_limit_pct 0.03` and
   `max_consecutive_losses 3`. A wider stop means a larger per-trade loss against an unchanged daily
   limit, so the breakers may bind harder at the selected geometry than they did at baseline. This
   interaction is unmeasured and should be the first thing Phase 2 examines.
5. **`ema-4h` ETH/USD now REJECTs at 0 bps** (43% windows) where the prior study PROMOTEd it (50%).
   Not a contradiction — a different exit configuration produces a different set of trades and hence
   different window-level consistency — but it is a reminder that these consistency fractions are
   unstable at n=14.

---

## Decision

**The Phase 1 → Phase 2 gate PASSES.** All four configurations satisfy all three pre-registered
conditions: breakeven ≥ 60 bps (measured 70–90), median eligible combos ≥ 3 (measured 18.0), and
`end_of_data` share ≤ 15% (measured 5.4–7.8%).

**Phase 2 executes.** Per spec §6, that is the deep daily study: backfill Coinbase daily OHLCV
(BTC ~2015, ETH ~2016), re-run the exit grid at 1d resolution across roughly 38 out-of-sample
windows spanning three market cycles, and grade at the unchanged 60 bps promotion gate.

The specific question Phase 2 must answer is **not** whether the edge exists — this study is
reasonably convincing that widening exits raises breakeven well past the cost we pay. It is whether
the 36–43% positive-window fraction is small-sample noise or a real inconsistency. Fourteen windows
cannot distinguish those; thirty-eight across three cycles can.

**Spec §6 asymmetry, now decision-relevant:** `ema-4h` is price-only, so Coinbase daily reaches
~2015 and it gains the full window increase. `premium-standalone` needs OKX spot for the premium
leg, which paginates keyless only from 2022 — so it cannot gain much depth at all. Since both
signals passed, Phase 2 should lead with `ema-4h`, where the extra history actually exists.

**The live bot is untouched.** It remains the Kronos-only paper trader. No research code is wired
into it, and nothing here is a deployment recommendation — the promotion gate has not been cleared.
