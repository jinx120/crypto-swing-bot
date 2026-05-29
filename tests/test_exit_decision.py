from datetime import datetime, timedelta, timezone

from swingbot.exits import exit_decision
from swingbot.types import ExitReason

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
LATER = T0 + timedelta(hours=9)


def test_stop_before_tp_same_bar():
    res = exit_decision(stop=95.0, tp=110.0, max_hold_until=LATER,
                        high=111.0, low=94.0, close=100.0, now=T0)
    assert res == (ExitReason.STOP, 95.0)

def test_take_profit():
    res = exit_decision(stop=95.0, tp=110.0, max_hold_until=LATER,
                        high=111.0, low=99.0, close=108.0, now=T0)
    assert res == (ExitReason.TAKE_PROFIT, 110.0)

def test_time_cap_fills_at_close():
    res = exit_decision(stop=90.0, tp=120.0, max_hold_until=T0,
                        high=105.0, low=96.0, close=101.0, now=T0)
    assert res == (ExitReason.TIME_CAP, 101.0)

def test_no_exit():
    res = exit_decision(stop=90.0, tp=120.0, max_hold_until=LATER,
                        high=105.0, low=96.0, close=101.0, now=T0)
    assert res is None

def test_live_spot_price_stop():
    res = exit_decision(stop=95.0, tp=110.0, max_hold_until=LATER,
                        high=94.5, low=94.5, close=94.5, now=T0)
    assert res == (ExitReason.STOP, 95.0)
