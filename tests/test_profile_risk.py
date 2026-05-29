from datetime import datetime, timezone

from swingbot.profile import StrategyProfile
from swingbot.types import OpenPosition, Regime, Side


def test_profile_has_risk_defaults():
    p = StrategyProfile.from_dict({"symbol": "TRX/USD"})
    assert p.daily_loss_limit_pct == 0.05
    assert p.max_consecutive_losses == 4
    assert p.max_concurrent == 1
    assert p.cooldown_minutes == 60
    assert p.poll_seconds == 60

def test_profile_risk_overrides():
    p = StrategyProfile.from_dict({"symbol": "TRX/USD", "max_concurrent": 2,
                                   "cooldown_minutes": 30})
    assert p.max_concurrent == 2
    assert p.cooldown_minutes == 30

def test_open_position_roundtrips_fields():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    op = OpenPosition(symbol="TRX/USD", entry_ts=now, entry_price=0.1, qty=100.0,
                      stop=0.09, tp=0.12, max_hold_until=now,
                      score_at_entry=0.7, regime_at_entry=Regime.UPTREND, side=Side.LONG)
    assert op.symbol == "TRX/USD"
    assert op.qty == 100.0
    assert op.side == Side.LONG
