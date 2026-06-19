from datetime import datetime, timezone

from swingbot.state import StateStore
from swingbot.rebalance import RebalanceState
from swingbot.types import OpenPosition, Regime, Side
from swingbot.risk import RiskState


def _pos(now):
    return OpenPosition(symbol="TRX/USD", entry_ts=now, entry_price=0.10, qty=100.0,
                        stop=0.09, tp=0.12, max_hold_until=now,
                        score_at_entry=0.7, regime_at_entry=Regime.UPTREND, side=Side.LONG)


def test_position_save_load_clear(tmp_path):
    s = StateStore(str(tmp_path / "s.db"))
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert s.load_position() is None
    s.save_position(_pos(now))
    loaded = s.load_position()
    assert loaded.symbol == "TRX/USD"
    assert loaded.qty == 100.0
    assert loaded.regime_at_entry == Regime.UPTREND
    s.clear_position()
    assert s.load_position() is None

def test_risk_state_roundtrip(tmp_path):
    s = StateStore(str(tmp_path / "s.db"))
    rs = RiskState(kill_switch_active=True, kill_switch_reason="daily loss",
                   day="2026-01-01", realized_pnl_today=-12.5, consecutive_losses=3,
                   day_start_equity=1000.0,
                   cooldown_until={"TRX/USD": "2026-01-01T05:00:00+00:00"})
    s.save_risk_state(rs)
    out = s.load_risk_state()
    assert out.kill_switch_active is True
    assert out.consecutive_losses == 3
    assert out.realized_pnl_today == -12.5
    assert out.cooldown_until["TRX/USD"] == "2026-01-01T05:00:00+00:00"

def test_load_risk_state_default_when_empty(tmp_path):
    s = StateStore(str(tmp_path / "s.db"))
    rs = s.load_risk_state()
    assert rs.kill_switch_active is False
    assert rs.consecutive_losses == 0
    assert rs.cooldown_until == {}

def test_persistence_across_instances(tmp_path):
    path = str(tmp_path / "s.db")
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    StateStore(path).save_position(_pos(now))
    assert StateStore(path).load_position().symbol == "TRX/USD"


def test_rebalance_state_round_trip(tmp_path):
    s = StateStore(str(tmp_path / "s.db"))
    s.save_rebalance_state(
        RebalanceState(last_rebalance_at="2026-06-19T12:00:00+00:00")
    )
    got = s.load_rebalance_state()
    assert got.last_rebalance_at == "2026-06-19T12:00:00+00:00"


def test_rebalance_state_default_when_empty(tmp_path):
    s = StateStore(str(tmp_path / "s.db"))
    assert s.load_rebalance_state().last_rebalance_at == ""
