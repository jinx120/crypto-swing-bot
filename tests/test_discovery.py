import pandas as pd

from swingbot.discovery import good_history, windows_for, _apply_window, MIN_TRADES


def test_good_history_requires_trades_expectancy_profit_factor():
    assert good_history({"n_trades": 25, "expectancy": 0.5, "profit_factor": 1.3})
    assert not good_history({"n_trades": 5, "expectancy": 0.5, "profit_factor": 1.3})   # too few
    assert not good_history({"n_trades": 25, "expectancy": -0.1, "profit_factor": 1.3}) # losing
    assert not good_history({"n_trades": 25, "expectancy": 0.5, "profit_factor": 0.9})  # pf<=1
    assert not good_history({"n_trades": None, "expectancy": None, "profit_factor": None})
    assert MIN_TRADES == 20


def test_windows_for_only_offers_covered_windows():
    day = 86400
    short = windows_for({"min_ts": 1_700_000_000, "max_ts": 1_700_000_000 + 10 * day})
    assert [w["key"] for w in short] == ["full"]                 # 10 days -> full only
    deep = windows_for({"min_ts": 1_700_000_000, "max_ts": 1_700_000_000 + 400 * day})
    assert [w["key"] for w in deep] == ["full", "last_1y", "last_90d", "last_30d"]
    assert windows_for({}) == [{"key": "full", "label": "Full history", "days": None}]


def test_apply_window_slices_trailing_days():
    ts = pd.date_range("2024-01-01", periods=200, freq="D", tz="UTC")
    df = pd.DataFrame({"ts": ts, "close": range(200)})
    full = _apply_window(df, "full")
    last30 = _apply_window(df, "last_30d")
    assert len(full) == 200
    assert 29 <= len(last30) <= 31                               # ~30 trailing days
    assert last30["ts"].iloc[-1] == df["ts"].iloc[-1]
