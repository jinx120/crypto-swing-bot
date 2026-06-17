import os
from types import SimpleNamespace

import pytest

from swingbot.broker.alpaca import AlpacaBroker, normalize_symbol
from swingbot.types import BrokerOrder, OrderSide, OrderStatus

CREDS = bool(os.getenv("ALPACA_API_KEY_ID") and os.getenv("ALPACA_API_SECRET_KEY"))


def test_normalize_symbol_keeps_slash():
    assert normalize_symbol("BTC/USD") == "BTC/USD"
    assert normalize_symbol("btc/usd") == "BTC/USD"

@pytest.mark.skipif(not CREDS, reason="Alpaca creds not set")
def test_live_account_smoke():
    from swingbot.broker.alpaca import AlpacaBroker
    b = AlpacaBroker(os.environ["ALPACA_API_KEY_ID"],
                     os.environ["ALPACA_API_SECRET_KEY"], paper=True)
    acct = b.get_account()
    assert acct["equity"] >= 0
    _ = b.get_position("BTC/USD")


from alpaca.common.exceptions import APIError
class _HttpError:
    def __init__(self, status_code):
        self.response = type("Response", (), {"status_code": status_code})()


class _PositionClient:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def get_open_position(self, symbol):
        if self.error is not None:
            raise self.error
        return self.result


class _OrderClient:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []
        self.submitted = None

    def get_order_by_id(self, order_id):
        self.calls.append(("id", order_id))
        if self.error is not None:
            raise self.error
        return self.result

    def get_order_by_client_id(self, client_id):
        self.calls.append(("client", client_id))
        if self.error is not None:
            raise self.error
        return self.result

    def submit_order(self, order_data):
        self.submitted = order_data
        if self.error is not None:
            raise self.error
        return self.result


def _api_error(status_code):
    return APIError('{"code": 1, "message": "request failed"}',
                    _HttpError(status_code))


def _broker_with_client(client):
    broker = object.__new__(AlpacaBroker)
    broker._client = client
    return broker


def test_get_position_returns_none_only_for_confirmed_404():
    broker = _broker_with_client(_PositionClient(error=_api_error(404)))
    assert broker.get_position("BTC/USD") is None


def test_get_position_propagates_non_404_api_error():
    broker = _broker_with_client(_PositionClient(error=_api_error(500)))
    with pytest.raises(APIError):
        broker.get_position("BTC/USD")


def test_get_position_propagates_transport_error():
    broker = _broker_with_client(_PositionClient(error=ConnectionError("network down")))
    with pytest.raises(ConnectionError):
        broker.get_position("BTC/USD")


def test_get_position_serializes_confirmed_position():
    position = type("Position", (), {
        "qty": "0.25",
        "avg_entry_price": "50000",
        "market_value": "12500",
    })()
    broker = _broker_with_client(_PositionClient(result=position))
    assert broker.get_position("BTC/USD") == {
        "symbol": "BTC/USD",
        "qty": 0.25,
        "avg_entry_price": 50000.0,
        "market_value": 12500.0,
    }


def _alpaca_order(status="new", side="buy", filled_avg_price=None):
    return SimpleNamespace(
        id="broker-1",
        client_order_id="client-1",
        symbol="BTC/USD",
        side=side,
        status=status,
        qty="1.5",
        filled_qty="0.4",
        filled_avg_price=filled_avg_price,
    )


@pytest.mark.parametrize("alpaca_status, normalized", [
    ("new", OrderStatus.NEW),
    ("accepted", OrderStatus.ACCEPTED),
    ("partially_filled", OrderStatus.PARTIALLY_FILLED),
    ("filled", OrderStatus.FILLED),
    ("rejected", OrderStatus.REJECTED),
    ("canceled", OrderStatus.CANCELED),
    ("expired", OrderStatus.EXPIRED),
    # Full Alpaca order lifecycle — a pending/transient status must never crash
    # serialization (a live `pending_new` order once took the whole bot down on
    # auto-start reconcile). See docs.alpaca.markets order lifecycle.
    ("pending_new", OrderStatus.PENDING_NEW),
    ("accepted_for_bidding", OrderStatus.ACCEPTED_FOR_BIDDING),
    ("pending_cancel", OrderStatus.PENDING_CANCEL),
    ("pending_replace", OrderStatus.PENDING_REPLACE),
    ("replaced", OrderStatus.REPLACED),
    ("done_for_day", OrderStatus.DONE_FOR_DAY),
    ("stopped", OrderStatus.STOPPED),
    ("suspended", OrderStatus.SUSPENDED),
    ("calculated", OrderStatus.CALCULATED),
    ("held", OrderStatus.HELD),
])
def test_get_order_serializes_known_statuses(alpaca_status, normalized):
    client = _OrderClient(_alpaca_order(alpaca_status, filled_avg_price="101.5"))
    broker = _broker_with_client(client)

    result = broker.get_order(order_id="broker-1")

    assert result == BrokerOrder(
        order_id="broker-1",
        client_order_id="client-1",
        symbol="BTC/USD",
        side=OrderSide.BUY,
        status=normalized,
        requested_qty=1.5,
        filled_qty=0.4,
        filled_avg_price=101.5,
    )
    assert client.calls == [("id", "broker-1")]


def test_get_order_can_lookup_by_client_id_and_preserves_nullable_fill_price():
    client = _OrderClient(_alpaca_order(side="sell"))
    broker = _broker_with_client(client)

    result = broker.get_order(client_order_id="client-1")

    assert result.side is OrderSide.SELL
    assert result.filled_avg_price is None
    assert client.calls == [("client", "client-1")]


def test_get_order_requires_exactly_one_lookup_id():
    broker = _broker_with_client(_OrderClient())

    with pytest.raises(ValueError):
        broker.get_order()
    with pytest.raises(ValueError):
        broker.get_order(order_id="broker-1", client_order_id="client-1")


def test_get_order_returns_none_only_for_confirmed_404():
    broker = _broker_with_client(_OrderClient(error=_api_error(404)))
    assert broker.get_order(order_id="missing") is None


@pytest.mark.parametrize("error", [
    _api_error(401),
    _api_error(429),
    TimeoutError("timed out"),
    ConnectionError("network down"),
])
def test_get_order_propagates_non_404_errors(error):
    broker = _broker_with_client(_OrderClient(error=error))
    with pytest.raises(type(error)):
        broker.get_order(order_id="broker-1")


def test_get_order_rejects_unknown_status():
    broker = _broker_with_client(_OrderClient(_alpaca_order("not_a_real_status")))
    with pytest.raises(ValueError, match="unknown Alpaca order status"):
        broker.get_order(order_id="broker-1")


@pytest.mark.parametrize("side", [OrderSide.BUY, OrderSide.SELL])
def test_market_submission_includes_client_id_and_returns_normalized_order(side):
    client = _OrderClient(_alpaca_order(side=side.value))
    broker = _broker_with_client(client)

    if side is OrderSide.BUY:
        result = broker.submit_market_buy("btc/usd", 1.5, "client-1")
    else:
        result = broker.submit_market_sell("btc/usd", 1.5, "client-1")

    assert result.order_id == "broker-1"
    assert result.side is side
    assert client.submitted.symbol == "BTC/USD"
    assert client.submitted.client_order_id == "client-1"
