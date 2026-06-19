import math

from core_engine.backtest import BacktestResult
from swingbot.autodash.backtest_runner import summarize, BacktestSummary


def _result(pnls):
    trades = [{"pnl": p, "reason": "tp", "won": p > 0} for p in pnls]
    wins = sum(1 for p in pnls if p > 0)
    return BacktestResult(trades=trades, final_equity=1000.0 + sum(pnls),
                          wins=wins, losses=len(pnls) - wins)


def test_summarize_empty_is_zeroed():
    s = summarize(BacktestResult([], 1000.0, 0, 0), equity0=1000.0)
    assert isinstance(s, BacktestSummary)
    assert s.n_trades == 0 and s.win_rate == 0.0 and s.total_pnl == 0.0
    assert s.sharpe == 0.0 and s.equity_curve == [1000.0]


def test_summarize_computes_winrate_pnl_and_curve():
    s = summarize(_result([10.0, -5.0, 15.0]), equity0=1000.0)
    assert s.n_trades == 3
    assert math.isclose(s.win_rate, 2 / 3)
    assert math.isclose(s.total_pnl, 20.0)
    assert s.equity_curve == [1000.0, 1010.0, 1005.0, 1020.0]
    assert s.sharpe > 0.0


def test_to_dict_shape():
    d = summarize(_result([1.0, 2.0]), equity0=1000.0).to_dict()
    assert set(d) == {"n_trades", "win_rate", "total_pnl", "sharpe",
                      "final_equity", "equity_curve"}


import numpy as np
import pandas as pd

from swingbot.autodash.backtest_runner import run_comparison


def _trending_candles(n=200):
    ts = pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC")
    base = np.linspace(100.0, 130.0, n)
    return pd.DataFrame({
        "ts": (ts.view("int64") // 1_000_000_000),
        "open": base, "high": base + 1.0, "low": base - 1.0,
        "close": base + 0.5, "volume": np.full(n, 1.0),
    })


def test_run_comparison_returns_both_sides_with_shapes():
    out = run_comparison(_trending_candles(), kronos_factory=None)
    assert set(out) == {"ema", "kronos"}
    for side in ("ema", "kronos"):
        assert set(out[side]) == {"n_trades", "win_rate", "total_pnl",
                                  "sharpe", "final_equity", "equity_curve"}
    # kronos_factory=None makes both runs identical (kronos contributes 0.0)
    assert out["ema"]["n_trades"] == out["kronos"]["n_trades"]
