from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd


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


def detect_drift(
    allocations: list[StrategyAllocation],
    threshold: float,
) -> list[StrategyAllocation]:
    return [a for a in allocations if a.drift > threshold]


def recent_volatility(prices: pd.Series) -> float:
    rets = prices.pct_change().dropna()
    if len(rets) < 2:
        return 0.0
    return float(rets.std())


def correlation_clusters(
    returns_by_symbol: dict[str, pd.Series],
    threshold: float,
) -> list[set[str]]:
    symbols = sorted(returns_by_symbol)
    clusters: list[set[str]] = []
    for symbol in symbols:
        placed = False
        for cluster in clusters:
            rep = next(iter(cluster))
            corr = returns_by_symbol[symbol].corr(returns_by_symbol[rep])
            if pd.notna(corr) and corr >= threshold:
                cluster.add(symbol)
                placed = True
                break
        if not placed:
            clusters.append({symbol})
    return clusters


def plan_trims(
    drifted: list[StrategyAllocation],
    all_allocations: list[StrategyAllocation],
    prices: dict,
    total_equity: float,
    settings: RebalanceSettings,
    returns_by_symbol: dict,
) -> tuple[list[TrimAction], list[str]]:
    trims: list[TrimAction] = []
    skips: list[str] = []
    min_trim_notional = (
        settings.benefit_factor * 2 * settings.fee_rate * total_equity
    )

    clusters = correlation_clusters(returns_by_symbol, settings.correlation_threshold)
    under_by_symbol = {a.symbol: a for a in all_allocations if a.drift < 0}

    for allocation in drifted:
        returns = returns_by_symbol.get(allocation.symbol)
        if (
            returns is not None
            and recent_volatility(returns) > settings.vol_skip_threshold
        ):
            skips.append(f"{allocation.name}: high volatility")
            continue

        ceiling = (
            allocation.target_weight + settings.drift_threshold
        ) * total_equity
        trim_value = allocation.deployed_value - ceiling

        cluster = next(
            (c for c in clusters if allocation.symbol in c),
            {allocation.symbol},
        )
        offset = sum(
            -under_by_symbol[s].drift * total_equity
            for s in cluster
            if s in under_by_symbol
        )
        trim_value = max(0.0, trim_value - offset)

        if trim_value < min_trim_notional or trim_value <= 0:
            skips.append(f"{allocation.name}: below fee/benefit floor")
            continue

        price = prices.get(allocation.symbol, 0.0)
        if price <= 0:
            skips.append(f"{allocation.name}: no price")
            continue

        trims.append(
            TrimAction(
                name=allocation.name,
                symbol=allocation.symbol,
                qty=trim_value / price,
                value=trim_value,
                reason=f"drift {allocation.drift:.3f} > {settings.drift_threshold}",
            )
        )
    return trims, skips


class Rebalancer:
    """Pure rebalancing logic over a mutable RebalanceState. No IO."""

    def __init__(self, settings: RebalanceSettings, state: RebalanceState):
        self.settings = settings
        self.state = state

    def _interval_ok(self, now: datetime) -> bool:
        if not self.state.last_rebalance_at:
            return True
        last = datetime.fromisoformat(self.state.last_rebalance_at)
        return now - last >= timedelta(minutes=self.settings.min_interval_minutes)

    def mark_ran(self, now: datetime) -> None:
        self.state.last_rebalance_at = now.isoformat()

    def evaluate(
        self,
        *,
        now,
        total_equity,
        deployed,
        symbols,
        targets,
        prices,
        returns_by_symbol,
    ) -> RebalanceResult:
        allocations = compute_allocations(deployed, symbols, targets, total_equity)
        if not self._interval_ok(now):
            return RebalanceResult(
                False,
                "min interval not elapsed",
                allocations,
                [],
                self.settings.mode,
            )
        if self.settings.mode != "hard":
            return RebalanceResult(True, "", allocations, [], "soft")
        drifted = detect_drift(allocations, self.settings.drift_threshold)
        trims, _skips = plan_trims(
            drifted,
            allocations,
            prices,
            total_equity,
            self.settings,
            returns_by_symbol,
        )
        return RebalanceResult(True, "", allocations, trims, "hard")
