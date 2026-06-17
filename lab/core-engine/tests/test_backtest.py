import pandas as pd
from core_engine.backtest import run_backtest
from core_engine.config import PROFILE
from tests.conftest import FakeKronos


def test_backtest_runs_and_returns_result():
    closes = [100 + (i % 20) * 0.5 for i in range(200)]
    candles = pd.DataFrame({
        "open": closes, "high": [c + 0.5 for c in closes],
        "low": [c - 0.5 for c in closes], "close": closes,
        "volume": [10.0] * 200,
    })
    res = run_backtest(candles, profile=PROFILE, kronos=FakeKronos(0.9))
    assert res.final_equity > 0
    assert res.wins + res.losses == len(res.trades)
