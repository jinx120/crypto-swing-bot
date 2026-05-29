from __future__ import annotations

from dataclasses import dataclass

from swingbot.journal import Trade


@dataclass
class Metrics:
    n_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    expectancy: float
    profit_factor: float
    max_drawdown: float        # most negative equity dip from running peak (<= 0)


def compute_metrics(trades: list[Trade]) -> Metrics:
    if not trades:
        return Metrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    n = len(pnls)
    win_rate = len(wins) / n
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    expectancy = sum(pnls) / n
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    # max drawdown of the cumulative-pnl equity curve
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        cum += p
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)

    return Metrics(n, win_rate, avg_win, avg_loss, expectancy, profit_factor, max_dd)
