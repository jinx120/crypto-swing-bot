import pandas as pd
import pytest

from lab.walkforward import Window, apply_combo, generate_windows, with_cost
from swingbot.profile import StrategyProfile
from lab.walkforward import (
    WalkForwardResult, WindowResult, profit_factor, promotion_verdict, walk_forward,
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
