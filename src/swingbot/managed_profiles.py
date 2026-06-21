from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Bump when the managed definitions below change in a way that should re-seed.
MANAGED_VERSION = 1

# Every name the reconciler is allowed to create/own. Anything NOT in this set
# is a user profile and must never be deleted or overwritten.
MANAGED_PROFILE_NAMES = {"btc_trend", "eth_trend"}

# UI/labeling metadata so the dashboard can distinguish managed and user strategies.
MANAGED_LABELS = {
    "btc_trend": {"kind": "strategy", "label": "BTC Trend (EMA)"},
    "eth_trend": {"kind": "strategy", "label": "ETH Trend (EMA)"},
}


def managed_meta(name: str) -> dict:
    """UI metadata for a profile: kind (strategy|probe|user) and display label."""
    return MANAGED_LABELS.get(name, {"kind": "user", "label": name})


def _trend_profile(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "benchmark_symbol": "BTC/USD",
        "timeframe": "15m",
        "htf_timeframe": "4h",
        "signals": {"ema_trend": {"weight": 1.0, "fast": 12, "slow": 26, "band": 0.01}},
        "entry_threshold": 0.5,
        "regime_ma_period": 50,
        "allowed_regimes": ["uptrend", "neutral"],
        "atr_period": 14,
        "stop_atr_mult": 1.5,
        "take_profit_atr_mult": 2.0,
        "max_hold_bars": 32,
        "risk_per_trade": 0.01,
        "max_position_frac": 0.25,
    }


def managed_definitions(enable_probe: bool) -> dict[str, dict]:
    """Return name -> profile dict for managed profiles."""
    return {
        "btc_trend": _trend_profile("BTC/USD"),
        "eth_trend": _trend_profile("ETH/USD"),
    }


@dataclass
class ReconcileReport:
    seeded: list[str] = field(default_factory=list)
    upgraded: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    preserved_user: list[str] = field(default_factory=list)
    backup_path: str | None = None
    version_from: int | None = None
    version_to: int = MANAGED_VERSION


def backup_profiles(store, backup_dir: str, now: datetime | None = None) -> str:
    """Dump the full profile set and armed flags before managed mutation."""
    now = now or datetime.now(timezone.utc)
    os.makedirs(backup_dir, exist_ok=True)
    snapshot = {
        "ts": now.isoformat(),
        "profiles": {name: store.get(name) for name in store.list()},
        "armed": list(store.list_armed()),
    }
    path = os.path.join(backup_dir, f"profiles-{now.strftime('%Y%m%dT%H%M%S%f')}.json")
    with open(path, "w") as f:
        json.dump(snapshot, f, indent=2)
    return path


def reconcile_managed_profiles(
    store, *, enable_probe: bool, mode: str, backup_dir: str, now: datetime | None = None
) -> ReconcileReport:
    """Seed or upgrade managed profiles while preserving user profiles."""
    import swingbot.managed_profiles as _self

    prev_version = store.get_meta("managed_version")
    prev_version_int = int(prev_version) if prev_version is not None else None
    prev_names = set(json.loads(store.get_meta("managed_names") or "[]"))

    target = _self.managed_definitions(enable_probe and mode == "paper")
    target_names = set(target)

    seeded: list[str] = []
    upgraded: list[str] = []
    for name, pdict in target.items():
        existing = store.get(name)
        if existing is None:
            seeded.append(name)
        elif existing != pdict:
            upgraded.append(name)

    removed = sorted(prev_names - target_names)
    version_changed = prev_version_int != _self.MANAGED_VERSION
    changed = bool(seeded or upgraded or removed or version_changed)

    report = ReconcileReport(
        seeded=sorted(seeded),
        upgraded=sorted(upgraded),
        removed=removed,
        preserved_user=sorted(set(store.list()) - prev_names - target_names),
        version_from=prev_version_int,
        version_to=_self.MANAGED_VERSION,
    )
    if not changed:
        return report

    report.backup_path = backup_profiles(store, backup_dir, now)

    for name, pdict in target.items():
        store.save(name, pdict)
        store.arm(name)
    for name in removed:
        if store.is_armed(name):
            store.disarm(name)
        store.delete(name)

    store.set_meta("managed_version", str(_self.MANAGED_VERSION))
    store.set_meta("managed_names", json.dumps(sorted(target_names)))
    return report
