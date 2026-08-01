# Hold-Period / Exit-Geometry Study — Design

**Date:** 2026-07-31
**Status:** approved, ready for planning
**Predecessor:** `docs/superpowers/specs/2026-07-26-signal-research-walk-forward.md` (executed;
verdict "promote nothing" — `docs/SIGNAL_RESEARCH_FINDINGS.md`)

---

## 1. Motivation

The signal-research track closed with every candidate REJECTing at the 60 bps promotion gate. All
10 graded configurations were net negative at the gate (−0.19% to −0.42%), best PF 0.88. The shape
was identical across three independent signals: healthy gross profit factor, collapse once cost is
charged.

That pattern says the binding constraint is **cost per round trip relative to the size of the move
captured**, not signal quality. Three ways to attack it were identified. This spec takes the one
that is cheapest to test and carries no new modelling assumptions: **change the holding period**, so
the same fixed cost is amortised over a larger move.

### 1.1 The specific gap this exploits

Exit geometry has **never been varied in any crypto-swing-bot study.** Both prior walk-forward
runners hold it constant:

```python
atr_period=14, bracket_mode="atr", stop_atr_mult=1.5, take_profit_atr_mult=3.0,
risk_per_trade=0.0075, max_hold_bars=48,
```

`lab/research_ema_4h.py:base_profile` and `lab/research_premium.py:standalone_profile` are identical
on every one of those fields. The 27-combo EMA grid varied `ema_trend.fast`, `ema_trend.slow`, and
`entry_threshold`; the 18-combo premium grid varied `premium_flow.lookback`, `premium_flow.band`,
and `entry_threshold`. **Neither grid contained a single exit parameter.**

So the prior studies did not test short holds and reject long ones — they tested exactly one exit
geometry and never asked the question. `max_hold_bars=48` at 4h is already an 8-day ceiling, and the
ATR brackets (1.5× stop / 3.0× TP) are multi-day-scale. The untested axis is not "hold longer than a
scalp" but **"is 1.5/3.0/48 anywhere near the right exit geometry for these signals at this cost?"**

### 1.2 Correcting the roadmap's framing

`docs/ROADMAP_STATUS.md` states candidates "collapse between 10 and 25 bps." That describes where
configs cross the **promotion** gate (PF 1.10), not where they cross **breakeven** (PF 1.0).
Interpolating the published cost tiers gives the actual breakeven costs:

| config | PF @ 25 bps | PF @ 60 bps | breakeven (PF = 1.0) |
|---|---|---|---|
| `ema-4h` — BTC/USD | 1.07 | 0.84 | ~36 bps |
| `ema-4h` — ETH/USD | 0.96 | 0.79 | ~18 bps |
| `premium-standalone` — BTC/USD | 1.15 | 0.88 | **~44 bps** |
| `premium-standalone` — ETH/USD | 0.98 | 0.82 | ~22 bps |

This matters directly for gate design: BTC premium-standalone already breaks even at ~44 bps with
no intervention, so any phase gate set below that would pass at baseline and measure nothing.

---

## 2. Hypothesis under test

> Widening exit geometry raises the breakeven round-trip cost enough that at least one signal
> reaches PF ≥ 1.0 at the 60 bps we actually pay.

Falsifiable, pre-registered, and gradeable by the existing harness.

---

## 3. Phase 1 — widened-exit probe

Runs against the **existing** 4h archive (Coinbase 15m from 2022-01-01, resampled). No new data
ingress beyond re-backfilling what `/tmp` lost. Cheap by design: if the lever is inert, we learn it
in one session and close the track.

### 3.1 Scope — 4 configurations

| label | signal | symbols |
|---|---|---|
| `ema-4h` | `ema_trend` | BTC/USD, ETH/USD |
| `premium-standalone` | `premium_flow` | BTC/USD, ETH/USD |

**Excluded, with reasons:**
- **Funding mean-reversion** — conceptually incompatible with a long hold (it bets on a snap-back;
  holding for days bets against the mechanism generating the signal). It was also the worst result
  in the study (BTC overlay: 0% positive windows) and its Hyperliquid history only starts
  2023-05-14, so its windows would not align with the other configs.
- **Premium overlay variants** — standalone beat overlay on both symbols at every cost tier
  (BTC: PF 1.15 vs 1.04 at 25 bps). Testing the dominated variant spends grid budget for nothing.
- **Kronos** — the 4h forecast cache died with `/tmp`; regenerating costs ~32 min GPU per symbol,
  and the 2026-06-22 finding (EMA+Kronos within noise of EMA-core, n 369 vs 370) says the confluence
  term is inert. Out of scope; no Kronos claim is made.

### 3.2 Frozen signal parameters

Signal parameters are pinned to each base profile's **declared defaults** — the values chosen a
priori, before any results existed:

- `ema-4h`: `fast 21`, `slow 55`, `band 0.001`, `entry_threshold 0.65`
- `premium-standalone`: `lookback 180`, `band 2.0`, `entry_threshold 0.65`

