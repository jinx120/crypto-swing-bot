from lab.deep_backfill import HISTORY_START, TIMEFRAMES, deep_config
from swingbot.data.ccxt_provider import CcxtProvider


def test_deep_config_disables_the_usd_to_usdt_rewrite():
    cfg = deep_config("BTC/USD")
    assert cfg.quote_map == {}
    provider = CcxtProvider(exchange_id=cfg.exchange, quote_map=cfg.quote_map)
    assert provider.map_symbol("BTC/USD") == "BTC/USD"


def test_the_default_quote_map_would_have_rewritten_to_usdt():
    # Pins the trap this module exists to avoid. Coinbase's USDT market returns
    # nothing before 2022-01-01, which is why every prior archive starts there.
    assert CcxtProvider(exchange_id="coinbase").map_symbol("BTC/USD") == "BTC/USDT"


def test_deep_config_starts_at_each_market_s_inception():
    assert deep_config("BTC/USD").history_start == "2015-07-20"
    assert deep_config("ETH/USD").history_start == "2016-05-18"


def test_deep_config_fetches_both_research_timeframes():
    assert deep_config("BTC/USD").timeframes == ["1h", "1d"]
    assert deep_config("BTC/USD").exchange == "coinbase"


def test_history_start_covers_exactly_the_two_studied_symbols():
    assert set(HISTORY_START) == {"BTC/USD", "ETH/USD"}
    assert TIMEFRAMES == ["1h", "1d"]
