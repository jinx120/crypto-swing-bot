# Strategy backtest findings — researched TA strategies vs 15m BTC/ETH

**Date:** 2026-06-22
**Verdict:** None of the researched pure-TA strategies have a deployable edge at 15m.
Keep the live bot **Kronos-only**; deploy none of these.

## What was tested

A deep-research pass (claude-mem S210) produced 5 candidate strategies expressed
purely in the bot's 6 signal primitives. The user picked the recommended 3 for backtest:

1. **#1 Trend-Aligned VWAP Discount Pullback** — `vwap`+`oversold`+`ema_trend`, ATR brackets (1.2/2.0).
2. **#2 EMA Trend-Momentum (core)** — `ema_trend` (the 0.30 `kronos_forecast` confluence was
   dropped: host venv has no torch/CUDA; EMA is the evidenced core anyway), ATR brackets (1.5/3.0).
3. **#4 ETH Relative-Strength Rotation** — `relative_strength`+`ema_trend`+`vwap`, ETH with BTC
   benchmark, ATR brackets (1.3/2.5).

**Data:** Coinbase 15m, BTC/USD + ETH/USD, **2022-01-01 → 2026-06-22** (~156k bars/symbol,
backfilled via `swingbot.backfill_cli --exchange coinbase`). Spans 2022 bear, 2023 recovery,
2024 bull, 2025 chop. (BTC/ETH 15m were NOT previously in the archive — only alts were; the
deep archive had only ~26 days of BTC/ETH 15m.)

**Harness:** `lab/strategy_backtest.py` defines the profiles and a vectorized `run_backtest_fast`
that precomputes every signal score + the regime gate over the full series, then replays
entries/exits through the **real** `SimulatedBroker`/`exit_decision`/`bracket_levels`/`position_size`.
It is **validated bit-for-bit identical** to the production `swingbot.backtest.run_backtest` on an
8k-bar sample (the production harness is O(n²) — it recomputes indicators on a growing slice each
bar — and is infeasible at 156k bars; the fast path is O(n) and exact because all indicators are
causal `ewm(adjust=False)`/rolling).

Diagnostics: `lab/strategy_diag.py` (cost sensitivity + per-year), `lab/strategy_htf.py` (1h/4h).

## Evidence

### 15m cost sensitivity — totRet% over 4.5y (PF)
| strategy | n | 0 bps | 10 bps | 25 bps | 60 bps* |
|---|--:|--:|--:|--:|--:|
| #1 VWAP BTC | 594 | −0 (0.99) | −14 (0.73) | −31 (0.47) | −59 (0.16) |
| #1 VWAP ETH | 803 | −6 (0.92) | −23 (0.71) | −43 (0.49) | −72 (0.20) |
| #2 EMA BTC | 6005 | +8 (1.01) | −76 (0.77) | −97 (0.54) | −100 (0.26) |
| #2 EMA ETH | 6124 | +9 (1.01) | −76 (0.82) | −98 (0.62) | −100 (0.36) |
| #4 ETH-RS | 6149 | +1 (1.00) | −78 (0.79) | −98 (0.58) | −100 (0.30) |

\*60 bps = profile default (`fee_rate=0.0025`/side + `slippage_rate=0.0005`/side).

