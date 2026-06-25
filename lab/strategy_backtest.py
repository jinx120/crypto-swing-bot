"""Backtest the three research-recommended strategies (#1 VWAP pullback,
#2 EMA trend-momentum core, #4 ETH relative-strength) on deep Coinbase 15m
history, and rank them by risk-adjusted metrics.

Run:
    SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python lab/strategy_backtest.py

Notes / honest caveats baked in:
- run_backtest() is a pure entry/exit replay. It does NOT apply the live-only
  circuit breakers (cooldown_minutes, daily_loss_limit_pct, max_consecutive_losses),
  so these results reflect the raw signal+bracket edge (conservative: live guards
  can only reduce drawdown, not the edge).
- EmaTrendSignal divides by `band`; the research's band:0.0 ("long-bias only")
  is undefined, so band:0.0 -> 0.0005 (any real positive spread saturates to 1).
- Pick #2's 0.30 kronos_forecast confluence is dropped here (host venv has no
  torch/CUDA); we backtest the EMA core (ema_trend weight 1.0, threshold 0.65).
  If #2 ranks well, the live-deployed version re-adds kronos confirmation.
- Cost model = profile.fee_rate(0.25%/side) + slippage(0.05%/side) = 0.6% round
  trip. Research bar: median winner net return >= 3x round trip ~= 1.8%.
"""
from __future__ import annotations

import os
import sqlite3
import statistics
from dataclasses import dataclass

import numpy as np
import pandas as pd

from swingbot.backtest import _warmup_bars, run_backtest
from swingbot.broker.simulated import SimulatedBroker
from swingbot.exits import bracket_levels
from swingbot.indicators import atr, ema, rolling_vwap, rsi, sma
from swingbot.journal import TradeJournal
from swingbot.profile import StrategyProfile
from swingbot.sizing import position_size
from swingbot.types import Regime


def _signal_scores(df, profile, benchmark_df, kronos_pct=None) -> np.ndarray:
    """Vectorized confluence score per bar, identical to ConfluenceEngine.evaluate
    at each bar's .iloc[-1] (ewm/rolling indicators are causal: full-series value
    at i == slice[:i+1] last value).

    kronos_pct: optional per-bar forecast pct_change array (precomputed Kronos
    inference, aligned to df rows). Required if the profile uses 'kronos_forecast'.
    Mirrors KronosForecastSignal: score = clip(pct_change / threshold_pct, 0, 1);
    NaN forecast -> 0.5 (neutral_on_error)."""
    close = df["close"]
    total = np.zeros(len(df))
    for name, params in profile.signals.items():
        w = float(params.get("weight", 0.0))
        if name == "kronos_forecast":
            if kronos_pct is None:
                raise ValueError("profile uses kronos_forecast but kronos_pct not provided")
            thr = params.get("threshold_pct", 0.02)
            arr = np.asarray(kronos_pct, dtype=float)
            s_arr = np.clip(arr / thr, 0.0, 1.0)
            s_arr = np.where(np.isnan(arr), 0.5, s_arr)  # no_forecast -> neutral
            total += w * s_arr
            continue
        if name == "vwap":
            vwap = rolling_vwap(df, params.get("window", 96))
            s = ((vwap - close) / vwap / params.get("max_dist", 0.03)).clip(0, 1)
            s = s.where(vwap.notna(), 0.0)
        elif name == "oversold":
            lvl = params.get("oversold_level", 30.0)
            val = rsi(close, params.get("period", 14))
            s = ((lvl - val) / lvl).clip(0, 1).where(val.notna(), 0.0)
        elif name == "ema_trend":
            ef, es = ema(close, params["fast"]), ema(close, params["slow"])
            s = ((ef - es) / es / params.get("band", 0.01)).clip(0, 1)
            s = s.where(ef.notna() & es.notna() & (es != 0), 0.0)
        elif name == "relative_strength":
            lb, band = params.get("lookback", 96), params.get("band", 0.02)
            if benchmark_df is None:
                s = pd.Series(0.5, index=df.index)
            else:
                cr = (close / close.shift(lb) - 1.0).fillna(0.0).to_numpy()
                bc = benchmark_df["close"].reset_index(drop=True)
                br = (bc / bc.shift(lb) - 1.0).fillna(0.0).to_numpy()
                rs = cr - br
                s = pd.Series(np.clip((rs + band) / (2 * band), 0, 1), index=df.index)
        else:
            raise ValueError(f"unsupported signal in fast path: {name}")
        total += w * s.to_numpy()
    return total


