import dataclasses

import pandas as pd
import pytest

from lab.research_data import series_agreement
from lab.research_exit_geometry_daily import select_train_days
from lab.walkforward import Window, apply_combo, generate_windows, with_cost
from swingbot.profile import StrategyProfile
from lab.walkforward import (
    WalkForwardResult, WindowResult, breakeven_cost, phase_gate_verdict,
    profit_factor, promotion_verdict, walk_forward,
)


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


class _FakeTrade:
    """Minimal stand-in for swingbot.journal.Trade for gate arithmetic."""

    def __init__(self, entry_ts, pnl, entry_price=100.0, qty=1.0):
        self.entry_ts = entry_ts
        self.exit_ts = entry_ts + pd.Timedelta(hours=4)
        self.pnl = pnl
        self.entry_price = entry_price
        self.qty = qty


def _result(pnls_by_window, label="x", symbol="BTC/USD"):
    windows, oos = [], []
    for i, pnls in enumerate(pnls_by_window):
        start = _ts("2023-01-01") + pd.Timedelta(days=90 * i)
        trades = [_FakeTrade(start + pd.Timedelta(hours=j), p) for j, p in enumerate(pnls)]
        oos.extend(trades)
        windows.append(WindowResult(
            window=Window(start, start, start, start + pd.Timedelta(days=90)),
            combo={}, train_pf=1.5, trades=trades, net_pnl=sum(pnls)))
    return WalkForwardResult(label=label, symbol=symbol, windows=windows, oos_trades=oos)


def test_profit_factor_is_gross_profit_over_gross_loss():
    assert profit_factor([_FakeTrade(_ts("2023-01-01"), 30.0),
                          _FakeTrade(_ts("2023-01-02"), -10.0)]) == 3.0


def test_profit_factor_of_no_trades_is_zero():
    assert profit_factor([]) == 0.0


def test_promotion_verdict_promotes_a_profitable_consistent_signal():
    # 4 windows, all positive, PF = 400/100 = 4.0, 40 trades
    v = promotion_verdict(_result([[20.0] * 5 + [-5.0] * 5] * 4))
    assert v.decision == "PROMOTE"
    assert v.n_trades == 40
    assert v.profit_factor == 4.0
    assert v.positive_window_frac == 1.0


def test_promotion_verdict_rejects_when_too_few_trades():
    v = promotion_verdict(_result([[20.0] * 5]))
    assert v.decision == "REJECT"
    assert "trades" in v.reason


def test_promotion_verdict_rejects_a_profitable_signal_carried_by_one_window():
    # window 1 huge winner, windows 2-4 losers -> PF passes but consistency fails
    v = promotion_verdict(_result([[100.0] * 10, [-1.0] * 10, [-1.0] * 10, [-1.0] * 10]))
    assert v.decision == "REJECT"
    assert "window" in v.reason


def test_promotion_verdict_rejects_negative_net_return():
    v = promotion_verdict(_result([[5.0, -20.0] * 6, [5.0, -20.0] * 6,
                                   [5.0, -20.0] * 6, [5.0, -20.0] * 6]))
    assert v.decision == "REJECT"


