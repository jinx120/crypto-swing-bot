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
