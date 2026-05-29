from swingbot.graduation import can_go_live
from swingbot.metrics import Metrics


def _m(n, expectancy, max_dd=-0.02):
    return Metrics(n_trades=n, win_rate=0.5, avg_win=2, avg_loss=-1,
                   expectancy=expectancy, profit_factor=1.5, max_drawdown=max_dd)


def test_blocked_when_too_few_trades():
    ok, reason = can_go_live(_m(5, 1.0), min_trades=30, min_expectancy=0.0)
    assert ok is False and "trades" in reason.lower()


def test_blocked_when_negative_expectancy():
    ok, reason = can_go_live(_m(40, -0.5), min_trades=30, min_expectancy=0.0)
    assert ok is False and "expectancy" in reason.lower()


def test_allowed_when_criteria_met():
    ok, reason = can_go_live(_m(40, 0.8), min_trades=30, min_expectancy=0.0)
    assert ok is True
