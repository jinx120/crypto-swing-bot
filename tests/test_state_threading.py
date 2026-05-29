import threading
from datetime import datetime, timezone
from swingbot.state import StateStore
from swingbot.types import OpenPosition, Regime, Side


def test_statestore_usable_across_threads(tmp_path):
    s = StateStore(str(tmp_path / "s.db"))   # created in main thread
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    pos = OpenPosition(symbol="TRX/USD", entry_ts=now, entry_price=0.1, qty=10.0,
                       stop=0.09, tp=0.12, max_hold_until=now,
                       score_at_entry=0.5, regime_at_entry=Regime.UPTREND, side=Side.LONG)
    errors = []
    def worker():
        try:
            s.save_position(pos)              # used from a different thread
            assert s.load_position().symbol == "TRX/USD"
        except Exception as e:                # noqa
            errors.append(e)
    t = threading.Thread(target=worker); t.start(); t.join()
    assert errors == [], f"cross-thread StateStore use failed: {errors}"
