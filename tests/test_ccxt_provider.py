import pandas as pd

from swingbot.data.ccxt_provider import CcxtProvider


def test_quote_map_translates_usd_to_usdt():
    p = CcxtProvider(exchange_id="binance", exchange=object())
    assert p.map_symbol("BTC/USD") == "BTC/USDT"
    assert p.map_symbol("ETH/USD") == "ETH/USDT"


def test_per_symbol_override_wins_over_quote_map():
    p = CcxtProvider(exchange_id="kraken", exchange=object(),
                     symbol_overrides={"BTC/USD": "XBT/USD"})
    assert p.map_symbol("BTC/USD") == "XBT/USD"


def test_custom_quote_map_passes_unknown_quotes_through():
    p = CcxtProvider(exchange_id="coinbase", exchange=object(), quote_map={})
    assert p.map_symbol("BTC/USD") == "BTC/USD"  # exact USD venue, no remap
