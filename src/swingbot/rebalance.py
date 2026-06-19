from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RebalanceSettings:
    enabled: bool = False
    mode: str = "soft"
    drift_threshold: float = 0.05
    min_interval_minutes: int = 1440
    vol_skip_threshold: float = 0.05
    vol_lookback: int = 24
    fee_rate: float = 0.0025
    benefit_factor: float = 1.0
    correlation_threshold: float = 0.8
    cash_buffer_frac: float = 0.0


@dataclass(frozen=True)
class StrategyAllocation:
    name: str
    symbol: str
    target_weight: float
    deployed_value: float
    actual_weight: float
    drift: float


@dataclass
class RebalanceState:
    last_rebalance_at: str = ""


@dataclass(frozen=True)
class TrimAction:
    name: str
    symbol: str
    qty: float
    value: float
    reason: str


@dataclass(frozen=True)
class RebalanceResult:
    ran: bool
    skipped_reason: str
    allocations: list[StrategyAllocation]
    trims: list[TrimAction]
    mode: str


def allocated_equity(
    name: str,
    targets: dict,
    total_equity: float,
    n_strategies: int,
) -> float:
    weight = targets.get(name)
    if weight is None:
        weight = (1.0 / n_strategies) if n_strategies else 0.0
    return weight * total_equity


def compute_allocations(
    deployed: dict,
    symbols: dict,
    targets: dict,
    total_equity: float,
) -> list[StrategyAllocation]:
    n = len(deployed)
    out = []
    for name in sorted(deployed):
        deployed_value = deployed[name]
        target = targets.get(name, (1.0 / n) if n else 0.0)
        actual = (deployed_value / total_equity) if total_equity else 0.0
        out.append(
            StrategyAllocation(
                name=name,
                symbol=symbols.get(name, ""),
                target_weight=target,
                deployed_value=deployed_value,
                actual_weight=actual,
                drift=actual - target,
            )
        )
    return out
