import os
import pytest

from swingbot.broker.alpaca import normalize_symbol

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
from swingbot.broker.alpaca import AlpacaBroker


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
