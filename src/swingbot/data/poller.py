from __future__ import annotations

import threading
import time

from swingbot.data.market import MarketData
from swingbot.profiles import ProfileStore


class CandlePoller:
    """Periodically refreshes the active profile's symbol/timeframe candles via
    MarketData (Alpaca -> SQLite).

    Runs independently of the trading loop so the dashboard chart always has
    fresh data for the active timeframe, even when the bot is stopped. Other
    timeframes are fetched on demand by the /api/candles endpoint.
    """

    def __init__(self, market: MarketData, profiles: ProfileStore, interval: int = 60):
        self.market = market
        self.profiles = profiles
        self.interval = interval
        self._running = False
        self._thread: threading.Thread | None = None

    def poll_once(self) -> int:
        pdict = self.profiles.get_active()
        if not pdict:
            return 0
        symbol = pdict.get("symbol")
        timeframe = pdict.get("timeframe", "15m")
        if not symbol:
            return 0
        return self.market.refresh(symbol, timeframe)

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
