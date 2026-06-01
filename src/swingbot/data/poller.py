from __future__ import annotations

import threading
import time

from swingbot.data.market import MarketData
from swingbot.profiles import ProfileStore


class CandlePoller:
    """Periodically refreshes candles for all armed symbols via MarketData
    (Alpaca -> SQLite), grouped by timeframe into batched fetches.

    Runs independently of the trading loop so the dashboard charts always have
    fresh data for every armed strategy, even when the bot is stopped.
    """

    def __init__(self, market: MarketData, profiles: ProfileStore, interval: int = 60):
        self.market = market
        self.profiles = profiles
        self.interval = interval
        self._running = False
        self._thread: threading.Thread | None = None

    def poll_once(self) -> int:
        names = self.profiles.list_armed()
        by_tf: dict[str, set[str]] = {}
        for name in names:
            pdict = self.profiles.get(name)
            if not pdict or not pdict.get("symbol"):
                continue
            by_tf.setdefault(pdict.get("timeframe", "15m"), set()).add(pdict["symbol"])
        total = 0
        for tf, syms in by_tf.items():
            total += self.market.refresh_many(sorted(syms), tf)
        return total

    def start(self) -> None:
        if self._running:
            return
        self._running = True

        def loop():
            while self._running:
                try:
                    self.poll_once()
                except Exception as e:  # network/credential hiccups must not kill the thread
                    print(f"[candle-poller] {e}")
                for _ in range(self.interval):  # 1s steps so stop() stays responsive
                    if not self._running:
                        break
                    time.sleep(1)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
