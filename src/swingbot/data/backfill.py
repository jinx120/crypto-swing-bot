from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from swingbot.data.market import timeframe_seconds
from swingbot.data.store import CandleStore


def _default_symbols() -> list[str]:
    return ["BTC/USD", "ETH/USD", "SOL/USD"]


def _default_timeframes() -> list[str]:
    return ["5m", "15m", "1h"]


@dataclass
class ArchiveConfig:
    """Which markets to archive and how far back. CLI args / env override these."""
    exchange: str = "binance"
    symbols: list[str] = field(default_factory=_default_symbols)
    timeframes: list[str] = field(default_factory=_default_timeframes)
    history_start: str = "2024-06-01"     # ISO date; ~2y of depth by default
    quote_map: dict | None = None
    symbol_overrides: dict | None = None

    def start_ms(self) -> int:
        dt = datetime.fromisoformat(self.history_start).replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


class Backfiller:
    """Populate CandleStore with deep history. Coverage-driven and idempotent:
    on each (symbol, timeframe) it fetches only the ranges not already stored,
    so a re-run fills gaps and a crash mid-run is safe to resume."""

    def __init__(self, store: CandleStore, provider=None):
        self.store = store
        self.provider = provider

    def _missing_ranges(self, symbol: str, timeframe: str,
                        start_ms: int, end_ms: int) -> list[tuple[int, int]]:
        cov = self.store.coverage(symbol, timeframe)
        if not cov["count"]:
            return [(start_ms, end_ms)]
        step_ms = timeframe_seconds(timeframe) * 1000
        min_ms = cov["min_ts"] * 1000
        max_ms = cov["max_ts"] * 1000
        ranges = []
        # Step one bar past the covered edge so we never re-fetch a stored bar
        # (upsert counts rows written, so overlap would inflate the total).
        if start_ms < min_ms:
            ranges.append((start_ms, min_ms - step_ms))      # older gap
        if end_ms > max_ms:
            ranges.append((max_ms + step_ms, end_ms))        # newer gap (top-up)
        return [(s, e) for s, e in ranges if e >= s]

    def run(self, cfg: ArchiveConfig, end_ms: int | None = None,
            log=print) -> int:
        end_ms = end_ms or _now_ms()
        start_ms = cfg.start_ms()
        total = 0
        for symbol in cfg.symbols:
            for tf in cfg.timeframes:
                for r_start, r_end in self._missing_ranges(symbol, tf, start_ms, end_ms):
                    df = self.provider.get_candles_range(symbol, tf, r_start, r_end)
                    written = self.store.upsert_df(symbol, tf, df)
                    total += written
                cov = self.store.coverage(symbol, tf)
                log(f"[backfill] {symbol} {tf}: {cov['count']} bars "
                    f"({cov['min_ts']} -> {cov['max_ts']})")
        return total