**The 0-bps column is decisive:** even with zero cost there is no edge (#1 negative gross;
#2/#4 PF ≈ 1.01 ≈ random with these brackets). Net losses occur every calendar year, including
the 2024 bull. Root cause: 15m median ATR/price is only **0.287% (BTC) / 0.383% (ETH)**, so
2×ATR take-profits (~0.57% BTC) are *below* the round-trip cost — a perfect winner still loses.

### Higher-timeframe check (the only structural fix)
Resampling to 1h/4h raises ATR/price (1h: 0.64%/0.85%; 4h: 1.37%/1.83%).

- **1h:** still no edge (#2 EMA PF 1.03 BTC / 0.97 ETH gross; negative by 10 bps).
- **4h:** only **#2 EMA** develops a real but thin edge — PF **1.17 BTC / 1.11 ETH gross**,
  +12%/+9% over 4.5y at 10 bps, **breakeven at 25 bps, negative at 60 bps**. #1 and #4 stay dead.

### Kronos confirmation (the dropped 0.30 component of #2) — tested on GPU

Kronos *was* backtested (the host venv has no torch, but the `swingbot` container has torch
2.6.0+cu126 on an RTX 3050). `lab/kronos_precompute.py` runs Kronos-small (pred_len 8, ~207 ms/bar)
once per bar in the container and caches `pct_change`; `lab/strategy_kronos.py` then backtests
cheaply on the host. Done on **4h full history** (9,286 forecasts/symbol, ~32 min each, 0 NaN) —
4h chosen because it is the only TF where EMA showed a pulse, so it is the sharpest test.

totRet% over 4.5y (PF) @ 0/10/25/60 bps round-trip:

| profile | BTC n | BTC 0/10/25/60 | ETH n | ETH 0/10/25/60 |
|---|--:|---|--:|---|
| EMA-core (no Kronos) | 370 | 27(1.20)/16(1.12)/1(1.01)/−27(0.80) | 331 | 17(1.11)/8(1.05)/−4(0.98)/−27(0.82) |
| EMA0.70+Kronos0.30 (research #2) | 369 | 27(1.20)/16(1.12)/1(1.01)/−26(0.80) | 329 | 18(1.12)/9(1.06)/−3(0.98)/−26(0.83) |
| Kronos-only | 407 | 13(1.09)/2(1.02)/−12(0.92)/−38(0.73) | 372 | 24(1.14)/13(1.08)/−1(1.00)/−27(0.83) |

- **Adding Kronos to EMA does essentially nothing** — bit-identical to EMA-core on BTC (n 369 vs
  370), +1pt within noise on ETH. The 0.30 confluence weight rarely flips an entry (thr 0.003 vs
  0.005 gave identical results → the Kronos term is saturated/inert in the sum).
- **Kronos-only** has a thin standalone edge (PF 1.08–1.14 gross on ETH, weaker on BTC) that breaks
  even ~25 bps and loses at the 60 bps default — same shape as the EMA edge.
- (Full 15m Kronos would be ~9h of inference; 4h is the favorable-case test and already shows Kronos
  doesn't add edge, so 15m was not run. The *live* bot is already 15m Kronos-only with a stricter
  config — not separately re-backtested here.)

## Conclusion

- The 6-primitive **pure-TA signal set has no standalone alpha at 15m** on BTC/ETH; the costs are
  irrelevant because the gross edge is absent.
- **Kronos confirmation does not rescue them** (tested 4h GPU): EMA+Kronos ≈ EMA-core; Kronos-only is
  the same thin ~PF 1.1 trend edge that dies by 25–60 bps.
- The only candidate with a pulse is **EMA trend-momentum on 4h**, and it is marginal
  (~2–3%/yr gross) and cost-fragile (needs sub-25 bps round-trip). Not worth deploying without a
  low-fee venue and a forward paper validation.
- Decision (user, 2026-06-22): **deploy none; keep the live bot Kronos-only.**

## Reproduce

```bash
# ~8 min, idempotent; /tmp is ephemeral so re-run after reboot
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m swingbot.backfill_cli \
  --exchange coinbase --symbols "BTC/USD,ETH/USD" --timeframes 15m --start 2022-01-01
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python lab/strategy_backtest.py
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.strategy_diag
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.strategy_htf
```

### Reproduce (Kronos, in container)
```bash
CID=crypto-swing-bot-swingbot-1
docker cp /tmp/swingbot-bt/candles.db $CID:/tmp/bt.db
docker exec $CID mkdir -p /app/lab && docker cp lab/kronos_precompute.py $CID:/app/lab/
docker exec -i -e DB=/tmp/bt.db -e SYM=BTC/USD -e RULE=4h -e PRED=8 -e OUT=/tmp/k_btc_4h.csv \
  $CID python -u lab/kronos_precompute.py 2>/dev/null     # ~32 min; repeat SYM=ETH/USD
docker cp $CID:/tmp/k_btc_4h.csv /tmp/swingbot-bt/ && docker cp $CID:/tmp/k_eth_4h.csv /tmp/swingbot-bt/
SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.strategy_kronos
```

## Open avenues (if revisited)
- **Full 15m Kronos** (research #2 exactly): ~9h of inference, or ~2h for a recent 1y window. The 4h
  test (favorable case) already shows Kronos adds no edge, so this is expected to be negative.
- Full **sweep grids** (TP/stop/threshold/lookback) — low value given no gross 15m edge to amplify.
- Tighter **regime gate** (the SMA-200 filter allows NEUTRAL, which lets chop/bear bounces in).
- A genuinely different edge source (the 6-primitive TA set is exhausted at 15m).