def test_walk_forward_never_trains_and_tests_on_the_same_bars(monkeypatch):
    """The recorded out-of-sample trades must all fall inside test periods."""
    import lab.walkforward as wf

    seen_ranges = []

    def fake_run(df, profile, benchmark_df=None, starting_equity=1000.0,
                 kronos_pct=None, extras=None):
        seen_ranges.append((df["ts"].iloc[0], df["ts"].iloc[-1]))
        mid = df["ts"].iloc[len(df) // 2]
        return [_FakeTrade(mid, 1.0) for _ in range(25)], None

    monkeypatch.setattr(wf, "run_backtest_fast", fake_run)

    ts = pd.date_range("2022-01-01", periods=365 * 3 * 6, freq="4h", tz="UTC")
    df = pd.DataFrame({"ts": ts, "open": 100.0, "high": 101.0, "low": 99.0,
                       "close": 100.0, "volume": 1.0})
    base = StrategyProfile(symbol="BTC/USD",
                           signals={"ema_trend": {"weight": 1.0, "fast": 21, "slow": 55}})
    res = walk_forward(df, base, [{"ema_trend.fast": 8}, {"ema_trend.fast": 21}],
                       round_trip=0.006)

    assert len(res.windows) >= 4
    for w in res.windows:
        for t in w.trades:
            assert w.window.test_start <= t.entry_ts <= w.window.test_end


def test_breakeven_cost_returns_last_tier_before_pf_drops_below_one():
    pf = {0.0: 1.30, 0.0025: 1.15, 0.0050: 1.02, 0.0060: 0.97, 0.0080: 0.90}
    assert breakeven_cost(pf) == 0.0050


def test_breakeven_cost_includes_a_tier_sitting_exactly_at_one():
    pf = {0.0: 1.20, 0.0050: 1.00, 0.0060: 0.95}
    assert breakeven_cost(pf) == 0.0050


def test_breakeven_cost_returns_highest_tier_when_pf_never_drops_below_one():
    pf = {0.0: 1.40, 0.0050: 1.25, 0.0080: 1.10}
    assert breakeven_cost(pf) == 0.0080


def test_breakeven_cost_is_none_when_there_is_no_gross_edge():
    pf = {0.0: 0.95, 0.0050: 0.80}
    assert breakeven_cost(pf) is None


def test_breakeven_cost_takes_the_first_downward_crossing_not_a_later_rebound():
    # A noisy curve that dips below 1.0 and pops back above it must not report
    # the rebound tier - that would overstate the cost the signal survives.
    pf = {0.0: 1.30, 0.0025: 1.10, 0.0050: 0.98, 0.0060: 1.04, 0.0080: 0.70}
    assert breakeven_cost(pf) == 0.0025


def test_breakeven_cost_of_an_empty_sweep_is_none():
    assert breakeven_cost({}) is None


def test_window_result_defaults_eligible_combos_to_zero():
    # Existing constructions in this file omit the new field; they must keep working.
    wr = WindowResult(window=Window(_ts("2022-01-01"), _ts("2022-02-01"),
                                    _ts("2022-02-01"), _ts("2022-03-01")),
                      combo={}, train_pf=1.0, trades=[], net_pnl=0.0)
    assert wr.n_eligible_combos == 0


def test_median_eligible_combos_across_windows():
    result = _result([[1.0], [1.0], [1.0]])
    counted = [dataclasses.replace(w, n_eligible_combos=n)
               for w, n in zip(result.windows, [1, 5, 9])]
    result = dataclasses.replace(result, windows=counted)
    assert result.median_eligible_combos == 5.0


def test_median_eligible_combos_of_no_windows_is_zero():
    result = WalkForwardResult(label="x", symbol="BTC/USD", windows=[], oos_trades=[])
    assert result.median_eligible_combos == 0.0


class _FakeExitTrade(_FakeTrade):
    def __init__(self, entry_ts, pnl, exit_reason, entry_price=100.0, qty=1.0):
        super().__init__(entry_ts, pnl, entry_price, qty)
        self.exit_reason = exit_reason


def _exit_result(reasons, eligible=9):
    trades = [_FakeExitTrade(_ts("2022-06-01"), 1.0, r) for r in reasons]
    window = Window(_ts("2022-01-01"), _ts("2023-01-01"),
                    _ts("2023-01-01"), _ts("2023-04-01"))
    wr = WindowResult(window=window, combo={}, train_pf=1.2, trades=trades,
                      net_pnl=float(len(trades)), n_eligible_combos=eligible)
    return WalkForwardResult(label="exit-geom", symbol="BTC/USD",
                             windows=[wr], oos_trades=trades)


def test_exit_reason_counts_tallies_every_reason():
    result = _exit_result(["take_profit", "take_profit", "stop", "time_cap", "end_of_data"])
    assert result.exit_reason_counts() == {
        "take_profit": 2, "stop": 1, "time_cap": 1, "end_of_data": 1}


def test_exit_reason_counts_sum_to_the_trade_count():
    result = _exit_result(["stop"] * 7 + ["take_profit"] * 3)
    assert sum(result.exit_reason_counts().values()) == len(result.oos_trades)


def test_end_of_data_frac_measures_boundary_truncation():
    result = _exit_result(["end_of_data"] * 2 + ["take_profit"] * 8)
    assert result.end_of_data_frac == 0.2


def test_end_of_data_frac_of_no_trades_is_zero():
    result = WalkForwardResult(label="x", symbol="BTC/USD", windows=[], oos_trades=[])
    assert result.end_of_data_frac == 0.0


def test_phase_gate_promotes_when_breakeven_reaches_the_real_cost():
    result = _exit_result(["take_profit"] * 10)
    v = phase_gate_verdict(result, 0.0060)
    assert v.decision == "PROMOTE"
    assert v.breakeven_bps == 60.0


def test_phase_gate_rejects_when_breakeven_falls_short():
    result = _exit_result(["take_profit"] * 10)
    v = phase_gate_verdict(result, 0.0044)
    assert v.decision == "REJECT"
    assert "44" in v.reason


def test_phase_gate_rejects_when_there_is_no_gross_edge_at_all():
    result = _exit_result(["stop"] * 10)
    v = phase_gate_verdict(result, None)
    assert v.decision == "REJECT"
    assert v.breakeven_bps is None


def _frame(closes, start="2022-01-01"):
    ts = pd.date_range(start, periods=len(closes), freq="4h", tz="UTC")
    return pd.DataFrame({"ts": ts, "close": [float(c) for c in closes]})


def test_series_agreement_of_identical_frames_is_zero():
    frame = _frame([100.0, 101.0, 102.0])
    out = series_agreement(frame, frame)
    assert out["n_overlap"] == 3
    assert out["median_rel_diff"] == 0.0
    assert out["max_rel_diff"] == 0.0


def test_series_agreement_reports_a_relative_offset():
    out = series_agreement(_frame([101.0, 202.0]), _frame([100.0, 200.0]))
    assert out["n_overlap"] == 2
    assert out["median_rel_diff"] == pytest.approx(0.01)


def test_series_agreement_takes_the_max_not_just_the_median():
    out = series_agreement(_frame([100.0, 100.0, 110.0]), _frame([100.0, 100.0, 100.0]))
    assert out["median_rel_diff"] == 0.0
    assert out["max_rel_diff"] == pytest.approx(0.10)


def test_series_agreement_of_disjoint_frames_reports_no_overlap():
    out = series_agreement(_frame([100.0], start="2022-01-01"),
                           _frame([100.0], start="2023-01-01"))
    assert out["n_overlap"] == 0
    assert out["median_rel_diff"] != out["median_rel_diff"]   # NaN


def test_phase_gate_is_inconclusive_when_selection_was_starved():
    # Only 2 combos eligible per window: the harness had nothing to choose from,
    # so neither a pass nor a fail is meaningful.
    result = _exit_result(["take_profit"] * 10, eligible=2)
    v = phase_gate_verdict(result, 0.0080)
    assert v.decision == "INCONCLUSIVE"
    assert "eligible" in v.reason


def test_phase_gate_is_inconclusive_when_truncation_dominates():
    # 30% of trades force-closed at the window boundary: long-hold combos are
    # biased by truncation, not measured on their exits.
    result = _exit_result(["end_of_data"] * 3 + ["take_profit"] * 7)
    v = phase_gate_verdict(result, 0.0080)
    assert v.decision == "INCONCLUSIVE"
    assert "end_of_data" in v.reason


def test_phase_gate_validity_beats_a_failing_breakeven():
    # An invalid run is not gradeable in EITHER direction - it must not be
    # reported as REJECT, which would wrongly close the track.
    result = _exit_result(["end_of_data"] * 5 + ["take_profit"] * 5, eligible=1)
    v = phase_gate_verdict(result, 0.0010)
    assert v.decision == "INCONCLUSIVE"


def test_select_train_days_takes_the_smallest_candidate_that_clears_the_bar():
    probe = [(365, 0.0), (730, 1.0), (1095, 5.0), (1460, 9.0)]
    assert select_train_days(probe) == 1095


def test_select_train_days_is_none_when_no_candidate_clears_the_bar():
    # Not a negative result: the daily study is structurally untestable.
    assert select_train_days([(365, 0.0), (730, 1.0), (1095, 2.0)]) is None


def test_select_train_days_ignores_candidate_order():
    probe = [(1460, 9.0), (365, 3.0), (730, 8.0)]
    assert select_train_days(probe) == 365


def test_select_train_days_honours_a_custom_bar():
    probe = [(365, 2.0), (730, 4.0)]
    assert select_train_days(probe, min_median_eligible=5) is None
    assert select_train_days(probe, min_median_eligible=2) == 365
