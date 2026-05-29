from datetime import datetime, timedelta, timezone

from swingbot.journal import Trade
from swingbot.profile import StrategyProfile
from swingbot.risk import RiskManager, RiskState
from swingbot.types import ExitReason, Regime, Side

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _profile(**kw):
    base = {"symbol": "TRX/USD", "risk_per_trade": 0.01, "max_position_frac": 0.25,
            "daily_loss_limit_pct": 0.05, "max_consecutive_losses": 4,
            "max_concurrent": 1, "cooldown_minutes": 60}
    base.update(kw)
    return StrategyProfile.from_dict(base)


def _trade(pnl, reason, ts=T0):
    return Trade(entry_ts=ts, exit_ts=ts, side=Side.LONG, entry_price=0.10,
                 exit_price=0.10 + pnl, qty=1.0, pnl=pnl, exit_reason=reason,
                 score_at_entry=0.7, regime_at_entry=Regime.UPTREND)


def test_entry_approved_when_clean():
    rm = RiskManager(_profile(), RiskState(day_start_equity=1000.0))
    d = rm.check_can_enter("TRX/USD", now=T0, open_position_count=0)
    assert d.approved is True

def test_entry_blocked_when_killswitch_active():
    rm = RiskManager(_profile(), RiskState(kill_switch_active=True, kill_switch_reason="x"))
    d = rm.check_can_enter("TRX/USD", now=T0, open_position_count=0)
    assert d.approved is False and "kill" in d.reason.lower()

def test_entry_blocked_when_max_concurrent_reached():
    rm = RiskManager(_profile(max_concurrent=1), RiskState())
    d = rm.check_can_enter("TRX/USD", now=T0, open_position_count=1)
    assert d.approved is False and "concurrent" in d.reason.lower()

def test_entry_blocked_during_cooldown():
    rs = RiskState(cooldown_until={"TRX/USD": (T0 + timedelta(minutes=30)).isoformat()})
    rm = RiskManager(_profile(), rs)
    d = rm.check_can_enter("TRX/USD", now=T0, open_position_count=0)
    assert d.approved is False and "cooldown" in d.reason.lower()

def test_entry_allowed_after_cooldown_expires():
    rs = RiskState(cooldown_until={"TRX/USD": (T0 - timedelta(minutes=1)).isoformat()})
    rm = RiskManager(_profile(), rs)
    d = rm.check_can_enter("TRX/USD", now=T0, open_position_count=0)
    assert d.approved is True

def test_sizing_uses_fixed_fractional():
    rm = RiskManager(_profile(risk_per_trade=0.01), RiskState(day_start_equity=1000.0))
    qty = rm.size(equity=1000.0, entry_price=0.10, stop_price=0.095)
    assert abs(qty - 2000.0) < 1e-6

def test_stop_out_sets_cooldown_and_counts_loss():
    rs = RiskState(day="2026-01-01", day_start_equity=1000.0)
    rm = RiskManager(_profile(cooldown_minutes=60), rs)
    rm.on_trade_closed(_trade(-5.0, ExitReason.STOP), now=T0)
    assert rs.consecutive_losses == 1
    assert "TRX/USD" in rs.cooldown_until
    assert rs.realized_pnl_today == -5.0

def test_win_resets_consecutive_losses():
    rs = RiskState(day="2026-01-01", consecutive_losses=2, day_start_equity=1000.0)
    rm = RiskManager(_profile(), rs)
    rm.on_trade_closed(_trade(3.0, ExitReason.TAKE_PROFIT), now=T0)
    assert rs.consecutive_losses == 0

def test_killswitch_trips_on_consecutive_losses():
    rs = RiskState(day="2026-01-01", consecutive_losses=3, day_start_equity=1000.0)
    rm = RiskManager(_profile(max_consecutive_losses=4), rs)
    rm.on_trade_closed(_trade(-1.0, ExitReason.STOP), now=T0)
    assert rs.kill_switch_active is True

def test_killswitch_trips_on_daily_loss():
    rs = RiskState(day="2026-01-01", realized_pnl_today=-40.0, day_start_equity=1000.0)
    rm = RiskManager(_profile(daily_loss_limit_pct=0.05), rs)  # limit = -50
    rm.on_trade_closed(_trade(-15.0, ExitReason.STOP), now=T0)  # total -55 < -50
    assert rs.kill_switch_active is True

def test_daily_counters_reset_on_new_day():
    rs = RiskState(day="2026-01-01", realized_pnl_today=-40.0, consecutive_losses=3,
                   day_start_equity=1000.0)
    rm = RiskManager(_profile(), rs)
    next_day = T0 + timedelta(days=1)
    rm.start_day(now=next_day, equity=900.0)
    assert rs.day == "2026-01-02"
    assert rs.realized_pnl_today == 0.0
    assert rs.consecutive_losses == 0
    assert rs.day_start_equity == 900.0
