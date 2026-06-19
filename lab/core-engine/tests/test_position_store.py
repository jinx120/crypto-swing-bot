from datetime import datetime, timezone

from core_engine.contracts import EnginePosition
from core_engine.position_store import PositionStore


def _pos():
    return EnginePosition(
        symbol="BTC/USD",
        entry_ts=datetime(2026, 6, 17, 18, tzinfo=timezone.utc),
        entry_price=65000.0, qty=0.01, stop=64000.0, tp=67000.0,
        max_hold_until=datetime(2026, 6, 17, 20, tzinfo=timezone.utc))


def test_set_then_get_roundtrip(tmp_path):
    ps = PositionStore(str(tmp_path / "state.db"))
    ps.set(_pos())
    got = ps.get()
    assert got["symbol"] == "BTC/USD"
    assert got["entry_price"] == 65000.0 and got["qty"] == 0.01
    assert got["stop"] == 64000.0 and got["tp"] == 67000.0
    assert got["entry_ts"] == "2026-06-17T18:00:00+00:00"


def test_clear_sets_none(tmp_path):
    ps = PositionStore(str(tmp_path / "state.db"))
    ps.set(_pos())
    ps.clear()
    assert ps.get() is None


def test_get_empty_db_is_none(tmp_path):
    assert PositionStore(str(tmp_path / "state.db")).get() is None