def _regime_arrays(df, profile):
    """Per-bar regime gate (RegimeFilter: SMA(period), rising/falling), and enum."""
    close = df["close"]
    ma = sma(close, profile.regime_ma_period)
    rising = ma > ma.shift(1)
    up = ((close > ma) & rising).to_numpy()
    down = ((close < ma) & (~rising) & ma.notna()).to_numpy()
    neutral = ~up & ~down
    allowed = profile.allowed_regimes
    ok = np.zeros(len(df), bool)
    if Regime.UPTREND in allowed:
        ok |= up
    if Regime.NEUTRAL in allowed:
        ok |= neutral
    if Regime.DOWNTREND in allowed:
        ok |= down
    return ok, up, down


def run_backtest_fast(df, profile, benchmark_df=None, starting_equity=1000.0, kronos_pct=None):
    """O(n) backtest: precompute scores+regime vectorized, then replay entries/exits
    through the REAL SimulatedBroker/exit_decision/bracket_levels/position_size.
    Bit-for-bit equal to run_backtest (validated)."""
    n = len(df)
    if n < 2:
        raise ValueError("need >=2 candles")
    score = _signal_scores(df, profile, benchmark_df, kronos_pct=kronos_pct)
    regime_ok, up, down = _regime_arrays(df, profile)
    entry_ok = regime_ok & (score >= profile.entry_threshold)

    broker = SimulatedBroker(starting_equity, profile.fee_rate, profile.slippage_rate)
    journal = TradeJournal()
    atr_arr = atr(df, profile.atr_period).to_numpy()
    opens = df["open"].to_numpy(float)
    highs = df["high"].to_numpy(float)
    lows = df["low"].to_numpy(float)
    closes = df["close"].to_numpy(float)
    ts = df["ts"].tolist()
    warmup = _warmup_bars(profile)
    max_hold = (ts[1] - ts[0]) * profile.max_hold_bars

    for i in range(warmup, n - 1):
        tr = broker.update({"high": highs[i], "low": lows[i], "close": closes[i], "ts": ts[i]})
        if tr is not None:
            journal.record(tr)
        if broker.position is None and entry_ok[i]:
            a = atr_arr[i]
            if a > 0:
                ep = opens[i + 1]
                stop, tp = bracket_levels(ep, a, profile.stop_atr_mult, profile.take_profit_atr_mult)
                qty = position_size(broker.equity(closes[i]), profile.risk_per_trade,
                                    ep - stop, ep, profile.max_position_frac)
                reg = Regime.UPTREND if up[i] else (Regime.DOWNTREND if down[i] else Regime.NEUTRAL)
                broker.open_long(ts=ts[i + 1], price=ep, qty=qty, stop=stop, tp=tp,
                                 max_hold_until=ts[i + 1] + max_hold,
                                 score_at_entry=float(score[i]), regime_at_entry=reg)
    fc = broker.force_close(ts[-1], closes[-1])
    if fc is not None:
        journal.record(fc)
    return journal.trades, None


def validate(df):
    """Assert the fast path reproduces run_backtest's trades exactly on a sample."""
    sample = df.iloc[:8000].reset_index(drop=True)
    for name, prof in [("vwap", p1_vwap("BTC/USD")), ("ema", p2_ema_core("BTC/USD"))]:
        real, _ = run_backtest(sample, prof, starting_equity=START_EQ)
        fast, _ = run_backtest_fast(sample, prof, starting_equity=START_EQ)
        assert len(real) == len(fast), f"{name}: n {len(real)} != {len(fast)}"
        for a, b in zip(real, fast):
            assert a.entry_ts == b.entry_ts and abs(a.pnl - b.pnl) < 1e-6, \
                f"{name}: trade mismatch {a} vs {b}"
        print(f"  validate[{name}]: {len(real)} trades, fast == run_backtest  OK")

DB = os.path.join(os.environ.get("SWINGBOT_DATA_DIR", "/tmp/swingbot-bt"), "candles.db")
START_EQ = 1000.0
ROUND_TRIP = 0.006           # 0.6% (0.25%+0.05% per side x2)
COST_BAR = 3 * ROUND_TRIP    # 1.8% median-winner target


