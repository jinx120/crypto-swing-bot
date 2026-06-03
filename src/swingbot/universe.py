"""Curated fallback list of Alpaca-tradable crypto USD pairs.

Used when live broker asset listing is unavailable (no creds / network error).
"""
from __future__ import annotations

_FALLBACK = [
    "AAVE/USD", "AVAX/USD", "BCH/USD", "BTC/USD", "DOGE/USD", "DOT/USD",
    "ETH/USD", "LINK/USD", "LTC/USD", "SHIB/USD", "SOL/USD", "SUSHI/USD",
    "UNI/USD", "XRP/USD", "YFI/USD",
]


def fallback_universe() -> list[str]:
    return sorted(_FALLBACK)