**Why declared defaults rather than "the most-selected combo":** `SIGNAL_RESEARCH_FINDINGS.md`
records that window-by-window selection was *unstable* — "BTC drifts across `fast` 8→21 and `slow`
34→89 between quarters rather than settling." There is no stable most-selected value to freeze at,
and choosing one after seeing results would import hindsight into a study whose entire worth rests
on not doing that.

### 3.3 The exit grid — 18 combinations

The **only** thing that varies:

| parameter | values | baseline |
|---|---|---|
| `stop_atr_mult` | 1.5, 2.5, 3.5 | 1.5 |
| `take_profit_atr_mult` | 3.0, 6.0, 9.0 | 3.0 |
| `max_hold_bars` | 48, 120 | 48 |

3 × 3 × 2 = 18 combos, deliberately coarser than the 27-combo signal grids it replaces.

**The baseline combo (1.5 / 3.0 / 48) is a grid member on purpose.** If walk-forward keeps selecting
it on the training slices, that is direct positive evidence the lever is inert — a stronger and
cleaner null than "the widened variant lost," because the harness was free to choose either.

### 3.4 Held fixed (documented limitation)

`risk_per_trade 0.0075`, `atr_period 14`, `regime_ma_period 200`,
`allowed_regimes (UPTREND, NEUTRAL)`, `cooldown_minutes 45`, `daily_loss_limit_pct 0.03`,
`max_consecutive_losses 3`.

The last two are circuit breakers that can bind *harder* at long holds, since a wider stop means a
larger per-trade loss against a fixed 3% daily limit. They are left fixed anyway: moving them would
mean two variables changing at once, and the study's value depends on clean attribution. This is
recorded as a known limitation of the result, not an oversight — if Phase 1 passes, breaker
interaction is the first thing Phase 2 should examine.

### 3.5 Walk-forward configuration — unchanged

`train_days=365`, `test_days=90`, `step_days=90`, `min_train_trades=20`, 14 out-of-sample quarters,
archive from 2022-01-01. Identical to the baseline run so the numbers are directly comparable.

---

## 4. Harness additions

Three additions, all in `lab/`. No `src/` behaviour changes, so
`tests/test_lab_signal_parity.py` must remain green untouched.

### 4.1 `breakeven_cost()`

Locates the round-trip cost at which PF crosses 1.0.

**Cost ladder:** `[0, 10, 25, 50, 55, 60, 65, 70, 80]` bps — 9 tiers, denser around the gate.
An even 5 bps sweep from 0 to 100 would be 21 tiers, and at 18 combos × 14 windows × 4
configurations that is ~22,000 backtests, roughly 14× the prior study's load. The gate only needs
breakeven resolved *near 60 bps*, so the ladder spends its resolution there (±5 bps across 50–70)
while retaining 0/10/25/60 so the numbers stay directly comparable to the published
`SIGNAL_RESEARCH_FINDINGS.md` tables.

**Definition (must be exact, since a noisy PF curve is not guaranteed monotone):** the largest swept
cost `c` such that PF ≥ 1.0 at `c` **and** at every swept tier below `c`. This is the first downward
crossing. It is deliberately *not* "the highest cost with PF ≥ 1.0", which a single noisy tier far
out on the curve could inflate.

Returns `None` when PF < 1.0 at 0 bps (the signal has no gross edge to charge against).

### 4.2 Grid-eligibility instrumentation

`walk_forward` already skips any combo with fewer than `min_train_trades` training trades. Longer
holds mean fewer trades per training window, and the filter culls precisely the combos that trade
least — so the surviving set skews toward whichever exits close positions fastest. Left
uninstrumented, a study designed to test long holds could quietly re-select for short ones and
report REJECT for the wrong reason.

- `WindowResult` gains `n_eligible_combos: int`
- `WalkForwardResult` exposes `median_eligible_combos`
- **Pre-registered rule:** median < 3 ⇒ the run reports **`INCONCLUSIVE`**, never `REJECT`.

`min_train_trades` itself is **not** relaxed. The guard distinguishes "the lever does not work" from
"we could not test the lever" without touching a threshold.

### 4.3 Exit-reason distribution

`Trade.exit_reason` already exists and is populated by the real `SimulatedBroker`, so this is
reporting only — no new exit plumbing. The enum is
`STOP | TAKE_PROFIT | TIME_CAP | END_OF_DATA`. Report the distribution per configuration.

Two things it buys:

**Mechanism, not just outcome.** If almost no trades terminate on `TIME_CAP`, the hold ceiling is
not binding and raising `max_hold_bars` further is pointless — better evidence than guessing at a
third level and worsening grid starvation.

