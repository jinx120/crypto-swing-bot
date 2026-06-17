import pandas as pd
from swingbot.data.store import CandleStore
from core_engine.config import SYMBOL, TIMEFRAME
from core_engine.market import build_context, latest_price


def _seed(store):
    closes = [100 + i * 0.2 for i in range(50)]
    df = pd.DataFrame({
        "ts": pd.date_range("2026-06-17", periods=50, freq="5min", tz="UTC"),
        "open": closes, "high": [c + 0.2 for c in closes],
        "low": [c - 0.2 for c in closes], "close": closes, "volume": [5.0] * 50,
    })
    store.upsert_df(SYMBOL, TIMEFRAME, df)


def test_build_context_returns_dataframe(tmp_path):
    store = CandleStore(str(tmp_path / "c.db"))
    _seed(store)
    ctx = build_context(store, lookback=30)
    assert len(ctx.candles) == 30
    assert {"open", "high", "low", "close"} <= set(ctx.candles.columns)


def test_latest_price(tmp_path):
    store = CandleStore(str(tmp_path / "c.db"))
    _seed(store)
    assert latest_price(store) > 100
