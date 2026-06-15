from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest
from alpaca.common.exceptions import APIError

from swingbot.journal import TradeJournal
from swingbot.orchestrator import Orchestrator
from swingbot.profile import StrategyProfile
from swingbot.risk import RiskManager
from swingbot.state import StateStore
from swingbot.types import (
    BrokerOrder,
    DecisionCode,
    ExitReason,
    OpenPosition,
    OrderSide,
    OrderStatus,
    PendingOrder,
    Regime,
    Side,
)

T0 = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


def _series():
    closes = np.array(list(np.linspace(100, 130, 80)) + list(np.linspace(130, 118, 6)))
    return pd.DataFrame({
        "ts": pd.date_range(end=T0, periods=len(closes), freq="15min", tz="UTC"),
        "open": closes,
        "high": closes * 1.002,
        "low": closes * 0.998,
        "close": closes,
        "volume": np.full(len(closes), 100.0),
    })


class FakeData:
    def __init__(self, price=118.0):
        self.price = price
        self.candles = _series()

    def get_candles(self, *args, **kwargs):
        return self.candles

    def get_latest_price(self, symbol):
        return self.price


class ScriptedBroker:
    def __init__(self):
        self.position = None
        self.order = None
        self.lookup_error = None
        self.submit_error = None
        self.submit_status = OrderStatus.NEW
        self.buys = []
        self.sells = []
        self.lookups = []
        self.pending_seen_at_submit = False
        self.state = None

    def get_account(self):
        return {"equity": 1000.0, "cash": 1000.0, "buying_power": 1000.0}

    def get_position(self, symbol):
        return self.position

    def get_order(self, order_id=None, client_order_id=None):
        self.lookups.append((order_id, client_order_id))
        if self.lookup_error is not None:
            raise self.lookup_error
        return self.order

    def submit_market_buy(self, symbol, qty, client_order_id):
        self.pending_seen_at_submit = self.state.load_pending_order() is not None
        self.buys.append((symbol, qty, client_order_id))
        if self.submit_error is not None:
            raise self.submit_error
        return _order(
            OrderSide.BUY,
            self.submit_status,
            order_id="buy-1",
            client_order_id=client_order_id,
            requested_qty=qty,
        )

    def submit_market_sell(self, symbol, qty, client_order_id):
        self.pending_seen_at_submit = self.state.load_pending_order() is not None
        self.sells.append((symbol, qty, client_order_id))
        if self.submit_error is not None:
            raise self.submit_error
        return _order(
            OrderSide.SELL,
            self.submit_status,
            order_id="sell-1",
            client_order_id=client_order_id,
            requested_qty=qty,
        )


def _profile():
    return StrategyProfile.from_dict({
        "symbol": "TRX/USD",
        "timeframe": "15m",
        "signals": {
            "oversold": {"weight": 0.6, "oversold_level": 45, "period": 14},
            "vwap": {"weight": 0.4, "window": 20, "max_dist": 0.05},
        },
        "entry_threshold": 0.25,
        "regime_ma_period": 50,
        "atr_period": 14,
        "stop_atr_mult": 2.0,
        "take_profit_atr_mult": 2.0,
        "max_hold_bars": 32,
        "risk_per_trade": 0.02,
    })


def _orch(tmp_path, broker=None, data=None, state=None, journal=None):
    broker = broker or ScriptedBroker()
    data = data or FakeData()
    state = state or StateStore(str(tmp_path / "state.db"))
    broker.state = state
    profile = _profile()
    return Orchestrator(
        profile=profile,
        data=data,
        broker=broker,
        state=state,
        risk=RiskManager(profile, state.load_risk_state()),
        journal=journal or TradeJournal(),
    )


def _order(
    side,
    status,
    *,
    order_id="order-1",
    client_order_id="client-1",
    requested_qty=1.0,
    filled_qty=0.0,
    filled_avg_price=None,
):
    return BrokerOrder(
        order_id=order_id,
        client_order_id=client_order_id,
        symbol="TRX/USD",
        side=side,
        status=status,
        requested_qty=requested_qty,
        filled_qty=filled_qty,
        filled_avg_price=filled_avg_price,
    )


