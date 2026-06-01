from datetime import datetime, timedelta, timezone

from swingbot.portfolio_risk import (
    PortfolioRiskManager, PortfolioRiskState, PortfolioSettings,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _mgr(**kw):
    settings = PortfolioSettings(
        max_concurrent=kw.pop("max_concurrent", 3),
        max_total_deployed_frac=kw.pop("max_total_deployed_frac", 0.8),
        portfolio_daily_loss_limit_pct=kw.pop("portfolio_daily_loss_limit_pct", 0.08),
    )
    return PortfolioRiskManager(settings, PortfolioRiskState(**kw))


def test_approves_when_clean():
    m = _mgr(day_start_equity=1000.0)
    d = m.check_can_enter(equity=1000.0, open_position_count=0,
                          deployed_value=0.0, prospective_value=100.0)
    assert d.approved is True


def test_blocks_on_max_concurrent():
    m = _mgr(max_concurrent=2)
    d = m.check_can_enter(equity=1000.0, open_position_count=2,
                          deployed_value=0.0, prospective_value=10.0)
    assert d.approved is False and "concurrent" in d.reason.lower()


def test_blocks_when_deployed_cap_would_break():
    m = _mgr(max_total_deployed_frac=0.5)            # cap = 500
    d = m.check_can_enter(equity=1000.0, open_position_count=1,
                          deployed_value=450.0, prospective_value=100.0)  # 550 > 500
    assert d.approved is False and "deployed" in d.reason.lower()


def test_allows_up_to_deployed_cap():
    m = _mgr(max_total_deployed_frac=0.5)            # cap = 500
    d = m.check_can_enter(equity=1000.0, open_position_count=1,
                          deployed_value=400.0, prospective_value=100.0)  # 500 == cap
    assert d.approved is True


def test_blocks_when_kill_switch_active():
    m = _mgr(kill_switch_active=True, kill_switch_reason="x")
    d = m.check_can_enter(equity=1000.0, open_position_count=0,
                          deployed_value=0.0, prospective_value=10.0)
    assert d.approved is False and "kill" in d.reason.lower()


def test_daily_loss_trips_kill_switch():
    m = _mgr(day="2026-01-01", day_start_equity=1000.0,
             realized_pnl_today=-70.0, portfolio_daily_loss_limit_pct=0.08)  # limit -80
    m.on_trade_closed(-15.0, now=T0)                  # total -85 <= -80
    assert m.state.kill_switch_active is True


def test_start_day_resets_counters():
    m = _mgr(day="2026-01-01", realized_pnl_today=-50.0, day_start_equity=1000.0)
    m.start_day(now=T0 + timedelta(days=1), equity=900.0)
    assert m.state.day == "2026-01-02"
    assert m.state.realized_pnl_today == 0.0
    assert m.state.day_start_equity == 900.0
