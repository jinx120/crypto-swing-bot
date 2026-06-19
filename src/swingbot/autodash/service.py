from __future__ import annotations

import threading

from swingbot.autodash.backtest_runner import run_comparison
from swingbot.autodash.config import AutoDashConfig
from swingbot.autodash.kronos_factory import build_kronos_signal
from swingbot.autodash import queries

# Returned while the (heavy) backtest is still computing in the background. Valid summary
# shape so the frontend renders an empty/"computing" comparison instead of erroring.
_PENDING_SUMMARY = {"n_trades": 0, "win_rate": 0.0, "total_pnl": 0.0,
                    "sharpe": 0.0, "final_equity": 0.0, "equity_curve": [],
                    "pending": True}
_PENDING_BACKTEST = {"ema": _PENDING_SUMMARY, "kronos": _PENDING_SUMMARY}


def _default_candle_loader(config: AutoDashConfig):
    from swingbot.data.store import CandleStore
    rows = CandleStore(config.history_db).get(
        config.symbol, config.backtest_timeframe, config.backtest_limit)
    # CandleStore yields dicts keyed 'time' (epoch seconds); core_engine's backtest is
    # positional, but the Kronos adapter reads a 'ts' column as a tz-aware Timestamp
    # (it inspects .tzinfo). Add it so the real EMA-vs-Kronos comparison runs.
    import pandas as pd
    for r in rows:
        if "ts" not in r and "time" in r:
            r["ts"] = pd.Timestamp(r["time"], unit="s", tz="UTC")
    return rows


class AutoDashboardService:
    def __init__(self, config: AutoDashConfig, *,
                 comparison_fn=run_comparison,
                 kronos_factory=build_kronos_signal,
                 candle_loader=_default_candle_loader,
                 prewarm: bool = False):
        self._cfg = config
        self._comparison_fn = comparison_fn
        # Real Kronos inference is GPU-bound. Backtesting it bar-by-bar on CPU takes tens
        # of minutes, so when CUDA is unavailable we fall back to the plan's deterministic
        # kronos=None baseline (fast). Only auto-gate the DEFAULT factory; an explicitly
        # injected factory (e.g. tests, or a forced GPU run) is respected as given.
        if kronos_factory is build_kronos_signal:
            from swingbot.autodash.kronos_factory import pick_device
            if pick_device() != "cuda":
                kronos_factory = lambda: None  # noqa: E731
        self._kronos_factory = kronos_factory
        self._candle_loader = candle_loader
        self._cache: dict | None = None
        self._lock = threading.Lock()
        # On a real deployment the comparison runs the heavy (GPU/CPU) Kronos model once;
        # prewarm computes it in the background at startup so the first poll never blocks.
        if prewarm:
            threading.Thread(target=self._prewarm, daemon=True).start()

    def _prewarm(self) -> None:
        try:
            self.backtest()
        except Exception as exc:   # never let a prewarm failure crash anything
            print(f"[autodash] backtest prewarm failed: {type(exc).__name__}: {exc}")

    def backtest(self) -> dict:
        cached = self._cache
        if cached is not None:
            return cached
        # Non-blocking: if another thread (the prewarm) is already computing, return a
        # valid pending placeholder rather than blocking the request for minutes.
        if self._lock.acquire(blocking=False):
            try:
                if self._cache is None:
                    candles = self._candle_loader(self._cfg)
                    self._cache = self._comparison_fn(
                        candles, kronos_factory=self._kronos_factory,
                        equity0=self._cfg.equity0)
                return self._cache
            finally:
                self._lock.release()
        return _PENDING_BACKTEST

    def backtest_ready(self) -> bool:
        return self._cache is not None

    def position(self):
        return queries.live_position(self._cfg.state_db, self._cfg.journal_db)

    def trades(self, limit: int = 50):
        return queries.recent_trades(self._cfg.journal_db, limit)

    def journal(self, limit: int = 50):
        return queries.recent_events(self._cfg.journal_db, limit)

    def candles(self, limit: int = 200):
        return queries.recent_candles(self._cfg.candle_db, self._cfg.symbol,
                                      self._cfg.timeframe, limit)
