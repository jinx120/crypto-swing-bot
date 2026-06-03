from __future__ import annotations

import json
import os
import time

import pandas as pd

from swingbot.backtest import run_backtest
from swingbot.confluence import ConfluenceEngine, build_signals
from swingbot.presets import ARCHETYPES, STYLE, archetype_profile
from swingbot.profile import StrategyProfile
from swingbot.regime import RegimeFilter
from swingbot.strategy_search import _df_from_market, metrics_dict
from swingbot.types import MarketContext

MIN_TRADES = 20


def good_history(metrics: dict) -> bool:
    """Ranked-well predicate: enough trades, positive expectancy, profit factor > 1."""
    nt = metrics.get("n_trades") or 0
    exp = metrics.get("expectancy") or 0
    pf = metrics.get("profit_factor") or 0
    return nt >= MIN_TRADES and exp > 0 and pf > 1


_WINDOW_DEFS = [
    ("full", "Full history", None),
    ("last_1y", "Last 1y", 365),
    ("last_90d", "Last 90d", 90),
    ("last_30d", "Last 30d", 30),
]
_WINDOW_DAYS = {key: days for key, _label, days in _WINDOW_DEFS}


def windows_for(coverage: dict) -> list[dict]:
    """Selectable windows derived from store coverage, so each always has data."""
    min_ts, max_ts = coverage.get("min_ts"), coverage.get("max_ts")
    span_days = ((max_ts - min_ts) / 86400) if (min_ts and max_ts) else 0
    return [{"key": k, "label": lbl, "days": d}
            for k, lbl, d in _WINDOW_DEFS if d is None or span_days >= d]


def _apply_window(df: pd.DataFrame, window_key: str) -> pd.DataFrame:
    days = _WINDOW_DAYS.get(window_key)
    if not days:
        return df
    cutoff = df["ts"].iloc[-1] - pd.Timedelta(days=days)
    return df[df["ts"] >= cutoff].reset_index(drop=True)
