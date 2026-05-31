from __future__ import annotations

import pandas as pd

from swingbot.backtest import run_backtest
from swingbot.presets import build_candidates
from swingbot.profile import StrategyProfile

_CANON = ["ts", "open", "high", "low", "close", "volume"]


class InsufficientData(Exception):
    pass


def _df_from_market(market, symbol: str, timeframe: str, lookback: int) -> pd.DataFrame:
    bars = market.get(symbol, timeframe, lookback)
    if len(bars) < 30:
        raise InsufficientData(
            f"only {len(bars)} bars for {symbol} {timeframe}; need >=30 to backtest")
    df = pd.DataFrame(bars).rename(columns={"time": "ts"})
    df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df[_CANON].sort_values("ts").reset_index(drop=True)


def metrics_dict(m) -> dict:
    """Serialize a Metrics object defensively (unknown fields -> None)."""
    keys = ["n_trades", "win_rate", "expectancy", "profit_factor",
            "max_drawdown", "avg_win", "avg_loss", "total_return"]
    return {k: getattr(m, k, None) for k in keys}


def backtest_profile(market, profile_dict: dict, lookback: int = 1000):
    """Run one profile through the real backtest over cached candles. Returns Metrics."""
    profile = StrategyProfile.from_dict(profile_dict)
    df = _df_from_market(market, profile.symbol, profile.timeframe, lookback)
    bench = None
    if "relative_strength" in profile.signals:
        bench = _df_from_market(market, profile.benchmark_symbol, profile.timeframe, lookback)
    _trades, metrics = run_backtest(df, profile, benchmark_df=bench)
    return metrics


def search(market, symbol: str, risk: str, style: str, ai: bool = False,
           lookback: int = 1000) -> dict:
    """Backtest a bounded candidate set and rank by expectancy."""
    candidates = build_candidates(symbol, risk, style, ai)
    rows = []
    for c in candidates:
        try:
            m = backtest_profile(market, c["profile"], lookback)
            rows.append({"label": c["label"], "profile": c["profile"], "metrics": m, "error": None})
        except Exception as e:  # one bad candidate never aborts the search
            rows.append({"label": c["label"], "profile": c["profile"], "metrics": None, "error": str(e)})

    ok = [r for r in rows if r["metrics"] is not None]
    ok.sort(key=lambda r: (r["metrics"].expectancy, r["metrics"].win_rate, r["metrics"].n_trades),
            reverse=True)
    bad = [r for r in rows if r["metrics"] is None]

    out = []
    for i, r in enumerate(ok + bad):
        out.append({
            "label": r["label"], "profile": r["profile"],
            "metrics": metrics_dict(r["metrics"]) if r["metrics"] is not None else None,
            "error": r["error"], "recommended": r["metrics"] is not None and i == 0,
        })
    return {"symbol": symbol, "risk": risk, "style": style, "ai": ai, "results": out}
