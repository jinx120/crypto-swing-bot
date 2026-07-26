"""Walk-forward validation for candidate trading signals.

Method: split history into rolling (train, test) window pairs. Inside each
window, pick the best parameter combination on the TRAIN slice only, then trade
that frozen combination through the TEST slice. Concatenating the test slices
gives a single out-of-sample record with no in-sample parameter fitting in it.

Every backtest runs through the validated `run_backtest_fast` (bit-for-bit equal
to production `run_backtest`), so the exits, sizing and broker are the real ones.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import pandas as pd

from swingbot.profile import StrategyProfile


@dataclass(frozen=True)
class Window:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def generate_windows(first_ts, last_ts, train_days: int = 365,
                     test_days: int = 90, step_days: int = 90) -> list[Window]:
    """Rolling train/test splits covering [first_ts, last_ts].

    A window is emitted only if its full test period fits inside the data, so a
    truncated final window can never inflate or deflate the out-of-sample record.
    """
    if train_days <= 0 or test_days <= 0 or step_days <= 0:
        raise ValueError("train_days, test_days and step_days must all be > 0")
    first, last = pd.Timestamp(first_ts), pd.Timestamp(last_ts)
    train_len = pd.Timedelta(days=train_days)
    test_len = pd.Timedelta(days=test_days)
    step = pd.Timedelta(days=step_days)

    windows: list[Window] = []
    train_start = first
    while True:
        train_end = train_start + train_len
        test_end = train_end + test_len
        if test_end > last:
            return windows
        windows.append(Window(train_start, train_end, train_end, test_end))
        train_start = train_start + step


def apply_combo(profile: StrategyProfile, combo: dict) -> StrategyProfile:
    """Return a COPY of `profile` with a parameter combination applied.

    Dotted keys ("ema_trend.fast") set a param inside profile.signals; bare keys
    ("entry_threshold") set a top-level profile field. The input profile and its
    nested signal dicts are never mutated, so a combo loop stays independent.
    """
    signals = {name: dict(params) for name, params in profile.signals.items()}
    top: dict = {}
    for key, value in combo.items():
        if "." in key:
            signal_name, param = key.split(".", 1)
            if signal_name not in signals:
                raise KeyError(f"combo targets unknown signal {signal_name!r}")
            signals[signal_name][param] = value
        else:
            top[key] = value
    return dataclasses.replace(profile, signals=signals, **top)


def with_cost(profile: StrategyProfile, round_trip: float) -> StrategyProfile:
    """Set the total round-trip cost, charged symmetrically as fees."""
    return dataclasses.replace(profile, fee_rate=round_trip / 2.0, slippage_rate=0.0)
