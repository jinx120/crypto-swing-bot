from __future__ import annotations

import math
from dataclasses import dataclass, asdict

import pandas as pd
from core_engine.backtest import BacktestResult
from core_engine.backtest import run_backtest as _ce_run_backtest
from core_engine.config import PROFILE as _DEFAULT_PROFILE


@dataclass(frozen=True)
class BacktestSummary:
    n_trades: int
    win_rate: float
    total_pnl: float
    sharpe: float
    final_equity: float
    equity_curve: list[float]

    def to_dict(self) -> dict:
        return asdict(self)


def summarize(result: BacktestResult, equity0: float) -> BacktestSummary:
    pnls = [float(t["pnl"]) for t in result.trades]
    n = len(pnls)
    if n == 0:
        return BacktestSummary(0, 0.0, 0.0, 0.0, equity0, [equity0])

    win_rate = sum(1 for p in pnls if p > 0) / n
    total_pnl = sum(pnls)

    equity = equity0
    curve = [equity0]
    for p in pnls:
        equity += p
        curve.append(equity)

    mean = total_pnl / n
    var = sum((p - mean) ** 2 for p in pnls) / n
    std = math.sqrt(var)
    sharpe = (mean / std) * math.sqrt(n) if std > 0 else 0.0

    return BacktestSummary(n, win_rate, total_pnl, sharpe,
                           result.final_equity, curve)


def run_comparison(candles, *, profile=None, kronos_factory=None,
                   equity0: float = 10_000.0) -> dict:
    profile = profile or _DEFAULT_PROFILE
    if not isinstance(candles, pd.DataFrame):
        candles = pd.DataFrame(candles)

    ema_res = _ce_run_backtest(candles, profile=profile, kronos=None,
                               equity0=equity0)
    kronos = kronos_factory() if kronos_factory is not None else None
    kronos_res = _ce_run_backtest(candles, profile=profile, kronos=kronos,
                                  equity0=equity0)

    return {
        "ema": summarize(ema_res, equity0).to_dict(),
        "kronos": summarize(kronos_res, equity0).to_dict(),
    }
