"""Diagnostics for why the recommended strategies lose as-specified:
  1) gross (zero-cost) vs net edge  -> is the edge eaten by the 0.6% round trip?
  2) ATR/price magnitude            -> are ATR-scaled TPs below round-trip cost?
  3) per-calendar-year net PnL      -> bull vs bear attribution
Run: SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python lab/strategy_diag.py
"""
from __future__ import annotations

import dataclasses

import numpy as np

from swingbot.indicators import atr
from lab.strategy_backtest import (
    START_EQ, align, extended_metrics, load, p1_vwap, p2_ema_core, p4_eth_rs,
    run_backtest_fast,
)


def with_round_trip(profile, rt):
    """Set total round-trip cost = rt (fee_rate per side = rt/2, slippage 0)."""
    return dataclasses.replace(profile, fee_rate=rt / 2.0, slippage_rate=0.0)


def per_year(trades):
    out = {}
    for t in trades:
        y = t.exit_ts.year
        out.setdefault(y, [0, 0.0])
        out[y][0] += 1
        out[y][1] += t.pnl
    return out


def main():
    btc, eth = load("BTC/USD"), load("ETH/USD")
    eth_a, btc_a = align(eth, btc)

    runs = [
        ("#1 VWAP", "BTC/USD", p1_vwap("BTC/USD"), btc, None),
        ("#1 VWAP", "ETH/USD", p1_vwap("ETH/USD"), eth, None),
        ("#2 EMA",  "BTC/USD", p2_ema_core("BTC/USD"), btc, None),
        ("#2 EMA",  "ETH/USD", p2_ema_core("ETH/USD"), eth, None),
        ("#4 ETHRS","ETH/USD", p4_eth_rs(), eth_a, btc_a),
    ]

    print("=== ATR/price magnitude (median, %), and TP distance vs 0.6% round trip ===")
    for sym, df in [("BTC/USD", btc), ("ETH/USD", eth)]:
        a = atr(df, 14).to_numpy()
        c = df["close"].to_numpy()
        r = np.nanmedian(a / c) * 100
        print(f"  {sym}: median ATR/price = {r:.3f}%   2xATR TP ~= {2*r:.3f}%   "
              f"3xATR TP ~= {3*r:.3f}%   (round trip = 0.60%)")

    print("\n=== cost sensitivity: totRet% (PF) at round-trip 0 / 10 / 25 / 60 bps ===")
    costs = [0.0, 0.0010, 0.0025, 0.0060]
    print(f"{'run':<16}{'n':>7}" + "".join(f"{int(c*1e4):>4}bps" .rjust(16) for c in costs))
    for label, sym, prof, df, bench in runs:
        cells = []
        n = 0
        for c in costs:
            t, _ = run_backtest_fast(df, with_round_trip(prof, c),
                                     benchmark_df=bench, starting_equity=START_EQ)
            m = extended_metrics(label, sym, t, df)
            n = m.n
            cells.append(f"{m.total_return_pct:>7.0f}({m.profit_factor:>4.2f})")
        print(f"{label+' '+sym:<16}{n:>7}" + "".join(s.rjust(16) for s in cells))

    print("\n=== per-year NET pnl ($ on 1000 start, non-compounded sum) ===")
    for label, sym, prof, df, bench in runs:
        nt, _ = run_backtest_fast(df, prof, benchmark_df=bench, starting_equity=START_EQ)
        yr = per_year(nt)
        cells = "  ".join(f"{y}:{v[1]:+7.0f}({v[0]})" for y, v in sorted(yr.items()))
        print(f"  {label+' '+sym:<16} {cells}")


if __name__ == "__main__":
    main()
