from datetime import datetime, timezone
from core_engine.contracts import Action, Decision, OrderIntent, JournalEvent


def test_action_values():
    assert {a.value for a in Action} == {"enter_long", "hold", "exit"}


def test_decision_is_frozen():
    d = Decision(action=Action.HOLD, confidence=0.0, reason="flat regime", meta={})
    assert d.reason == "flat regime"
    try:
        d.confidence = 1.0
        raise AssertionError("Decision must be frozen")
    except AttributeError:
        pass


def test_order_intent_roundtrip():
    now = datetime(2026, 6, 17, tzinfo=timezone.utc)
    oi = OrderIntent(symbol="BTC/USD", qty=0.01, entry_price=100.0, stop=95.0,
                     tp=110.0, max_hold_until=now, reason="confluence pass")
    assert oi.qty == 0.01 and oi.symbol == "BTC/USD"


def test_journal_event_kinds():
    ev = JournalEvent(ts=datetime.now(timezone.utc), kind="decision",
                      symbol="BTC/USD", reason="hold", payload={"score": 0.3})
    assert ev.kind == "decision"
