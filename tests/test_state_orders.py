import threading
from datetime import datetime, timezone

from swingbot.state import StateStore, StrategyStateView
from swingbot.types import (
    ExitReason,
    OpenPosition,
    OrderSide,
    PendingOrder,
    Regime,
    Side,
)


T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _pending(symbol="BTC/USD", side=OrderSide.BUY, broker_order_id=None):
    return PendingOrder(
        client_order_id=f"client-{symbol}-{side.value}",
        broker_order_id=broker_order_id,
        symbol=symbol,
        side=side,
        submitted_at=T0,
        requested_qty=0.25,
        stop=90.0,
        tp=120.0,
        max_hold_until=T0,
        score_at_entry=0.7,
        regime_at_entry=Regime.UPTREND,
        exit_reason=ExitReason.STOP if side is OrderSide.SELL else None,
        observed_exit_price=89.0 if side is OrderSide.SELL else None,
    )


def _position():
    return OpenPosition(
        symbol="BTC/USD",
        entry_ts=T0,
        entry_price=100.0,
        qty=0.25,
        stop=90.0,
        tp=120.0,
        max_hold_until=T0,
        score_at_entry=0.7,
        regime_at_entry=Regime.UPTREND,
        side=Side.LONG,
        entry_order_id="buy-1",
    )


def test_pending_orders_are_keyed_by_strategy(tmp_path):
    store = StateStore(str(tmp_path / "state.db"))
    btc = _pending("BTC/USD")
    eth = _pending("ETH/USD", broker_order_id="eth-1")

    store.save_pending_order(btc, strategy="btc")
    store.save_pending_order(eth, strategy="eth")

    assert store.load_pending_order("btc") == btc
    assert store.load_pending_order("eth") == eth
    assert store.load_all_pending_orders() == {"btc": btc, "eth": eth}


def test_pending_order_survives_reopen_with_nullable_broker_id(tmp_path):
    path = str(tmp_path / "state.db")
    expected = _pending()
    StateStore(path).save_pending_order(expected, strategy="btc")

    assert StateStore(path).load_pending_order("btc") == expected


def test_strategy_state_view_binds_pending_order_key(tmp_path):
    store = StateStore(str(tmp_path / "state.db"))
    view = StrategyStateView(store, "btc")
    expected = _pending()

    view.save_pending_order(expected)

    assert view.load_pending_order() == expected
    assert store.load_pending_order("btc") == expected
    assert store.load_pending_order("eth") is None
    view.clear_pending_order()
    assert view.load_pending_order() is None


def test_clearing_pending_order_leaves_position_unchanged(tmp_path):
    store = StateStore(str(tmp_path / "state.db"))
    position = _position()
    store.save_position(position, strategy="btc")
    store.save_pending_order(_pending(), strategy="btc")

    store.clear_pending_order("btc")

    assert store.load_pending_order("btc") is None
    assert store.load_position("btc") == position


def test_concurrent_pending_order_and_position_access_is_serialized(tmp_path):
    store = StateStore(str(tmp_path / "state.db"))
    position = _position()
    pending = _pending()
    errors = []

    def position_worker():
        try:
            for _ in range(25):
                store.save_position(position, "btc")
                assert store.load_position("btc") == position
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    def pending_worker():
        try:
            for _ in range(25):
                store.save_pending_order(pending, "btc")
                assert store.load_pending_order("btc") == pending
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [
        threading.Thread(target=position_worker),
        threading.Thread(target=pending_worker),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