def load(symbol: str, tf: str = "15m") -> pd.DataFrame:
    con = sqlite3.connect(DB)
    df = pd.read_sql_query(
        "select ts, open, high, low, close, volume from bars "
        "where symbol=? and timeframe=? order by ts",
        con, params=(symbol, tf),
    )
    con.close()
    df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True)
    return df


def align(a: pd.DataFrame, b: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Inner-align two frames on ts so benchmark rows match index-for-index."""
    common = a.merge(b[["ts"]], on="ts")["ts"]
    aa = a[a["ts"].isin(common)].sort_values("ts").reset_index(drop=True)
    bb = b[b["ts"].isin(common)].sort_values("ts").reset_index(drop=True)
    return aa, bb


@dataclass
class Result:
    label: str
    symbol: str
    n: int
    win_rate: float
    profit_factor: float
    total_return_pct: float
    cagr_pct: float
    sharpe: float
    sortino: float
    max_dd_pct: float
    trades_per_week: float
    median_winner_pct: float
    pct_winners_over_cost: float
    cost_check: str


def extended_metrics(label, symbol, trades, df) -> Result:
    span_days = (df["ts"].iloc[-1] - df["ts"].iloc[0]).total_seconds() / 86400
    weeks = span_days / 7
    if not trades:
        return Result(label, symbol, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, "no-trades")

    trades = sorted(trades, key=lambda t: t.exit_ts)
    pnls = [t.pnl for t in trades]
    # per-trade net return on notional deployed
    rets = [t.pnl / (t.entry_price * t.qty) for t in trades]
    winners = [r for r in rets if r > 0]

    # compounded equity curve, resampled daily for Sharpe/Sortino
    eq, cum = [], START_EQ
    for t in trades:
        cum += t.pnl
        eq.append((t.exit_ts, cum))
    s = pd.Series({ts: v for ts, v in eq})
    s.index = pd.to_datetime(s.index, utc=True)
    daily = s.resample("1D").last().ffill()
    daily = pd.concat([pd.Series([START_EQ], index=[daily.index[0] - pd.Timedelta(days=1)]), daily])
    dret = daily.pct_change().dropna()
    sharpe = (dret.mean() / dret.std() * (365 ** 0.5)) if dret.std() > 0 else 0.0
    downside = dret[dret < 0]
    sortino = (dret.mean() / downside.std() * (365 ** 0.5)) if len(downside) > 1 and downside.std() > 0 else 0.0

    peak, max_dd = daily.iloc[0], 0.0
    for v in daily:
        peak = max(peak, v)
        max_dd = min(max_dd, v / peak - 1)

    final = START_EQ + sum(pnls)
    total_ret = final / START_EQ - 1
    cagr = (final / START_EQ) ** (365 / span_days) - 1 if span_days > 0 else 0.0

    gp = sum(p for p in pnls if p > 0)
    gl = -sum(p for p in pnls if p < 0)
    pf = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0.0)
    med_win = statistics.median(winners) if winners else 0.0
    pct_over = sum(1 for r in winners if r >= COST_BAR) / len(winners) if winners else 0.0
    check = "PASS" if med_win >= COST_BAR else "FAIL"

    return Result(
        label, symbol, len(trades), len(winners) / len(trades), pf,
        total_ret * 100, cagr * 100, sharpe, sortino, max_dd * 100,
        len(trades) / weeks if weeks else 0.0,
        med_win * 100, pct_over * 100, check,
    )


def p1_vwap(symbol: str) -> StrategyProfile:
    return StrategyProfile(
        symbol=symbol,
        signals={
            "vwap": {"weight": 0.45, "window": 96, "max_dist": 0.006},
            "oversold": {"weight": 0.30, "period": 14, "oversold_level": 35},
            "ema_trend": {"weight": 0.25, "fast": 20, "slow": 80, "band": 0.0005},
        },
        entry_threshold=0.60, regime_ma_period=200, atr_period=14,
        bracket_mode="atr", stop_atr_mult=1.2, take_profit_atr_mult=2.0,
        risk_per_trade=0.0075, max_hold_bars=24,
        daily_loss_limit_pct=0.025, max_consecutive_losses=3, cooldown_minutes=60,
    )


def p2_ema_core(symbol: str) -> StrategyProfile:
    return StrategyProfile(
        symbol=symbol,
        signals={"ema_trend": {"weight": 1.0, "fast": 21, "slow": 55, "band": 0.001}},
        entry_threshold=0.65, regime_ma_period=200, atr_period=14,
        bracket_mode="atr", stop_atr_mult=1.5, take_profit_atr_mult=3.0,
        risk_per_trade=0.0075, max_hold_bars=48,
        daily_loss_limit_pct=0.03, max_consecutive_losses=3, cooldown_minutes=45,
    )


def p4_eth_rs() -> StrategyProfile:
    return StrategyProfile(
        symbol="ETH/USD", benchmark_symbol="BTC/USD",
        signals={
            "relative_strength": {"weight": 0.50, "lookback": 96, "band": 0.005},
            "ema_trend": {"weight": 0.30, "fast": 21, "slow": 55, "band": 0.001},
            "vwap": {"weight": 0.20, "window": 96, "max_dist": 0.004},
        },
        entry_threshold=0.60, regime_ma_period=200, atr_period=14,
        bracket_mode="atr", stop_atr_mult=1.3, take_profit_atr_mult=2.5,
        risk_per_trade=0.0075, max_hold_bars=64,
        daily_loss_limit_pct=0.025, max_consecutive_losses=3, cooldown_minutes=120,
    )


def main() -> None:
    btc = load("BTC/USD")
    eth = load("ETH/USD")
    print(f"BTC/USD 15m: {len(btc)} bars  {btc['ts'].iloc[0]} -> {btc['ts'].iloc[-1]}")
    print(f"ETH/USD 15m: {len(eth)} bars  {eth['ts'].iloc[0]} -> {eth['ts'].iloc[-1]}")

    print("validating windowed replay against run_backtest ...")
    validate(btc)

    results: list[Result] = []
    runs = [
        ("#1 VWAP-pullback", "BTC/USD", p1_vwap("BTC/USD"), btc, None),
        ("#1 VWAP-pullback", "ETH/USD", p1_vwap("ETH/USD"), eth, None),
        ("#2 EMA-core",      "BTC/USD", p2_ema_core("BTC/USD"), btc, None),
        ("#2 EMA-core",      "ETH/USD", p2_ema_core("ETH/USD"), eth, None),
    ]
    for label, sym, prof, df, bench in runs:
        trades, _ = run_backtest_fast(df, prof, benchmark_df=bench, starting_equity=START_EQ)
        results.append(extended_metrics(label, sym, trades, df))
        print(f"  ran {label} {sym}: {len(trades)} trades")

    # #4 needs aligned ETH + BTC benchmark
    eth_a, btc_a = align(eth, btc)
    trades, _ = run_backtest_fast(eth_a, p4_eth_rs(), benchmark_df=btc_a, starting_equity=START_EQ)
    results.append(extended_metrics("#4 ETH-RS", "ETH/USD", trades, eth_a))
    print(f"  ran #4 ETH-RS ETH/USD: {len(trades)} trades")

    cols = ["label", "symbol", "n", "win%", "PF", "totRet%", "CAGR%",
            "Sharpe", "Sortino", "maxDD%", "trd/wk", "medWin%", "win>cost%", "costChk"]
    print("\n" + " | ".join(f"{c:>14}" if i > 1 else f"{c:<18}" for i, c in enumerate(cols)))
    print("-" * 150)
    for r in sorted(results, key=lambda x: x.sharpe, reverse=True):
        row = [
            f"{r.label:<18}", f"{r.symbol:>9}", f"{r.n:>4}",
            f"{r.win_rate*100:>6.1f}", f"{r.profit_factor:>6.2f}",
            f"{r.total_return_pct:>8.1f}", f"{r.cagr_pct:>7.1f}",
            f"{r.sharpe:>7.2f}", f"{r.sortino:>8.2f}", f"{r.max_dd_pct:>7.1f}",
            f"{r.trades_per_week:>7.2f}", f"{r.median_winner_pct:>8.2f}",
            f"{r.pct_winners_over_cost:>9.1f}", f"{r.cost_check:>8}",
        ]
        print(" ".join(row))


if __name__ == "__main__":
    main()
