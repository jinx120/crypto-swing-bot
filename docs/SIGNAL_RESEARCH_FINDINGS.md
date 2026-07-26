# Signal research findings — walk-forward validation

**Date:** 2026-07-26
**Spec:** `docs/superpowers/specs/2026-07-22-thermostat-rebuild-design.md` §6, §8 items 6–7
**Plan:** `docs/superpowers/plans/2026-07-26-signal-research-walk-forward.md`
**Verdict:** **No signal passed the 60 bps gate.** All three candidates (4h EMA trend, funding
mean reversion, Coinbase-premium flow) REJECT at the live cost tier, in every overlay and
standalone variant tested. The live bot stays Kronos-only and Phase 5 is not executed.

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

Parameter selection uses profit factor on the training slice **at the same cost tier the
verdict is graded at**, so no combination is chosen on gross performance and then graded net.
Grids were fixed before the runs and were not widened afterwards.

## Data

| series | source | granularity | coverage |
|---|---|---|---|
| BTC/USD, ETH/USD OHLCV | Coinbase via `swingbot.backfill_cli` | 15m → resampled 4h | 2022-01-01 00:00Z → 2026-07-26 16:00Z, 10,006 4h bars (from 159,476 / 159,047 15m bars) |
| `funding_8h` | Hyperliquid `BTC/USDC:USDC` via ccxt | hourly → trailing 8h sum | 2023-05-14 08:00Z → 2026-07-26 19:00Z, 27,517 rows |
| `cb_premium` | Coinbase BTC/USD vs OKX BTC/USDT | 4h | 2022-01-01 00:00Z → 2026-07-26 16:00Z, 10,006 rows |

Sources rejected during this work, and why: Binance HTTP 451 (geo-block);
binance.us spot-only, no perpetuals so no funding rates; Bybit CloudFront 403;
OKX funding history capped at ~97 days; Glassnode/CryptoQuant exchange net flow
is paid-tier only, which is why spec §6c's on-chain metric was substituted with
the Coinbase premium (approved 2026-07-26).

## 6a — 4h EMA trend

27-combo grid (fast 8/13/21 × slow 34/55/89 × entry threshold 0.50/0.65/0.80),
365-day training windows, 90-day test windows, 14 out-of-sample quarters.

```
=== BTC/USD 4h: 10006 bars 2022-01-01 00:00:00+00:00 -> 2026-07-26 16:00:00+00:00 ===
    0 bps | windows 14 | trades  317 | net    0.34% | PF  1.28 | +windows   64% | PROMOTE
   10 bps | windows 14 | trades  317 | net    0.24% | PF  1.19 | +windows   50% | PROMOTE
   25 bps | windows 14 | trades  317 | net    0.09% | PF  1.07 | +windows   50% | REJECT
   60 bps | windows 14 | trades  317 | net   -0.26% | PF  0.84 | +windows   21% | REJECT  <-- GATE

=== ETH/USD 4h: 10006 bars 2022-01-01 00:00:00+00:00 -> 2026-07-26 16:00:00+00:00 ===
    0 bps | windows 14 | trades  300 | net    0.18% | PF  1.10 | +windows   50% | PROMOTE
   10 bps | windows 14 | trades  300 | net    0.08% | PF  1.04 | +windows   50% | REJECT
   25 bps | windows 14 | trades  300 | net   -0.07% | PF  0.96 | +windows   36% | REJECT
   60 bps | windows 14 | trades  300 | net   -0.42% | PF  0.79 | +windows   29% | REJECT  <-- GATE
```

**Verdict: REJECT.**
- BTC/USD: `net return -0.26% is not positive; profit factor 0.84 below 1.10; only 21% of windows positive (need >= 50%)`
- ETH/USD: `net return -0.42% is not positive; profit factor 0.79 below 1.10; only 29% of windows positive (need >= 50%)`

The signal has a genuine gross edge (BTC PF 1.28 at zero cost) that walk-forward selection
reproduces rather than destroys — it simply does not survive being charged. It crosses from
PROMOTE to REJECT between 10 and 25 bps on both symbols. This confirms the 2026-06-22
in-sample estimate (PF 1.17 gross, breakeven ~25 bps) under honest out-of-sample selection.

Window-by-window the chosen parameters are unstable, which is corroborating evidence that
what is being fit is largely noise: BTC drifts across `fast` 8→21 and `slow` 34→89 between
quarters rather than settling.

