import numpy as np
import pandas as pd

from lab.research_data import EXTRA_PREFIX, attach_extra, resample, split_extras


def _bars(n, start="2024-01-01", freq="15min"):
    ts = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({
        "ts": ts,
        "open": np.arange(n, dtype=float) + 100.0,
        "high": np.arange(n, dtype=float) + 101.0,
        "low": np.arange(n, dtype=float) + 99.0,
        "close": np.arange(n, dtype=float) + 100.5,
        "volume": np.ones(n),
    })


def test_resample_15m_to_4h_aggregates_ohlcv():
    df = _bars(32)  # 32 x 15m == 8h == two 4h bars
    out = resample(df, "4h")
    assert len(out) == 2
    assert out["open"].iloc[0] == df["open"].iloc[0]
    assert out["close"].iloc[0] == df["close"].iloc[15]
    assert out["high"].iloc[0] == df["high"].iloc[:16].max()
    assert out["low"].iloc[0] == df["low"].iloc[:16].min()
    assert out["volume"].iloc[0] == 16.0


def test_attach_extra_is_causal_backward_asof():
    df = _bars(4, freq="1h")
    series = pd.DataFrame({
        "ts": pd.to_datetime(["2024-01-01 00:00", "2024-01-01 02:00"], utc=True),
        "value": [0.1, 0.9],
    })
    merged = attach_extra(df, "funding_8h", series)
    col = merged[EXTRA_PREFIX + "funding_8h"].tolist()
    # bar 0 and 1 see the 00:00 reading; bars 2,3 see the 02:00 reading.
    # No bar ever sees a value stamped after its own ts.
    assert col == [0.1, 0.1, 0.9, 0.9]


def test_attach_extra_leaves_nan_before_first_reading():
    df = _bars(3, freq="1h")
    series = pd.DataFrame({
        "ts": pd.to_datetime(["2024-01-01 02:00"], utc=True),
        "value": [0.5],
    })
    merged = attach_extra(df, "cb_premium", series)
    col = merged[EXTRA_PREFIX + "cb_premium"]
    assert bool(col.isna().iloc[0]) and bool(col.isna().iloc[1])
    assert col.iloc[2] == 0.5


def test_split_extras_returns_ohlcv_frame_and_arrays():
    df = attach_extra(_bars(3, freq="1h"), "funding_8h", pd.DataFrame(
        {"ts": pd.to_datetime(["2024-01-01 00:00"], utc=True), "value": [0.2]}))
    ohlc, extras = split_extras(df)
    assert list(ohlc.columns) == ["ts", "open", "high", "low", "close", "volume"]
    assert set(extras) == {"funding_8h"}
    assert extras["funding_8h"].tolist() == [0.2, 0.2, 0.2]
