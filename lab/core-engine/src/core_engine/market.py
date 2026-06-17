from __future__ import annotations
import pandas as pd
from swingbot.types import MarketContext
from core_engine.config import SYMBOL, TIMEFRAME


def _frame(store, lookback: int) -> pd.DataFrame:
    rows = store.get(SYMBOL, TIMEFRAME, limit=lookback)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    if "ts" not in df.columns and "time" in df.columns:
        df["ts"] = pd.to_datetime(df["time"], unit="s", utc=True)
    elif "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.sort_values("ts").reset_index(drop=True)


def refresh_candles(store, fetcher) -> int:
    """Fetch latest 5-min bars via injected fetcher and upsert. Returns rows added."""
    if hasattr(fetcher, "fetch"):
        df = fetcher.fetch(SYMBOL, TIMEFRAME)
    else:
        df = fetcher.get_candles(SYMBOL, TIMEFRAME, lookback=300)
    if df is None or len(df) == 0:
        return 0
    return store.upsert_df(SYMBOL, TIMEFRAME, df)


def build_context(store, lookback: int = 300) -> MarketContext:
    df = _frame(store, lookback)
    if df.empty:
        raise ValueError("no candles available")
    return MarketContext(candles=df)


def latest_price(store) -> float:
    df = _frame(store, 1)
    if df.empty:
        raise ValueError("no candles available")
    return float(df["close"].iloc[-1])


def latest_atr(store, n: int = 14) -> float:
    df = _frame(store, n + 1)
    if df.empty:
        raise ValueError("no candles available")
    hl = (df["high"] - df["low"]).tail(n)
    return float(hl.mean()) if len(hl) else 1.0
