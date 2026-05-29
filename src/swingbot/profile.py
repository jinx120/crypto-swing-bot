from __future__ import annotations

from dataclasses import dataclass, field

from swingbot.types import Regime


@dataclass
class StrategyProfile:
    symbol: str
    benchmark_symbol: str = "BTC/USD"
    timeframe: str = "15m"
    htf_timeframe: str = "4h"

    # signal config: name -> params dict (must include "weight")
    signals: dict = field(default_factory=dict)
    entry_threshold: float = 0.6

    # regime gate
    regime_ma_period: int = 200
    allowed_regimes: tuple[Regime, ...] = (Regime.UPTREND, Regime.NEUTRAL)

    # exits
    atr_period: int = 14
    stop_atr_mult: float = 1.5
    take_profit_atr_mult: float = 2.0
    max_hold_bars: int = 32          # 8 hours at 15m

    # sizing / risk
    risk_per_trade: float = 0.01     # 1% of equity
    max_position_frac: float = 0.25  # <=25% of equity in one trade

    # circuit breakers (Phase 2)
    daily_loss_limit_pct: float = 0.05   # halt new entries after -5% day
    max_consecutive_losses: int = 4      # ...or after N losses in a row
    max_concurrent: int = 1              # max simultaneous open positions
    cooldown_minutes: int = 60           # wait after a stop-out before re-entering
    poll_seconds: int = 60               # orchestrator loop interval

    # backtest cost model
    fee_rate: float = 0.0025         # per side
    slippage_rate: float = 0.0005    # per side

    @classmethod
    def from_dict(cls, d: dict) -> "StrategyProfile":
        d = dict(d)
        if "allowed_regimes" in d:
            d["allowed_regimes"] = tuple(Regime(r) for r in d["allowed_regimes"])
        return cls(**d)
