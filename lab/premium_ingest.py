"""Ingest the Coinbase premium series into SeriesStore.

This is the keyless stand-in for spec 6c's on-chain exchange net flow, which has
no free data source (Glassnode / CryptoQuant expose exchange flows on paid tiers
only). The premium - Coinbase BTC/USD against offshore BTC/USDT - is a
well-documented proxy for the same thing: US spot demand pressure. A positive
premium means US buyers are lifting offers (accumulation); a negative premium
means US supply is hitting bids (distribution).

Local leg: the Coinbase 15m bars already in the research archive, resampled to 4h.
Offshore leg: OKX BTC/USDT spot 4h, which paginates keyless back to 2022.

Run:
    SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.premium_ingest
"""
from __future__ import annotations

import os

import pandas as pd

from lab.research_data import resample


def compute_premium(local_4h: pd.DataFrame, offshore_4h: pd.DataFrame) -> pd.DataFrame:
    """Relative close spread on timestamps present at BOTH venues.

    (local - offshore) / offshore. Inner-joining on ts means a venue outage drops
    the bar entirely rather than producing a fabricated spread.
    """
    merged = local_4h[["ts", "close"]].merge(
        offshore_4h[["ts", "close"]], on="ts", suffixes=("_local", "_offshore"))
    merged["value"] = (merged["close_local"] - merged["close_offshore"]) / \
        merged["close_offshore"]
    return merged[["ts", "value"]].sort_values("ts").reset_index(drop=True)


def ingest(store, local_15m: pd.DataFrame, offshore_provider, *,
           store_symbol: str = "BTC/USD", offshore_symbol: str = "BTC/USDT",
           start_ms: int, end_ms: int) -> int:
    """Resample the local leg to 4h, fetch the offshore leg, store the spread."""
    local_4h = resample(local_15m, "4h")
    offshore_4h = offshore_provider.get_candles_range(
        offshore_symbol, "4h", start_ms, end_ms)
    series = compute_premium(local_4h, offshore_4h)
    rows = [(int(ts.timestamp()), float(v))
            for ts, v in zip(series["ts"], series["value"])]
    return store.upsert("cb_premium", store_symbol, rows)


def main() -> None:
    from lab.research_data import load
    from swingbot.data.ccxt_provider import CcxtProvider
    from swingbot.data.series_store import SeriesStore

    data_dir = os.environ.get("SWINGBOT_DATA_DIR", "/tmp/swingbot-bt")
    store = SeriesStore(os.path.join(data_dir, "series.db"))
    local_15m = load("BTC/USD", "15m")
    # OKX quotes USDT natively, so no quote remapping is wanted here.
    provider = CcxtProvider(exchange_id="okx", quote_map={})
    start = int(pd.Timestamp("2022-01-01", tz="UTC").timestamp() * 1000)
    end = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
    written = ingest(store, local_15m, provider, start_ms=start, end_ms=end)
    cov = store.coverage("cb_premium", "BTC/USD")
    print(f"[premium] wrote {written} rows; coverage {cov}")


if __name__ == "__main__":
    main()
