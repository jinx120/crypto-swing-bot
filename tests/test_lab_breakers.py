import pandas as pd

from lab.breakers import apply_breakers


class _T:
    """Minimal stand-in for swingbot.journal.Trade: the replay reads only these."""

    def __init__(self, entry, pnl, exit=None):
        self.entry_ts = pd.Timestamp(entry, tz="UTC")
        self.exit_ts = pd.Timestamp(exit or entry, tz="UTC")
        self.pnl = float(pnl)


def test_no_trades_produces_an_empty_report():
    report = apply_breakers([])
    assert report.kept == [] and report.blocked == []
    assert report.halted_at is None
    assert report.blocked_frac == 0.0


def test_a_clean_record_keeps_every_trade():
    trades = [_T(f"2022-01-{d:02d}", 5.0) for d in range(1, 6)]
    report = apply_breakers(trades)
    assert report.n_kept == 5 and report.n_blocked == 0
    assert report.halt_reason == ""


def test_three_consecutive_losses_trip_the_kill_switch():
    trades = [_T("2022-01-01", -1.0), _T("2022-01-02", -1.0), _T("2022-01-03", -1.0),
              _T("2022-01-04", 50.0)]
    report = apply_breakers(trades)
    assert report.n_kept == 3 and report.n_blocked == 1
    assert report.halted_at == pd.Timestamp("2022-01-03", tz="UTC")
    assert "consecutive losses" in report.halt_reason


def test_a_win_resets_the_consecutive_loss_counter():
    trades = [_T("2022-01-01", -1.0), _T("2022-01-02", -1.0), _T("2022-01-03", 1.0),
              _T("2022-01-04", -1.0), _T("2022-01-05", -1.0), _T("2022-01-06", 1.0)]
    report = apply_breakers(trades)
    assert report.n_blocked == 0


def test_the_kill_switch_is_terminal_and_never_auto_resets():
    # RiskManager.start_day resets the daily counters but NOT the switch, and only
    # an explicit manual resume clears it - so months of later trades stay blocked.
    trades = [_T("2022-01-01", -1.0), _T("2022-01-02", -1.0), _T("2022-01-03", -1.0)]
    trades += [_T(f"2022-06-{d:02d}", 20.0) for d in range(1, 11)]
    report = apply_breakers(trades)
    assert report.n_kept == 3 and report.n_blocked == 10
    assert report.blocked_frac == 10 / 13


def test_the_daily_loss_limit_trips_within_a_single_day():
    # Two -2% days' worth of loss inside one UTC day against a 3% limit.
    trades = [_T("2022-01-01T00:00", -20.0, exit="2022-01-01T04:00"),
              _T("2022-01-01T08:00", -20.0, exit="2022-01-01T12:00"),
              _T("2022-01-02T00:00", 50.0)]
    report = apply_breakers(trades, starting_equity=1000.0)
    assert report.n_kept == 2 and report.n_blocked == 1
    assert "daily loss" in report.halt_reason


def test_the_same_losses_spread_across_days_do_not_trip_the_daily_limit():
    trades = [_T("2022-01-01", -20.0), _T("2022-01-03", -20.0), _T("2022-01-05", 5.0)]
    report = apply_breakers(trades, starting_equity=1000.0)
    assert report.n_blocked == 0
    assert report.halted_at is None


def test_breakers_can_be_disabled_to_isolate_one_of_them():
    # Raising max_consecutive_losses out of reach isolates the daily-loss breaker.
    trades = [_T("2022-01-01", -1.0), _T("2022-01-02", -1.0), _T("2022-01-03", -1.0),
              _T("2022-01-04", 50.0)]
    report = apply_breakers(trades, max_consecutive_losses=10**9)
    assert report.n_blocked == 0


def test_a_multi_day_hold_rolls_the_day_at_its_exit():
    # A position opened before midnight and closed days later realises its loss on
    # the EXIT day, which is the day the live loop's start_day tick has moved to.
    trades = [_T("2022-01-01T00:00", -20.0, exit="2022-01-01T20:00"),
              _T("2022-01-01T22:00", -20.0, exit="2022-01-09T00:00"),
              _T("2022-01-09T04:00", 5.0)]
    report = apply_breakers(trades, starting_equity=1000.0)
    assert report.n_blocked == 0
