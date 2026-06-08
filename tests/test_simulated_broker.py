from datetime import datetime, timedelta, timezone

from swingbot.broker.simulated import SimulatedBroker
from swingbot.types import ExitReason, Regime


def _candle(ts, o, h, lo, c):
    return {"ts": ts, "open": o, "high": h, "low": lo, "close": c, "volume": 1.0}


T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_take_profit_fill():
    b = SimulatedBroker(cash=1000.0, fee_rate=0.0, slippage_rate=0.0)
    b.open_long(ts=T0, price=100.0, qty=1.0, stop=95.0, tp=110.0,
                max_hold_until=T0 + timedelta(hours=8),
                score_at_entry=0.7, regime_at_entry=Regime.UPTREND)
    trade = b.update(_candle(T0 + timedelta(minutes=15), 100, 111, 99, 108))
    assert trade is not None
    assert trade.exit_reason == ExitReason.TAKE_PROFIT
    assert abs(trade.exit_price - 110.0) < 1e-9
    assert b.position is None

def test_stop_fill_takes_priority_over_tp_same_bar():
    b = SimulatedBroker(cash=1000.0, fee_rate=0.0, slippage_rate=0.0)
    b.open_long(ts=T0, price=100.0, qty=1.0, stop=95.0, tp=110.0,
                max_hold_until=T0 + timedelta(hours=8),
                score_at_entry=0.7, regime_at_entry=Regime.UPTREND)
    trade = b.update(_candle(T0 + timedelta(minutes=15), 100, 111, 94, 100))
    assert trade.exit_reason == ExitReason.STOP
    assert abs(trade.exit_price - 95.0) < 1e-9

def test_time_cap_fill_at_close():
    b = SimulatedBroker(cash=1000.0, fee_rate=0.0, slippage_rate=0.0)
    b.open_long(ts=T0, price=100.0, qty=1.0, stop=90.0, tp=120.0,
                max_hold_until=T0 + timedelta(minutes=15),
                score_at_entry=0.7, regime_at_entry=Regime.UPTREND)
    trade = b.update(_candle(T0 + timedelta(minutes=15), 100, 105, 96, 101))
    assert trade.exit_reason == ExitReason.TIME_CAP
    assert abs(trade.exit_price - 101.0) < 1e-9

def test_fees_reduce_pnl():
    b = SimulatedBroker(cash=1000.0, fee_rate=0.01, slippage_rate=0.0)
    b.open_long(ts=T0, price=100.0, qty=1.0, stop=95.0, tp=110.0,
                max_hold_until=T0 + timedelta(hours=8),
                score_at_entry=0.7, regime_at_entry=Regime.UPTREND)
    trade = b.update(_candle(T0 + timedelta(minutes=15), 100, 111, 99, 108))
    # gross 10; fees: buy 100*0.01=1, sell 110*0.01=1.1 -> net 7.9
    assert abs(trade.pnl - 7.9) < 1e-6

def test_equity_reflects_open_position():
    b = SimulatedBroker(cash=1000.0, fee_rate=0.0, slippage_rate=0.0)
    b.open_long(ts=T0, price=100.0, qty=2.0, stop=95.0, tp=110.0,
                max_hold_until=T0 + timedelta(hours=8),
                score_at_entry=0.7, regime_at_entry=Regime.UPTREND)
    # spent 200 cash; at mark 105 -> position worth 210 -> equity 1010
    assert abs(b.equity(mark_price=105.0) - 1010.0) < 1e-9
