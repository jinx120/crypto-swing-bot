import pandas as pd
import pytest

from lab.walkforward import Window, apply_combo, generate_windows, with_cost
from swingbot.profile import StrategyProfile


def _ts(s):
    return pd.Timestamp(s, tz="UTC")


def test_generate_windows_rolls_forward_by_step():
    ws = generate_windows(_ts("2022-01-01"), _ts("2024-01-01"),
                          train_days=365, test_days=90, step_days=90)
    assert ws[0] == Window(_ts("2022-01-01"), _ts("2023-01-01"),
                           _ts("2023-01-01"), _ts("2023-04-01"))
    assert ws[1].train_start == _ts("2022-04-01")
    # test period always starts exactly where training ended: no gap, no overlap
    assert all(w.test_start == w.train_end for w in ws)


def test_generate_windows_drops_a_window_that_would_run_past_the_data():
    ws = generate_windows(_ts("2022-01-01"), _ts("2023-02-01"),
                          train_days=365, test_days=90, step_days=90)
    assert ws == []  # 2022-01-01 + 365d + 90d = 2023-04-01 > 2023-02-01


def test_generate_windows_rejects_nonpositive_spans():
    with pytest.raises(ValueError):
        generate_windows(_ts("2022-01-01"), _ts("2024-01-01"), train_days=0)


def test_apply_combo_sets_nested_signal_params_and_top_level_fields():
    base = StrategyProfile(symbol="BTC/USD",
                           signals={"ema_trend": {"weight": 1.0, "fast": 21, "slow": 55}},
                           entry_threshold=0.65)
    out = apply_combo(base, {"ema_trend.fast": 8, "ema_trend.slow": 34,
                             "entry_threshold": 0.5})
    assert out.signals["ema_trend"]["fast"] == 8
    assert out.signals["ema_trend"]["slow"] == 34
    assert out.entry_threshold == 0.5
    # the base profile must not be mutated - combos are evaluated in a loop
    assert base.signals["ema_trend"]["fast"] == 21
    assert base.entry_threshold == 0.65


def test_apply_combo_rejects_an_unknown_signal_name():
    base = StrategyProfile(symbol="BTC/USD", signals={"ema_trend": {"weight": 1.0}})
    with pytest.raises(KeyError):
        apply_combo(base, {"funding_mr.high_thresh": 0.1})


def test_with_cost_splits_round_trip_across_both_sides():
    p = with_cost(StrategyProfile(symbol="BTC/USD"), 0.006)
    assert p.fee_rate == 0.003
    assert p.slippage_rate == 0.0