Kronos confirmation: **not re-tested this session** — the cached 4h forecasts
(`/tmp/swingbot-bt/k_*_4h.csv`) were lost with `/tmp` on the host reboot, and regenerating
them costs ~32 min of GPU inference per symbol. The 2026-06-22 GPU finding stands:
EMA+Kronos is within noise of EMA-core (n 369 vs 370 on BTC), so the confluence term is
inert. No Kronos result is claimed for this run.

## 6b — Funding-rate mean reversion

12-combo grid (high_thresh 0.0003/0.0005/0.0010 × low_thresh −0.0001/−0.0005 × entry
threshold 0.50/0.65). **270-day** training windows — funding history starts 2023-05-14, so
365-day windows would leave too few out-of-sample quarters to judge consistency. 9 quarters.

```
funding_8h: 27517 rows 2023-05-14 08:00:00+00:00 -> 2026-07-26 19:00:00+00:00

=== BTC/USD 4h: 7016 bars from 2023-05-14 08:00:00+00:00 ===
  -- overlay --
      0 bps | windows  9 | trades  205 | net    0.19% | PF  1.15 | +windows   67% | PROMOTE
     10 bps | windows  9 | trades  205 | net    0.09% | PF  1.07 | +windows   44% | REJECT
     25 bps | windows  9 | trades  205 | net   -0.05% | PF  0.96 | +windows   44% | REJECT
     60 bps | windows  9 | trades  205 | net   -0.40% | PF  0.75 | +windows    0% | REJECT  <-- GATE
  -- standalone --
      0 bps | windows  9 | trades  172 | net    0.33% | PF  1.28 | +windows   67% | PROMOTE
     10 bps | windows  9 | trades  172 | net    0.23% | PF  1.19 | +windows   56% | PROMOTE
     25 bps | windows  9 | trades  172 | net    0.08% | PF  1.06 | +windows   44% | REJECT
     60 bps | windows  9 | trades  172 | net   -0.27% | PF  0.83 | +windows   22% | REJECT  <-- GATE

=== ETH/USD 4h: 7016 bars from 2023-05-14 08:00:00+00:00 ===
  -- overlay --
      0 bps | windows  9 | trades  178 | net    0.16% | PF  1.09 | +windows   67% | REJECT
     10 bps | windows  9 | trades  178 | net    0.06% | PF  1.03 | +windows   56% | REJECT
     25 bps | windows  9 | trades  178 | net   -0.09% | PF  0.96 | +windows   33% | REJECT
     60 bps | windows  9 | trades  177 | net   -0.42% | PF  0.81 | +windows   33% | REJECT  <-- GATE
  -- standalone --
      0 bps | windows  9 | trades  196 | net    0.35% | PF  1.21 | +windows   67% | PROMOTE
     10 bps | windows  9 | trades  196 | net    0.25% | PF  1.15 | +windows   67% | PROMOTE
     25 bps | windows  9 | trades  196 | net    0.10% | PF  1.06 | +windows   67% | REJECT
     60 bps | windows  9 | trades  196 | net   -0.24% | PF  0.88 | +windows   33% | REJECT  <-- GATE
```

**Verdict: REJECT** (all four variants).
- BTC overlay: `net return -0.40% is not positive; profit factor 0.75 below 1.10; only 0% of windows positive (need >= 50%)`
- BTC standalone: `net return -0.27% is not positive; profit factor 0.83 below 1.10; only 22% of windows positive (need >= 50%)`
- ETH overlay: `net return -0.42% is not positive; profit factor 0.81 below 1.10; only 33% of windows positive (need >= 50%)`
- ETH standalone: `net return -0.24% is not positive; profit factor 0.88 below 1.10; only 33% of windows positive (need >= 50%)`

Two things worth recording. First, the **overlay is worse than the standalone at every cost
tier on BTC** — blending funding into the EMA entry does not filter out the losing trend
trades, it just perturbs which ones get taken; at the gate the overlay posts 0% positive
windows, the worst result in the study. Second, the standalone variant is long-only "buy when
perps are crowded short", and it does carry a gross edge (BTC PF 1.28, ETH PF 1.21) that
survives 10 bps on both symbols — but the bot trades Alpaca spot and cannot short, so the
half of the hypothesis that funding is most informative about is untradeable here anyway.

## 6c substitute — Coinbase premium flow

18-combo grid (lookback 180/360/540 4h bars = 30/60/90d × band 1.5/2.0/2.5 std dev × entry
threshold 0.50/0.65), 365-day training windows, 14 quarters.

