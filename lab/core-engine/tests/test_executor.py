from datetime import datetime, timedelta, timezone
from core_engine.config import LOOP_SECONDS, PROFILE
from core_engine.contracts import OrderIntent
from core_engine.executor import Executor
from tests.conftest import FakeBroker


def _intent():
    return OrderIntent(symbol="BTC/USD", qty=0.01, entry_price=100.0, stop=95.0,
                       tp=110.0, max_hold_until=datetime(2026, 6, 17, tzinfo=timezone.utc),
                       reason="test")


def test_filled_buy_returns_position():
    pos = Executor(FakeBroker(buy_stalls=False)).enter(
        _intent(), now=datetime(2026, 6, 17, tzinfo=timezone.utc))
    assert pos is not None and pos.qty == 0.01


def test_pending_buy_returns_none_truthfully():
    pos = Executor(FakeBroker(buy_stalls=True)).enter(
        _intent(), now=datetime(2026, 6, 17, tzinfo=timezone.utc))
    assert pos is None  # never report a position on an unfilled order


def test_exit_returns_realized_pnl():
    broker = FakeBroker(buy_stalls=False)
    ex = Executor(broker)
    pos = ex.enter(_intent(), now=datetime(2026, 6, 17, tzinfo=timezone.utc))
    pnl = ex.exit(pos, price=105.0, reason="take_profit")
    assert round(pnl, 2) == round((105.0 - 100.0) * 0.01, 2)


def test_reconcile_adopts_broker_position_with_live_management_levels():
    now = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)
    broker = FakeBroker(position={
        "symbol": "BTC/USD",
        "qty": 0.02,
        "avg_entry_price": 100.0,
    })

    pos = Executor(broker).reconcile(None, profile=PROFILE, atr=2.0, now=now)

    assert pos is not None
    assert pos.stop == 97.0
    assert pos.entry_price == 100.0
    assert pos.tp == 104.0
    assert pos.max_hold_until == now + timedelta(
        seconds=PROFILE.max_hold_bars * LOOP_SECONDS
    )
