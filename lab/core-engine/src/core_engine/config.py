from __future__ import annotations
import os
from swingbot.profile import StrategyProfile

SYMBOL = "BTC/USD"
TIMEFRAME = "5Min"
LOOP_SECONDS = 300

_DATA_DIR = os.environ.get("CORE_ENGINE_DATA", os.path.expanduser("~/.core-engine"))
os.makedirs(_DATA_DIR, exist_ok=True)
CANDLE_DB = os.path.join(_DATA_DIR, "candles.db")
STATE_DB = os.path.join(_DATA_DIR, "state.db")
JOURNAL_DB = os.path.join(_DATA_DIR, "journal.db")

PROFILE = StrategyProfile(
    symbol=SYMBOL,
    benchmark_symbol=SYMBOL,
    timeframe=TIMEFRAME,
    signals={"ema_trend": {"weight": 1.0, "fast": 12, "slow": 26, "band": 0.01}},
    entry_threshold=0.6,
    stop_atr_mult=1.5,
    take_profit_atr_mult=2.0,
    max_hold_bars=32,
    risk_per_trade=0.01,
    max_position_frac=0.25,
    poll_seconds=LOOP_SECONDS,
)