```
cb_premium: 10006 rows 2022-01-01 00:00:00+00:00 -> 2026-07-26 16:00:00+00:00

=== BTC/USD 4h: 10006 bars from 2022-01-01 00:00:00+00:00 ===
  -- overlay --
      0 bps | windows 14 | trades  325 | net    0.30% | PF  1.25 | +windows   64% | PROMOTE
     10 bps | windows 14 | trades  325 | net    0.21% | PF  1.16 | +windows   64% | PROMOTE
     25 bps | windows 14 | trades  325 | net    0.05% | PF  1.04 | +windows   36% | REJECT
     60 bps | windows 14 | trades  325 | net   -0.29% | PF  0.81 | +windows   29% | REJECT  <-- GATE
  -- standalone --
      0 bps | windows 14 | trades  300 | net    0.46% | PF  1.39 | +windows   71% | PROMOTE
     10 bps | windows 14 | trades  301 | net    0.36% | PF  1.30 | +windows   57% | PROMOTE
     25 bps | windows 14 | trades  303 | net    0.20% | PF  1.15 | +windows   50% | PROMOTE
     60 bps | windows 14 | trades  316 | net   -0.19% | PF  0.88 | +windows   29% | REJECT  <-- GATE

=== ETH/USD 4h: 10006 bars from 2022-01-01 00:00:00+00:00 ===
  -- overlay --
      0 bps | windows 14 | trades  281 | net    0.20% | PF  1.12 | +windows   43% | REJECT
     10 bps | windows 14 | trades  283 | net    0.10% | PF  1.06 | +windows   43% | REJECT
     25 bps | windows 14 | trades  281 | net   -0.06% | PF  0.97 | +windows   43% | REJECT
     60 bps | windows 14 | trades  281 | net   -0.40% | PF  0.80 | +windows   14% | REJECT  <-- GATE
  -- standalone --
      0 bps | windows 14 | trades  288 | net    0.22% | PF  1.13 | +windows   64% | PROMOTE
     10 bps | windows 14 | trades  288 | net    0.11% | PF  1.07 | +windows   64% | REJECT
     25 bps | windows 14 | trades  287 | net   -0.03% | PF  0.98 | +windows   50% | REJECT
     60 bps | windows 14 | trades  282 | net   -0.37% | PF  0.82 | +windows   14% | REJECT  <-- GATE
```

**Verdict: REJECT** (all four variants).
- BTC overlay: `net return -0.29% is not positive; profit factor 0.81 below 1.10; only 29% of windows positive (need >= 50%)`
- BTC standalone: `net return -0.19% is not positive; profit factor 0.88 below 1.10; only 29% of windows positive (need >= 50%)`
- ETH overlay: `net return -0.40% is not positive; profit factor 0.80 below 1.10; only 14% of windows positive (need >= 50%)`
- ETH standalone: `net return -0.37% is not positive; profit factor 0.82 below 1.10; only 14% of windows positive (need >= 50%)`

**BTC premium-standalone is the strongest result anywhere in this study**: it is the only
configuration that still clears all four gate conditions at 25 bps (PF 1.15, +0.20%, 50% of
windows positive, 303 trades). It is also the cleanest confirmation of the study's central
finding — an edge that is real, out-of-sample, and still not worth deploying, because at the
cost we actually pay it turns into PF 0.88.

## Decision

**No signal proceeds to Phase 5.** Every candidate in every variant is REJECT at 60 bps: all
10 graded configurations are net negative at the gate (−0.19% to −0.42%), none reaches PF 1.10
(best 0.88), and none reaches 50% positive windows (best 33%).

Phase 5 (Tasks 14–16: regime-aware fusion, live series poller, promoted paper strategy) is
**not executed** and is marked N/A in the plan. The live bot stays Kronos-only, exactly as it
was before this work.

What this research bought, despite promoting nothing:
- A reusable, validated walk-forward harness with a coded promotion gate (`lab/walkforward.py`)
  — the machinery, not just the answer, so the next candidate signal is a runner away.
- Two real `Signal` classes (`FundingMeanReversionSignal`, `PremiumFlowSignal`) plus
  `MarketContext.extras` and a generic `SeriesStore`, all shipped and test-pinned to their
  vectorized research counterparts. They are registered but unused by any armed strategy.
- Keyless ingress for funding (Hyperliquid) and the Coinbase premium, with the paid/blocked
  alternatives documented so the dead ends are not re-explored.

The consistent shape across all three signals — healthy gross PF, collapse between 10 and
25 bps — says the constraint is not signal quality but the 60 bps round trip against a 4h
holding period. A future attempt should change that ratio (longer holds, fewer entries, or a
venue with lower fees) rather than search for another 4h entry signal.

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

`/tmp` is ephemeral: after a host reboot the backfill and both ingest steps must be re-run
(~8 min backfill, ~2 min funding, ~1 min premium) before any runner will produce output.
