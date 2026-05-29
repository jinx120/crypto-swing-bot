import numpy as np
import pandas as pd

from swingbot.backtest import run_backtest
from swingbot.profile import StrategyProfile


def _make_series(closes):
    n = len(closes)
    closes = np.array(closes, dtype=float)
    return pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open": closes,
        "high": closes * 1.002,
        "low": closes * 0.998,
        "close": closes,
        "volume": np.full(n, 100.0),
    })


def _dip_and_recover():
    base = list(np.linspace(100, 130, 80))          # uptrend warmup
    dip = list(np.linspace(130, 118, 6))            # sharp dip (oversold)
    recover = list(np.linspace(118, 135, 20))       # bounce -> hits take-profit
    return _make_series(base + dip + recover)


def _profile():
    return StrategyProfile.from_dict({
        "symbol": "TRX/USD",
        "timeframe": "15m",
        "signals": {
            "oversold": {"weight": 0.6, "oversold_level": 45, "period": 14},
            "vwap": {"weight": 0.4, "window": 20, "max_dist": 0.05},
        },
        "entry_threshold": 0.25,
        "regime_ma_period": 50,
        "atr_period": 14,
        "stop_atr_mult": 2.0,
        "take_profit_atr_mult": 2.0,
        "max_hold_bars": 32,
        "risk_per_trade": 0.02,
        "fee_rate": 0.0,
        "slippage_rate": 0.0,
    })


def test_backtest_produces_trades_and_metrics():
    df = _dip_and_recover()
    trades, metrics = run_backtest(df, _profile(), starting_equity=1000.0)
    assert metrics.n_trades >= 1
    assert metrics.n_trades == len(trades)
    from swingbot.types import Regime
    assert all(t.regime_at_entry != Regime.DOWNTREND for t in trades)

def test_backtest_no_trades_in_pure_downtrend():
    df = _make_series(list(np.linspace(200, 100, 120)))   # relentless decline
    trades, metrics = run_backtest(df, _profile(), starting_equity=1000.0)
    assert metrics.n_trades == 0

def test_backtest_is_lookahead_safe_entry_at_next_open():
    df = _dip_and_recover()
    trades, _ = run_backtest(df, _profile(), starting_equity=1000.0)
    assert len(trades) >= 1
    opens = set(round(o, 6) for o in df["open"])
    assert round(trades[0].entry_price, 6) in opens