**A truncation confound that scales with the manipulated variable.** `END_OF_DATA` fires when a
position is still open at the end of a test slice. Test windows are 90 days; `max_hold_bars=120` at
4h is 20 days. So the wider the hold, the larger the fraction of each window in which a newly
opened position cannot fully develop before being force-closed at the boundary. This biases long-hold
combos specifically — the exact thing under test — so it cannot be left unmeasured.

**Pre-registered rule:** report the `END_OF_DATA` share per config. If it exceeds **15%** of
out-of-sample trades for the config that clears the §5 gate, that config's result is reported as
**`INCONCLUSIVE`** rather than passing, because boundary truncation rather than exit geometry is
plausibly driving it. Phase 2 would then need a longer test window before the claim is trusted.

### 4.4 `Verdict.decision` gains a third value

Currently `"PROMOTE" | "REJECT"`. Becomes `"PROMOTE" | "REJECT" | "INCONCLUSIVE"`.

---

## 5. The phase gate — pre-registered

**Phase 2 proceeds if and only if, for at least one of the 4 configurations:**

1. `breakeven_cost >= 60 bps` (equivalently: PF ≥ 1.0 at the real 60 bps cost), **and**
2. `median_eligible_combos >= 3` (the run was not selection-starved), **and**
3. `END_OF_DATA` share ≤ 15% of out-of-sample trades (the result is not an artefact of
   test-window truncation — see §4.3).

Conditions 2 and 3 are not additional performance bars; they are validity conditions. A config
failing either is reported `INCONCLUSIVE`, not `REJECT`, because the study failed to test it
properly rather than the config failing to perform.

**Why 60 and not lower:** the best baseline breakeven is ~44 bps, so 60 cannot be cleared without a
genuine effect. **Why not the full promotion gate:** that additionally demands PF ≥ 1.10, net return
> 0, and ≥ 50% positive windows; on 14 thin windows with a reduced trade count, a real effect could
miss those on noise alone, and Phase 1 exists to decide whether to *invest further*, not whether to
deploy. The 60 bps promotion gate itself is untouched and still governs any actual promotion.

**If the gate does not pass:** Phase 2 is not executed, the track closes, and the finding is
recorded. That is an accepted outcome. The gate is not relaxed after seeing results, and the grid is
not widened after seeing results — the same discipline that made the previous REJECT trustworthy.

---

## 6. Phase 2 — deep daily study (conditional)

Executed only on a Phase 1 pass.

1. Backfill Coinbase **daily** OHLCV — BTC-USD from ~2015, ETH-USD from ~2016.
2. Re-run the winning configuration's exit grid at 1d resolution.
3. Grade at the unchanged 60 bps promotion gate.

At `train 365 / test 90 / step 90` over ~10.5 years this yields roughly **38 out-of-sample windows
spanning three market cycles** (2018 bear, 2020–21 bull, 2022 bear, 2023–25) versus the current 14
over one and a half. That increase in out-of-sample record is the real prize.

**Asymmetry to flag now:** the prize is not equal across configs. `ema-4h` is price-only, so
Coinbase daily reaches ~2015. `premium-standalone` needs OKX spot for the premium leg, which
paginates keyless only from 2022 — so if premium is what passes Phase 1, Phase 2 buys it far fewer
additional windows than EMA would get. Phase 2 scope must be re-checked against whichever config
actually passes.

---

## 7. Testing

| area | test |
|---|---|
| `breakeven_cost` | monotone curve crossing between tiers; crossing exactly on a tier; never crosses (PF ≥ 1.0 throughout); no gross edge (PF < 1.0 at 0 bps) ⇒ `None`; non-monotone curve takes the *first* downward crossing |
| eligibility | grid where every combo is filtered ⇒ `INCONCLUSIVE`, not `REJECT`; median computed across windows |
| exit reasons | distribution sums to trade count; covers all four `ExitReason` values; `END_OF_DATA` share > 15% ⇒ `INCONCLUSIVE` even when the breakeven condition passes |
| regression | `tests/test_lab_signal_parity.py` green and unmodified |
| gate | full backend pytest + ruff clean |

Docker rebuild + restart of `swingbot` per the standing rule, even though `lab/` is not packaged
into the image.

---

## 8. Non-goals

- The live bot is not touched. It stays the Kronos-only paper trader.
- The 60 bps promotion gate is not relaxed, and `min_train_trades` is not relaxed.
- No re-test of funding mean-reversion or Kronos.
- No widening of signal-parameter grids.
- No maker-order or venue-cost modelling (that is a separate avenue, deliberately deferred — an
  honest maker study requires a fill model first, because assuming limit orders fill is
  systematically optimistic through adverse selection).

---

## 9. Deliverable

`docs/HOLD_PERIOD_FINDINGS.md`, in the same format as `SIGNAL_RESEARCH_FINDINGS.md`: per-config
cost-tier tables, plus a breakeven column, the eligibility diagnostic, the exit-reason distribution,
the selected combo per window, and an explicit pass/fail statement against the §5 phase gate.

Plus an updated `docs/ROADMAP_STATUS.md`.
