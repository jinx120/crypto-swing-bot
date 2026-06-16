from datetime import timedelta

import pytest
from alpaca.common.exceptions import APIError

from swingbot.profiles import ProfileStore
from swingbot.supervisor import PortfolioSupervisor
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
from tests.test_supervisor import FakeMarket, T0, _bars, _profile


class Broker:
    def __init__(self):
        self.positions = {}
        self.order = None
        self.lookup_error = None
        self.position_error = None
        self.account_error = None
        self.buys = []
        self.sells = []

    def get_account(self):
        if self.account_error is not None:
            raise self.account_error
        return {"equity": 1000.0, "cash": 1000.0, "buying_power": 1000.0}

    def get_position(self, symbol):
        if self.position_error is not None:
            raise self.position_error
        return self.positions.get(symbol)

    def get_order(self, order_id=None, client_order_id=None):
        if self.lookup_error is not None:
            raise self.lookup_error
        return self.order

    def submit_market_buy(self, symbol, qty, client_order_id):
        self.buys.append((symbol, qty, client_order_id))
        self.order = BrokerOrder(
            "buy-1", symbol, OrderSide.BUY, OrderStatus.ACCEPTED,
            qty, 0.0, None, client_order_id,
        )
        return self.order

    def submit_market_sell(self, symbol, qty, client_order_id):
        self.sells.append((symbol, qty, client_order_id))
        self.order = BrokerOrder(
            "sell-1", symbol, OrderSide.SELL, OrderStatus.ACCEPTED,
            qty, 0.0, None, client_order_id,
        )
        return self.order


def _supervisor(tmp_path, broker, *, profiles=None):
    profiles = profiles or ProfileStore(str(tmp_path / "profiles.db"))
    if not profiles.list():
        profiles.save("btc", _profile("BTC/USD"))
        profiles.arm("btc")
    market = FakeMarket({"BTC/USD": _bars()})
    sup = PortfolioSupervisor(
        profiles=profiles,
        creds=None,
        state_db=str(tmp_path / "state.db"),
        market=market,
        broker=broker,
    )
    sup.build()
    return sup


def _position():
    return OpenPosition(
        symbol="BTC/USD",
        entry_ts=T0,
        entry_price=100.0,
        qty=1.0,
        stop=90.0,
        tp=120.0,
        max_hold_until=T0 + timedelta(hours=8),
        score_at_entry=0.7,
        regime_at_entry=Regime.UPTREND,
        side=Side.LONG,
        entry_order_id="buy-1",
    )


def _pending_sell():
    return PendingOrder(
        client_order_id="client-sell",
        broker_order_id="sell-1",
        symbol="BTC/USD",
        side=OrderSide.SELL,
        submitted_at=T0,
        requested_qty=1.0,
        stop=90.0,
        tp=120.0,
        max_hold_until=T0 + timedelta(hours=8),
        score_at_entry=0.7,
        regime_at_entry=Regime.UPTREND,
        exit_reason=ExitReason.TAKE_PROFIT,
        observed_exit_price=105.0,
    )


def _lifecycle(desired, actual):
    return {
        "mode": "paper", "running_flag": actual, "thread_alive": actual,
        "running_actual": actual, "running_desired": desired,
        "running_desired_error": None, "paused": False, "halted": False,
        "startup_error": None,
    }


def test_restart_with_pending_buy_submits_no_duplicate_and_promotes_one_position(tmp_path):
    broker = Broker()
    first = _supervisor(tmp_path, broker)
    first.tick_all(T0)
    assert len(broker.buys) == 1

    restarted = _supervisor(tmp_path, broker, profiles=first.profiles)
    restarted.tick_all(T0)
    assert len(broker.buys) == 1
    assert restarted._store.load_position("btc") is None

    broker.order = BrokerOrder(
        "buy-1", "BTC/USD", OrderSide.BUY, OrderStatus.FILLED,
        1.0, 1.0, 101.0, broker.order.client_order_id,
    )
    broker.positions["BTC/USD"] = {
        "symbol": "BTC/USD", "qty": 1.0, "avg_entry_price": 101.0, "market_value": 101.0,
    }
    restarted.tick_all(T0)

    assert len(broker.buys) == 1
    assert restarted._store.load_position("btc").entry_order_id == "buy-1"


