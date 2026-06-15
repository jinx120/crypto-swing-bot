from datetime import datetime, timezone

import pandas as pd

from swingbot.data.market import closed_bar_freshness, closed_bars


def _bars(*timestamps: str) -> pd.DataFrame:
    return pd.DataFrame({
        "ts": pd.to_datetime(list(timestamps), utc=True),
        "open": range(len(timestamps)),
        "high": range(len(timestamps)),
        "low": range(len(timestamps)),
        "close": range(len(timestamps)),
        "volume": range(len(timestamps)),
    })


def test_empty_input_has_no_closed_bar_and_is_not_fresh():
    bars = _bars()
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)

    result = closed_bar_freshness(bars, timeframe="15m", now=now, provider_grace=120)

    assert closed_bars(bars, timeframe="15m", now=now).empty
    assert result.closed.empty
    assert result.bar_ts is None
    assert result.fresh is False


def test_bar_is_excluded_until_its_interval_closes():
    bars = _bars("2026-01-01T12:00:00Z")
    now = datetime(2026, 1, 1, 12, 14, 59, tzinfo=timezone.utc)

    assert closed_bars(bars, timeframe="15m", now=now).empty


def test_latest_closed_bar_is_fresh_at_grace_boundary():
    bars = _bars("2026-01-01T12:00:00Z")
    now = datetime(2026, 1, 1, 12, 17, tzinfo=timezone.utc)

    result = closed_bar_freshness(bars, timeframe="15m", now=now, provider_grace=120)

    assert result.bar_ts == datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    assert result.fresh is True


def test_latest_closed_bar_is_stale_after_grace_boundary():
    bars = _bars("2026-01-01T12:00:00Z")
    now = datetime(2026, 1, 1, 12, 17, 1, tzinfo=timezone.utc)

    assert closed_bar_freshness(
        bars, timeframe="15m", now=now, provider_grace=120
    ).fresh is False


def test_in_progress_bar_is_excluded_and_bar_ts_is_latest_closed():
    bars = _bars("2026-01-01T12:00:00Z", "2026-01-01T12:15:00Z")
    now = datetime(2026, 1, 1, 12, 16, tzinfo=timezone.utc)

    result = closed_bar_freshness(bars, timeframe="15m", now=now, provider_grace=120)

    assert list(result.closed["ts"]) == [pd.Timestamp("2026-01-01T12:00:00Z")]
    assert result.bar_ts == datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
