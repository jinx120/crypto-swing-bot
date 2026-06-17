from datetime import datetime, timezone
from core_engine.contracts import Action, Decision
from core_engine.risk_gate import build_order_intent
from core_engine.config import PROFILE
from swingbot.risk import RiskManager, RiskState


def _risk():
    rm = RiskManager(PROFILE, RiskState())
    rm.start_day(datetime(2026, 6, 17, tzinfo=timezone.utc), equity=10_000.0)
    return rm


def test_non_entry_decision_yields_no_intent():
    d = Decision(Action.HOLD, 0.0, "hold", {})
    assert build_order_intent(d, symbol="BTC/USD",
                              now=datetime(2026, 6, 17, tzinfo=timezone.utc),
                              equity=10_000.0, entry_price=100.0, atr=2.0,
                              risk=_risk(), profile=PROFILE) is None


def test_entry_decision_sizes_and_brackets():
    d = Decision(Action.ENTER_LONG, 0.8, "confluence pass", {})
    oi = build_order_intent(d, symbol="BTC/USD",
                            now=datetime(2026, 6, 17, tzinfo=timezone.utc),
                            equity=10_000.0, entry_price=100.0, atr=2.0,
                            risk=_risk(), profile=PROFILE)
    assert oi is not None
    assert oi.qty > 0 and oi.stop < oi.entry_price < oi.tp
