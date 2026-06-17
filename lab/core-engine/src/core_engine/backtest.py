from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import pandas as pd
from swingbot.exits import exit_decision
from swingbot.types import MarketContext
from swingbot.risk import RiskManager, RiskState
from core_engine.contracts import Action
from core_engine.brain import decide
from core_engine.risk_gate import build_order_intent


@dataclass(frozen=True)
class BacktestResult:
    trades: list[dict]
    final_equity: float
    wins: int
    losses: int


def _atr(window: pd.DataFrame, n: int = 14) -> float:
    hl = (window["high"] - window["low"]).tail(n)
    return float(hl.mean()) if len(hl) else 1.0


def run_backtest(candles: pd.DataFrame, *, profile, kronos,
                 equity0: float = 10_000.0) -> BacktestResult:
    equity = equity0
    pos = None
    trades: list[dict] = []
    risk = RiskManager(profile, RiskState())
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    risk.start_day(start, equity)

    for i in range(30, len(candles)):
        window = candles.iloc[: i + 1]
        bar = candles.iloc[i]
        now = start
        if pos is not None:
            ex = exit_decision(pos["stop"], pos["tp"], pos["max_hold_until"],
                               float(bar["high"]), float(bar["low"]),
                               float(bar["close"]), now)
            if ex is not None:
                reason, price = ex
                pnl = (price - pos["entry_price"]) * pos["qty"]
                equity += pnl
                trades.append({"pnl": pnl, "reason": str(reason), "won": pnl > 0})
                pos = None
            continue
        d = decide(MarketContext(candles=window), has_position=False,
                   profile=profile, kronos=kronos)
        if d.action is Action.ENTER_LONG:
            oi = build_order_intent(d, symbol="BTC/USD", now=now, equity=equity,
                                    entry_price=float(bar["close"]),
                                    atr=_atr(window), risk=risk, profile=profile)
            if oi is not None:
                pos = {"entry_price": oi.entry_price, "qty": oi.qty, "stop": oi.stop,
                       "tp": oi.tp, "max_hold_until": oi.max_hold_until}

    wins = sum(1 for t in trades if t["won"])
    return BacktestResult(trades=trades, final_equity=equity,
                          wins=wins, losses=len(trades) - wins)
