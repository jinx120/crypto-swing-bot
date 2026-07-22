from datetime import datetime, timezone, timedelta

from swingbot.equity_store import EquitySnapshotStore


def _t(h):
    return datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc) - timedelta(hours=h)


def test_drawdown_zero_when_empty(tmp_path):
    s = EquitySnapshotStore(str(tmp_path / "e.db"))
    assert s.drawdown(24) == 0.0


def test_drawdown_from_window_peak(tmp_path):
    s = EquitySnapshotStore(str(tmp_path / "e.db"))
    now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    s.record(10000.0, now - timedelta(hours=20))  # peak in window
    s.record(9600.0, now - timedelta(hours=1))  # current: 4% below peak
    assert round(s.drawdown(24, now), 4) == 0.04


def test_drawdown_ignores_data_outside_window(tmp_path):
    s = EquitySnapshotStore(str(tmp_path / "e.db"))
    now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    s.record(20000.0, now - timedelta(hours=48))  # old peak, outside 24h window
    s.record(10000.0, now - timedelta(hours=2))
    s.record(9900.0, now - timedelta(hours=1))
    assert round(s.drawdown(24, now), 4) == 0.01  # peak inside window is 10000


def test_pnl_window(tmp_path):
    s = EquitySnapshotStore(str(tmp_path / "e.db"))
    now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    s.record(10000.0, now - timedelta(hours=23))
    s.record(10300.0, now - timedelta(minutes=5))
    abs_pnl, pct = s.pnl_window(24, now)
    assert round(abs_pnl, 2) == 300.0
    assert round(pct, 4) == 0.03