def _pending_buy(broker_order_id=None):
    return PendingOrder(
        client_order_id="client-buy",
        broker_order_id=broker_order_id,
        symbol="TRX/USD",
        side=OrderSide.BUY,
        submitted_at=T0,
        requested_qty=2.0,
        stop=90.0,
        tp=120.0,
        max_hold_until=T0,
        score_at_entry=0.7,
        regime_at_entry=Regime.UPTREND,
    )


def _position():
    return OpenPosition(
        symbol="TRX/USD",
        entry_ts=T0,
        entry_price=100.0,
        qty=2.0,
        stop=90.0,
        tp=120.0,
        max_hold_until=T0,
        score_at_entry=0.7,
        regime_at_entry=Regime.UPTREND,
        side=Side.LONG,
        entry_order_id="buy-1",
    )


def _pending_sell():
    return PendingOrder(
        client_order_id="client-sell",
        broker_order_id="sell-1",
        symbol="TRX/USD",
        side=OrderSide.SELL,
        submitted_at=T0,
        requested_qty=2.0,
        stop=90.0,
        tp=120.0,
        max_hold_until=T0,
        score_at_entry=0.7,
        regime_at_entry=Regime.UPTREND,
        exit_reason=ExitReason.STOP,
        observed_exit_price=89.0,
    )


def test_buy_intent_is_persisted_before_submission_and_position_stays_empty(tmp_path):
    broker = ScriptedBroker()
    orch = _orch(tmp_path, broker=broker)

    result = orch.tick(T0)

    pending = orch.state.load_pending_order()
    assert result.code is DecisionCode.ORDER_SUBMITTED
    assert broker.pending_seen_at_submit is True
    assert pending.broker_order_id == "buy-1"
    assert orch.state.load_position() is None


def test_restart_with_client_only_pending_buy_submits_no_duplicate(tmp_path):
    state = StateStore(str(tmp_path / "state.db"))
    state.save_pending_order(_pending_buy())
    broker = ScriptedBroker()
    broker.order = _order(
        OrderSide.BUY, OrderStatus.ACCEPTED, client_order_id="client-buy"
    )
    orch = _orch(tmp_path, broker=broker, state=state)

    result = orch.reconcile(T0)

    assert result.code is DecisionCode.ORDER_PENDING
    assert broker.buys == []
    assert broker.lookups == [(None, "client-buy")]
    assert state.load_pending_order().broker_order_id == "order-1"


def test_submit_timeout_retains_intent_for_client_id_reconcile(tmp_path):
    broker = ScriptedBroker()
    broker.submit_error = TimeoutError("submit timed out")
    orch = _orch(tmp_path, broker=broker)

    result = orch.tick(T0)

    pending = orch.state.load_pending_order()
    assert result.code is DecisionCode.ERROR
    assert pending is not None and pending.broker_order_id is None


def test_definitive_submission_rejection_clears_intent(tmp_path):
    broker = ScriptedBroker()
    broker.submit_status = OrderStatus.REJECTED
    orch = _orch(tmp_path, broker=broker)

    result = orch.tick(T0)

    assert result.code is DecisionCode.ORDER_FAILED
    assert orch.state.load_pending_order() is None


def test_confirmed_order_not_found_clears_pending(tmp_path):
    state = StateStore(str(tmp_path / "state.db"))
    state.save_pending_order(_pending_buy())
    orch = _orch(tmp_path, state=state)

    result = orch.reconcile(T0)

    assert result.code is DecisionCode.ORDER_FAILED
    assert state.load_pending_order() is None


