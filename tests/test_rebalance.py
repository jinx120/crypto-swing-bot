from datetime import datetime, timedelta, timezone

from swingbot.rebalance import (
    RebalanceState,
    RebalanceSettings,
    Rebalancer,
    StrategyAllocation,
    allocated_equity,
    compute_allocations,
)

import pandas as pd

from swingbot.rebalance import correlation_clusters, detect_drift, recent_volatility
from swingbot.rebalance import plan_trims


def test_allocated_equity_uses_target_times_total():
    assert allocated_equity("a", {"a": 0.3}, 10_000, n_strategies=2) == 3_000.0


def test_allocated_equity_equal_weight_fallback_when_no_target():
    assert allocated_equity("a", {}, 10_000, n_strategies=4) == 2_500.0


def test_compute_allocations_actual_and_drift():
    allocs = compute_allocations(
        deployed={"a": 4_000.0, "b": 1_000.0},
        symbols={"a": "BTC/USD", "b": "ETH/USD"},
        targets={"a": 0.3, "b": 0.3},
        total_equity=10_000.0,
    )
    by = {x.name: x for x in allocs}
    assert by["a"].actual_weight == 0.4
    assert round(by["a"].drift, 4) == 0.1
    assert round(by["b"].drift, 4) == -0.2


def test_detect_drift_returns_only_overweight_beyond_threshold():
    allocs = compute_allocations(
        deployed={"a": 4_000.0, "b": 2_000.0},
        symbols={"a": "X", "b": "Y"},
        targets={"a": 0.3, "b": 0.3},
        total_equity=10_000.0,
    )
    drifted = detect_drift(allocs, threshold=0.05)
    assert [d.name for d in drifted] == ["a"]


def test_recent_volatility_is_stdev_of_returns():
    s = pd.Series([100, 110, 105, 115, 120], dtype=float)
    rets = s.pct_change().dropna()
    assert abs(recent_volatility(s) - rets.std()) < 1e-9


def test_correlation_clusters_groups_correlated_symbols():
    base = pd.Series([1, 2, 3, 4, 5], dtype=float)
    returns = {
        "A": base.pct_change().dropna(),
        "B": (base * 2).pct_change().dropna(),
        "C": pd.Series([5, 1, 6, 2, 7]).pct_change().dropna(),
    }
    clusters = correlation_clusters(returns, threshold=0.8)
    assert any({"A", "B"} <= c for c in clusters)


def _alloc(name, sym, target, deployed, total):
    return compute_allocations({name: deployed}, {name: sym}, {name: target}, total)[0]


def test_plan_trims_minimal_trim_to_just_under_band():
    a = _alloc("a", "BTC/USD", 0.3, 5_000.0, 10_000.0)
    s = RebalanceSettings(
        drift_threshold=0.05,
        vol_skip_threshold=1.0,
        fee_rate=0.0,
        benefit_factor=0.0,
    )
    rets = {"BTC/USD": pd.Series([1, 2, 3, 4, 5]).pct_change().dropna()}
    trims, skips = plan_trims([a], [a], {"BTC/USD": 100.0}, 10_000.0, s, rets)
    assert len(trims) == 1
    assert round(trims[0].value, 2) == 1_500.0
    assert round(trims[0].qty, 4) == 15.0


def test_plan_trims_skips_on_high_volatility():
    a = _alloc("a", "BTC/USD", 0.3, 5_000.0, 10_000.0)
    s = RebalanceSettings(
        drift_threshold=0.05,
        vol_skip_threshold=0.0001,
        fee_rate=0.0,
        benefit_factor=0.0,
    )
    rets = {"BTC/USD": pd.Series([1, 5, 2, 9, 3]).pct_change().dropna()}
    trims, skips = plan_trims([a], [a], {"BTC/USD": 100.0}, 10_000.0, s, rets)
    assert trims == []
    assert any("volatil" in r for r in skips)


def test_plan_trims_skips_when_below_min_notional():
    a = _alloc("a", "BTC/USD", 0.3, 3_600.0, 10_000.0)
    s = RebalanceSettings(
        drift_threshold=0.05,
        vol_skip_threshold=1.0,
        fee_rate=0.0025,
        benefit_factor=10.0,
    )
    rets = {"BTC/USD": pd.Series([1, 2, 3, 4, 5]).pct_change().dropna()}
    trims, skips = plan_trims([a], [a], {"BTC/USD": 100.0}, 10_000.0, s, rets)
    assert trims == []
    assert any("fee" in r for r in skips)


def _now():
    return datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)


def test_evaluate_min_interval_skips():
    st = RebalanceState(last_rebalance_at=_now().isoformat())
    r = Rebalancer(
        RebalanceSettings(enabled=True, mode="hard", min_interval_minutes=60),
        st,
    )
    res = r.evaluate(
        now=_now() + timedelta(minutes=30),
        total_equity=10_000.0,
        deployed={"a": 5_000.0},
        symbols={"a": "BTC/USD"},
        targets={"a": 0.3},
        prices={"BTC/USD": 100.0},
        returns_by_symbol={},
    )
    assert res.ran is False
    assert "interval" in res.skipped_reason


def test_evaluate_soft_mode_returns_no_trims():
    r = Rebalancer(RebalanceSettings(enabled=True, mode="soft"), RebalanceState())
    res = r.evaluate(
        now=_now(),
        total_equity=10_000.0,
        deployed={"a": 5_000.0},
        symbols={"a": "BTC/USD"},
        targets={"a": 0.3},
        prices={"BTC/USD": 100.0},
        returns_by_symbol={},
    )
    assert res.ran is True
    assert res.trims == []
    assert res.mode == "soft"


def test_evaluate_hard_mode_emits_trim():
    rets = {"BTC/USD": pd.Series([1, 2, 3, 4, 5]).pct_change().dropna()}
    r = Rebalancer(
        RebalanceSettings(
            enabled=True,
            mode="hard",
            vol_skip_threshold=1.0,
            fee_rate=0.0,
            benefit_factor=0.0,
        ),
        RebalanceState(),
    )
    res = r.evaluate(
        now=_now(),
        total_equity=10_000.0,
        deployed={"a": 5_000.0},
        symbols={"a": "BTC/USD"},
        targets={"a": 0.3},
        prices={"BTC/USD": 100.0},
        returns_by_symbol=rets,
    )
    assert res.ran is True
    assert len(res.trims) == 1
