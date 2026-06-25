"""Test the higher-timeframe hypothesis: the 15m failure is driven by ATR(~0.3%)
being smaller than round-trip cost. On 1h/4h, ATR/price is ~2x/4x larger, so
ATR-scaled brackets clear cost more easily and trends are cleaner. Same research
profiles, resampled bars (params now span a proportionally longer horizon).
Run: SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.strategy_htf
"""
from __future__ import annotations

import dataclasses

import numpy as np

from swingbot.indicators import atr
from lab.strategy_backtest import (
    START_EQ, align, extended_metrics, load, p1_vwap, p2_ema_core, p4_eth_rs,
    run_backtest_fast,
)


def resample(df, rule):
    d = df.set_index("ts")
    out = d.resample(rule).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return out.dropna().reset_index()


def with_rt(profile, rt):
    return dataclasses.replace(profile, fee_rate=rt / 2.0, slippage_rate=0.0)


def main():
    btc15, eth15 = load("BTC/USD"), load("ETH/USD")
    costs = [0.0, 0.0010, 0.0025, 0.0060]

    for rule, tf in [("1h", "1h"), ("4h", "4h")]:
        btc, eth = resample(btc15, rule), resample(eth15, rule)
        eth_a, btc_a = align(eth, btc)
        for sym, df in [("BTC/USD", btc), ("ETH/USD", eth)]:
            a = atr(df, 14).to_numpy(); c = df["close"].to_numpy()
            print(f"[{tf}] {sym}: {len(df)} bars, median ATR/price = "
                  f"{np.nanmedian(a/c)*100:.3f}%")
        runs = [
            ("#1 VWAP", "BTC/USD", p1_vwap("BTC/USD"), btc, None),
            ("#1 VWAP", "ETH/USD", p1_vwap("ETH/USD"), eth, None),
            ("#2 EMA",  "BTC/USD", p2_ema_core("BTC/USD"), btc, None),
            ("#2 EMA",  "ETH/USD", p2_ema_core("ETH/USD"), eth, None),
            ("#4 ETHRS","ETH/USD", p4_eth_rs(), eth_a, btc_a),
        ]
        print(f"=== [{tf}] cost sensitivity: totRet% (PF) @ 0/10/25/60 bps ===")
        print(f"{'run':<16}{'n':>6}" + "".join(f"{int(x*1e4)}bps".rjust(15) for x in costs))
        for label, sym, prof, df, bench in runs:
            cells, n = [], 0
            for x in costs:
                t, _ = run_backtest_fast(df, with_rt(prof, x), benchmark_df=bench,
                                         starting_equity=START_EQ)
                m = extended_metrics(label, sym, t, df); n = m.n
                cells.append(f"{m.total_return_pct:>7.0f}({m.profit_factor:>4.2f})")
            print(f"{label+' '+sym:<16}{n:>6}" + "".join(s.rjust(15) for s in cells))
        print()


if __name__ == "__main__":
    main()