@pytest.mark.parametrize("error", [
    APIError('{"code": 1, "message": "auth"}'),
    TimeoutError("timed out"),
    APIError('{"code": 429, "message": "rate limited"}'),
])
def test_lookup_errors_propagate_and_retain_pending(tmp_path, error):
    state = StateStore(str(tmp_path / "state.db"))
    state.save_pending_order(_pending_buy())
    broker = ScriptedBroker()
    broker.lookup_error = error
    orch = _orch(tmp_path, broker=broker, state=state)

    with pytest.raises(type(error)):
        orch.reconcile(T0)

    assert state.load_pending_order() is not None


def test_partial_buy_fill_remains_pending_without_position(tmp_path):
    state = StateStore(str(tmp_path / "state.db"))
    state.save_pending_order(_pending_buy("buy-1"))
    broker = ScriptedBroker()
    broker.order = _order(
        OrderSide.BUY, OrderStatus.PARTIALLY_FILLED, order_id="buy-1", filled_qty=1.0
    )
    orch = _orch(tmp_path, broker=broker, state=state)

    result = orch.reconcile(T0)

    assert result.code is DecisionCode.ORDER_PENDING
    assert state.load_pending_order() is not None
    assert state.load_position() is None


def test_filled_buy_waits_for_position_then_promotes_broker_truth(tmp_path):
    state = StateStore(str(tmp_path / "state.db"))
    state.save_pending_order(_pending_buy("buy-1"))
    broker = ScriptedBroker()
    broker.order = _order(
        OrderSide.BUY,
        OrderStatus.FILLED,
        order_id="buy-1",
        filled_qty=2.0,
        filled_avg_price=101.0,
    )
    orch = _orch(tmp_path, broker=broker, state=state)

    assert orch.reconcile(T0).code is DecisionCode.ORDER_PENDING
    broker.position = {
        "symbol": "TRX/USD", "qty": 1.75, "avg_entry_price": 102.0, "market_value": 178.5,
    }
    result = orch.reconcile(T0)

    position = state.load_position()
    assert result.code is DecisionCode.ENTERED
    assert position.qty == 1.75
    assert position.entry_price == 102.0
    assert position.entry_order_id == "buy-1"
    assert state.load_pending_order() is None


def test_rejected_buy_clears_pending_and_returns_failed(tmp_path):
    state = StateStore(str(tmp_path / "state.db"))
    state.save_pending_order(_pending_buy("buy-1"))
    broker = ScriptedBroker()
    broker.order = _order(OrderSide.BUY, OrderStatus.REJECTED, order_id="buy-1")
    orch = _orch(tmp_path, broker=broker, state=state)

    assert orch.reconcile(T0).code is DecisionCode.ORDER_FAILED
    assert state.load_pending_order() is None


def test_submitted_sell_keeps_open_position(tmp_path):
    state = StateStore(str(tmp_path / "state.db"))
    state.save_position(_position())
    data = FakeData(price=89.0)
    broker = ScriptedBroker()
    orch = _orch(tmp_path, broker=broker, data=data, state=state)

    result = orch.tick(T0)

    assert result.code is DecisionCode.EXIT_SUBMITTED
    assert state.load_position() is not None
    assert state.load_pending_order().side is OrderSide.SELL


def test_filled_sell_and_confirmed_flat_records_actual_fill_trade_once(tmp_path):
    state = StateStore(str(tmp_path / "state.db"))
    state.save_position(_position())
    state.save_pending_order(_pending_sell())
    broker = ScriptedBroker()
    broker.order = _order(
        OrderSide.SELL,
        OrderStatus.FILLED,
        order_id="sell-1",
        filled_qty=2.0,
        filled_avg_price=88.0,
    )
    journal = TradeJournal()
    orch = _orch(tmp_path, broker=broker, state=state, journal=journal)

    result = orch.reconcile(T0)

    assert result.code is DecisionCode.EXITED
    assert state.load_position() is None
    assert state.load_pending_order() is None
    assert len(journal.trades) == 1
    assert journal.trades[0].exit_price == 88.0
    assert journal.trades[0].pnl == -24.0
