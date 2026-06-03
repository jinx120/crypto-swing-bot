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


def _rank_key(row: dict):
    m = row.get("metrics") or {}
    return (m.get("expectancy") or -1e9, m.get("win_rate") or 0, m.get("n_trades") or 0)


class DiscoveryEngine:
    """Sweeps symbols across the non-AI archetypes over the deep archive,
    ranking by expectancy. Pure compute — caching/threading live in web.py."""

    def __init__(self, market, lookback: int = 100_000):
        self.market = market
        self.lookback = lookback

    def _candidates(self, symbol: str, style: str) -> list[tuple]:
        return [(a.key, a.name, archetype_profile(a, symbol, style))
                for a in ARCHETYPES if not a.needs_ai]

    def _now_state(self, profile: StrategyProfile, df, bench) -> tuple[bool, bool, str]:
        ctx = MarketContext(candles=df, benchmark=bench)
        regime = RegimeFilter(profile)
        reg = regime.evaluate(ctx)
        engine = ConfluenceEngine(build_signals(profile), profile)
        return regime.permits_entry(reg.regime), bool(engine.evaluate(ctx).passed), reg.regime.value

    def _err_row(self, symbol, key, label, profile, err) -> dict:
        return {"symbol": symbol, "archetype": key, "label": label, "profile": profile,
                "metrics": None, "eligible_now": False, "fires_now": False,
                "regime": None, "error": str(err)}

    def sweep(self, symbols, window_key="full", style="swing", max_symbols=50) -> list[dict]:
        timeframe = STYLE[style]["timeframe"]
        rows: list[dict] = []
        for symbol in list(symbols)[:max_symbols]:
            try:
                df = _apply_window(
                    _df_from_market(self.market, symbol, timeframe, self.lookback), window_key)
            except Exception as e:                       # InsufficientData / load failure
                rows.append(self._err_row(symbol, None, None, None, e))
                continue
            bench = None
            for key, name, profile_dict in self._candidates(symbol, style):
                needs_bench = "relative_strength" in profile_dict["signals"]
                try:
                    if needs_bench and bench is None:
                        bench = _apply_window(
                            _df_from_market(self.market, profile_dict["benchmark_symbol"],
                                            timeframe, self.lookback), window_key)
                    b = bench if needs_bench else None
                    profile = StrategyProfile.from_dict(profile_dict)
                    _trades, m = run_backtest(df, profile, benchmark_df=b)
                    mrow = metrics_dict(m)
                    regime_ok, fires, regime = self._now_state(profile, df, b)
                    rows.append({"symbol": symbol, "archetype": key, "label": name,
                                 "profile": profile_dict, "metrics": mrow,
                                 "eligible_now": good_history(mrow) and regime_ok,
                                 "fires_now": fires, "regime": regime, "error": None})
                except Exception as e:                   # one bad candidate never aborts
                    rows.append(self._err_row(symbol, key, name, profile_dict, e))
        rows.sort(key=_rank_key, reverse=True)
        return rows


def load_cache(path: str) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_cache(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)                              # atomic on POSIX
