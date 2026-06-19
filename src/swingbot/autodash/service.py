from __future__ import annotations

import threading

from swingbot.autodash.backtest_runner import run_comparison
from swingbot.autodash.config import AutoDashConfig
from swingbot.autodash.kronos_factory import build_kronos_signal
from swingbot.autodash import queries


def _default_candle_loader(config: AutoDashConfig):
    from swingbot.data.store import CandleStore
    rows = CandleStore(config.history_db).get(
        config.symbol, config.timeframe, config.backtest_limit)
    return rows


class AutoDashboardService:
    def __init__(self, config: AutoDashConfig, *,
                 comparison_fn=run_comparison,
                 kronos_factory=build_kronos_signal,
                 candle_loader=_default_candle_loader):
        self._cfg = config
        self._comparison_fn = comparison_fn
        self._kronos_factory = kronos_factory
        self._candle_loader = candle_loader
        self._cache: dict | None = None
        self._lock = threading.Lock()

    def backtest(self) -> dict:
        with self._lock:
            if self._cache is None:
                candles = self._candle_loader(self._cfg)
                self._cache = self._comparison_fn(
                    candles, kronos_factory=self._kronos_factory,
                    equity0=self._cfg.equity0)
            return self._cache

    def position(self):
        return queries.live_position(self._cfg.state_db, self._cfg.journal_db)

    def trades(self, limit: int = 50):
        return queries.recent_trades(self._cfg.journal_db, limit)

    def journal(self, limit: int = 50):
        return queries.recent_events(self._cfg.journal_db, limit)

    def candles(self, limit: int = 200):
        return queries.recent_candles(self._cfg.candle_db, self._cfg.symbol,
                                      self._cfg.timeframe, limit)
