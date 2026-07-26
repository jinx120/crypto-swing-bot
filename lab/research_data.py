"""Shared data helpers for the signal-research runners.

Everything here is causal: a bar never sees a value stamped after its own ts.
`load`/`align` are re-exported from the validated 2026-06 harness so the research
runners have a single import surface.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lab.strategy_backtest import align, load  # noqa: F401  (re-export)

EXTRA_PREFIX = "x_"
_OHLCV = ["ts", "open", "high", "low", "close", "volume"]


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample OHLCV bars to a coarser timeframe (e.g. 15m -> '4h')."""
    d = df.set_index("ts")
    out = d.resample(rule).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return out.dropna().reset_index()


def attach_extra(df: pd.DataFrame, key: str, series_df: pd.DataFrame) -> pd.DataFrame:
    """Merge a (ts, value) series onto bars as column `x_<key>`.

    Uses a BACKWARD as-of join: each bar carries the most recent reading at or
    before its own timestamp, so there is no lookahead. Bars earlier than the
    first reading get NaN, which every consumer maps to a neutral 0.5 score.
    """
    right = series_df.sort_values("ts")[["ts", "value"]].rename(
        columns={"value": EXTRA_PREFIX + key})
    return pd.merge_asof(df.sort_values("ts"), right, on="ts", direction="backward")


def split_extras(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    """Split a frame built by attach_extra back into (OHLCV frame, extras arrays).

    Windowing/slicing happens on the combined frame so extras can never fall out
    of alignment with the bars they were joined to.
    """
    extras = {
        c[len(EXTRA_PREFIX):]: df[c].to_numpy(dtype=float)
        for c in df.columns if c.startswith(EXTRA_PREFIX)
    }
    return df[_OHLCV].reset_index(drop=True), extras