def test_confirmed_exit_survives_restart_in_journal_metrics_and_marker_fields(tmp_path):
    broker = Broker()
    sup = _supervisor(tmp_path, broker)
    sup._store.save_position(_position(), strategy="btc")
    sup._store.save_pending_order(_pending_sell(), strategy="btc")
    broker.order = BrokerOrder(
        "sell-1", "BTC/USD", OrderSide.SELL, OrderStatus.FILLED,
        1.0, 1.0, 105.0, "client-sell",
    )

    sup.tick_all(T0)
    restarted = _supervisor(tmp_path, broker, profiles=sup.profiles)

    marker = restarted.journal("btc")[0]
    assert restarted.metrics("btc")["n_trades"] == 1
    assert marker["entry_ts"] and marker["exit_ts"]
    assert marker["entry_price"] == 100.0
    assert marker["exit_price"] == 105.0
    assert marker["pnl"] == 5.0


@pytest.mark.parametrize("error", [
    APIError('{"code": 401, "message": "auth"}'),
    TimeoutError("timed out"),
    APIError('{"code": 429, "message": "rate limited"}'),
])
def test_broker_errors_record_failed_reconcile_without_clearing_position(tmp_path, error):
    broker = Broker()
    sup = _supervisor(tmp_path, broker)
    position = _position()
    sup._store.save_position(position, strategy="btc")
    broker.position_error = error

    sup.tick_all(T0)

    row = sup._telemetry.recent(strategy="btc")[0]
    assert row.reconcile == "failed"
    assert sup._store.load_position("btc") == position


def test_account_fetch_failure_records_failed_cycle_without_clearing_or_duplicating(tmp_path):
    # A total broker/credential/network outage that fails the account lookup must not
    # escape tick_all: the cycle is recorded as failed, the open position is preserved
    # (an error is not "flat"), no order is placed, and the local-only health surfaces
    # stay answerable. Regression guard for issue #2 (account fetch was outside the
    # per-strategy failure handling).
    broker = Broker()
    sup = _supervisor(tmp_path, broker)
    position = _position()
    sup._store.save_position(position, strategy="btc")
    broker.account_error = ConnectionError("alpaca unreachable")
    before_buys = list(broker.buys)

    sup.tick_all(T0)  # must not raise

    assert sup._store.load_position("btc") == position
    assert broker.buys == before_buys
    row = sup._telemetry.recent(strategy="btc")[0]
    assert row.decision_code is DecisionCode.ERROR
    assert isinstance(sup.readiness()["ready"], bool)
    assert sup.trading_health()["status"] in {"active", "inactive", "unhealthy"}


def test_health_reliability_uses_exactly_latest_200_completed_cycles(tmp_path):
    broker = Broker()
    sup = _supervisor(tmp_path, broker)
    sup.paused = True
    for _ in range(205):
        sup.tick_all(T0)
    sup.lifecycle_state = lambda: _lifecycle(True, True)

    health = sup.trading_health()

    assert health["reliability"]["completed_cycles"] == 200
    assert len(sup._telemetry.recent(limit=300, strategy="btc")) == 200


def test_desired_but_not_running_is_unhealthy_with_perfect_reliability(tmp_path):
    broker = Broker()
    sup = _supervisor(tmp_path, broker)
    sup.paused = True
    sup.tick_all(T0)
    sup.lifecycle_state = lambda: _lifecycle(True, False)

    health = sup.trading_health()

    assert health["reliability"]["cycle_completion_ratio"] == 1.0
    assert health["status"] == "unhealthy"
