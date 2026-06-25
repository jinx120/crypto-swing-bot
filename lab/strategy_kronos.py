"""Does Kronos confirmation rescue the strategies? Uses precomputed Kronos
pct_change (from lab/kronos_precompute.py, run in the GPU container) so the
backtest math runs on the host. Compares, on identical 4h bars + cost levels:
  - EMA-core (no Kronos)            <- baseline (the only thing with a 15m/4h pulse)
  - EMA(0.70) + Kronos(0.30)        <- research #2 as fully specified
  - Kronos-only                     <- incumbent-style
plus a small Kronos threshold sweep. All cheap (one inference pass, reused).

Run: SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.strategy_kronos
Expects /tmp/swingbot-bt/k_btc_4h.csv and k_eth_4h.csv.
"""
from __future__ import annotations

import dataclasses
import os

import pandas as pd

from swingbot.profile import StrategyProfile
from lab.strategy_backtest import START_EQ, extended_metrics, load, run_backtest_fast
from lab.strategy_htf import resample

KDIR = "/tmp/swingbot-bt"
COSTS = [0.0, 0.0010, 0.0025, 0.0060]


def with_rt(p, rt):
    return dataclasses.replace(p, fee_rate=rt / 2.0, slippage_rate=0.0)


def load_kronos(sym_tag, df4h):
    """Trim df4h to ~start of kronos coverage (keeping indicator warmup) and return
    (df, kronos_pct_array)."""
    k = pd.read_csv(os.path.join(KDIR, f"k_{sym_tag}_4h.csv"))
    k["ts"] = pd.to_datetime(k["ts"], utc=True)
    first = k["ts"].iloc[0]
    gi = int(df4h.index[df4h["ts"] == first][0])
    trim = max(0, gi - 205)
    df = df4h.iloc[trim:].reset_index(drop=True)
    kser = k.set_index("ts")["pct_change"]
    kpct = df["ts"].map(kser).to_numpy()
    return df, kpct


# --- 4h profiles (same risk frame as the 15m research specs) ---
def ema_core():
    return StrategyProfile(
        symbol="X", signals={"ema_trend": {"weight": 1.0, "fast": 21, "slow": 55, "band": 0.001}},
        entry_threshold=0.65, regime_ma_period=200, atr_period=14,
        bracket_mode="atr", stop_atr_mult=1.5, take_profit_atr_mult=3.0,
        risk_per_trade=0.0075, max_hold_bars=48)


def ema_kronos(thr=0.003):
    return StrategyProfile(
        symbol="X", signals={
            "ema_trend": {"weight": 0.70, "fast": 21, "slow": 55, "band": 0.001},
            "kronos_forecast": {"weight": 0.30, "threshold_pct": thr}},
        entry_threshold=0.65, regime_ma_period=200, atr_period=14,
        bracket_mode="atr", stop_atr_mult=1.5, take_profit_atr_mult=3.0,
        risk_per_trade=0.0075, max_hold_bars=48)


def kronos_only(thr=0.003, entry=0.65):
    return StrategyProfile(
        symbol="X", signals={"kronos_forecast": {"weight": 1.0, "threshold_pct": thr}},
        entry_threshold=entry, regime_ma_period=200, atr_period=14,
        bracket_mode="atr", stop_atr_mult=1.5, take_profit_atr_mult=3.0,
        risk_per_trade=0.0075, max_hold_bars=48)


def sweep_row(label, df, prof, kpct):
    cells, n = [], 0
    for c in COSTS:
        t, _ = run_backtest_fast(df, with_rt(prof, c), starting_equity=START_EQ, kronos_pct=kpct)
        m = extended_metrics(label, "", t, df)
        n = m.n
        cells.append(f"{m.total_return_pct:>7.0f}({m.profit_factor:>4.2f})")
    print(f"{label:<26}{n:>6}" + "".join(s.rjust(15) for s in cells))


def main():
    for tag, sym in [("btc", "BTC/USD"), ("eth", "ETH/USD")]:
        df4h = resample(load(sym), "4h")
        df, kpct = load_kronos(tag, df4h)
        span = (df["ts"].iloc[-1] - df["ts"].iloc[0]).days
        kvalid = int((~pd.isna(kpct)).sum())
        print(f"\n##### {sym} 4h: {len(df)} bars ({span}d), kronos on {kvalid} #####")
        print(f"{'profile':<26}{'n':>6}" + "".join(f"{int(c*1e4)}bps".rjust(15) for c in COSTS))
        sweep_row("EMA-core (no kronos)", df, ema_core(), kpct)
        sweep_row("EMA0.7+Kronos0.3 thr.003", df, ema_kronos(0.003), kpct)
        sweep_row("EMA0.7+Kronos0.3 thr.005", df, ema_kronos(0.005), kpct)
        sweep_row("Kronos-only thr.003 e.65", df, kronos_only(0.003, 0.65), kpct)
        sweep_row("Kronos-only thr.005 e.50", df, kronos_only(0.005, 0.50), kpct)


if __name__ == "__main__":
    main()
