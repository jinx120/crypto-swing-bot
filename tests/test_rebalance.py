from swingbot.rebalance import (
    RebalanceSettings,
    StrategyAllocation,
    allocated_equity,
    compute_allocations,
)


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
