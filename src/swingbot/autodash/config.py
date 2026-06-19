from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AutoDashConfig:
    core_engine_data: str
    history_db: str
    symbol: str = "BTC/USD"
    timeframe: str = "5m"          # live core-engine candle timeframe (chart + live reads)
    backtest_timeframe: str = "15m"  # timeframe available for BTC/USD in the swingbot archive
    backtest_limit: int = 5000
    equity0: float = 10_000.0

    @classmethod
    def default(cls) -> "AutoDashConfig":
        data = os.environ.get(
            "CORE_ENGINE_DATA", os.path.expanduser("~/.core-engine")
        )
        history = os.environ.get(
            "SWINGBOT_DATA_DIR", os.path.expanduser("~/.swingbot")
        )
        return cls(core_engine_data=data,
                   history_db=os.path.join(history, "candles.db"))

    @property
    def journal_db(self) -> str:
        return os.path.join(self.core_engine_data, "journal.db")

    @property
    def state_db(self) -> str:
        return os.path.join(self.core_engine_data, "state.db")

    @property
    def candle_db(self) -> str:
        return os.path.join(self.core_engine_data, "candles.db")
