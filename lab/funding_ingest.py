"""Ingest perpetual-swap funding rates into SeriesStore.

Venue: Hyperliquid via ccxt. It is the only keyless source verified to serve deep
funding history from this host - Binance returns HTTP 451 (geo-block), binance.us
is spot-only and has no perpetuals at all, Bybit's edge returns 403, and OKX caps
public funding history at ~97 days. Hyperliquid honours `since` and pages FORWARD
from 2023-05-12, at HOURLY granularity.

Spec 6b states thresholds for 8-hour funding, so hourly readings are converted to
a trailing 8-hour sum before storage; stored values are directly comparable to the
+0.05% / -0.01% thresholds.

Run (writes to the research data dir, never to ~/.swingbot):
    SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.funding_ingest
"""
from __future__ import annotations

import os

HOUR_MS = 3_600_000
WINDOW_HOURS = 8


def fetch_funding(exchange, symbol: str, since_ms: int, end_ms: int,
                  page_limit: int = 500) -> list[tuple[int, float]]:
    """Page forward through funding history, returning (epoch_seconds, rate).

    Stops when the venue returns nothing, stops advancing, or passes end_ms - so
    a venue that silently caps its history terminates instead of looping.
    """
    out: dict[int, float] = {}
    since = since_ms
    while since <= end_ms:
        page = exchange.fetch_funding_rate_history(symbol, since=since, limit=page_limit)
        if not page:
            break
        for row in page:
            ts_ms = int(row["timestamp"])
            if ts_ms > end_ms:
                break
            out[ts_ms // 1000] = float(row["fundingRate"])
        last_ms = int(page[-1]["timestamp"])
        if last_ms < since:
            break                      # no forward progress
        if len(page) < page_limit:
            break                      # partial page: history is exhausted
        since = last_ms + HOUR_MS
    return sorted(out.items())


def to_8h_equivalent(rows: list[tuple[int, float]]) -> list[tuple[int, float]]:
    """Trailing 8-hour sum of hourly rates, stamped at the window's last hour.

    Rows before the first complete window are dropped rather than partially
    summed - a partial window would understate funding and bias the signal long.
    """
    out = []
    for i in range(WINDOW_HOURS - 1, len(rows)):
        window = rows[i - WINDOW_HOURS + 1: i + 1]
        out.append((rows[i][0], sum(v for _, v in window)))
    return out


def ingest(store, exchange, *, symbol: str = "BTC/USDC:USDC",
           store_symbol: str = "BTC/USD", since_ms: int, end_ms: int) -> int:
    """Fetch, convert to 8h-equivalent, and upsert under series name funding_8h."""
    hourly = fetch_funding(exchange, symbol, since_ms, end_ms)
    return store.upsert("funding_8h", store_symbol, to_8h_equivalent(hourly))


def main() -> None:
    import ccxt
    import pandas as pd

    from swingbot.data.series_store import SeriesStore

    data_dir = os.environ.get("SWINGBOT_DATA_DIR", "/tmp/swingbot-bt")
    store = SeriesStore(os.path.join(data_dir, "series.db"))
    exchange = ccxt.hyperliquid({"enableRateLimit": True})
    since = int(pd.Timestamp("2023-05-01", tz="UTC").timestamp() * 1000)
    end = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
    written = ingest(store, exchange, since_ms=since, end_ms=end)
    cov = store.coverage("funding_8h", "BTC/USD")
    print(f"[funding] wrote {written} rows; coverage {cov}")


if __name__ == "__main__":
    main()
