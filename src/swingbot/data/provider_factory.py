from __future__ import annotations

from swingbot.data.ccxt_provider import CcxtProvider

_CCXT_VENUES = {"coinbase", "kraken"}


def provider_for(data_source: str, creds):
    """Return a market-data provider for the configured data_source.

    coinbase/kraken -> public CcxtProvider with USD pairs sent verbatim.
    alpaca -> the broker's data provider via creds, or None if unset.
    """
    if data_source in _CCXT_VENUES:
        return CcxtProvider(exchange_id=data_source, quote_map={})
    if data_source == "alpaca":
        return creds.make_data() if creds else None
    raise ValueError(f"unknown data_source {data_source!r}")
