from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Callable


class PriceCache:
    """Per-symbol TTL cache over a last-price fetcher. Multiple clients / a fast
    poll collapse to <=1 upstream call per symbol per `ttl` seconds. On a fetch
    error the last cached value is served with stale=True; never raises."""

    def __init__(self, fetch: Callable[[list[str]], dict],
                 ttl: float = 2.0, clock: Callable[[], float] = time.monotonic):
        self._fetch = fetch
        self._ttl = ttl
        self._clock = clock
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, float, str]] = {}  # sym -> (price, mono_ts, iso)

    def get(self, symbols: list[str]) -> dict:
        now = self._clock()
        stale_syms = [s for s in symbols if self._expired(s, now)]
        if stale_syms:
            try:
                fresh = self._fetch(stale_syms)
                iso = datetime.now(timezone.utc).isoformat()
                with self._lock:
                    for s, price in fresh.items():
                        self._cache[s] = (float(price), now, iso)
            except Exception:
                pass  # serve last cached; stale flag computed below
        out: dict = {}
        with self._lock:
            for s in symbols:
                entry = self._cache.get(s)
                if entry is None:
                    out[s] = {"price": None, "ts": None, "stale": True}
                else:
                    price, mono_ts, iso = entry
                    out[s] = {"price": price, "ts": iso,
                              "stale": (now - mono_ts) > self._ttl}
        return out

    def _expired(self, symbol: str, now: float) -> bool:
        entry = self._cache.get(symbol)
        return entry is None or (now - entry[1]) > self._ttl
