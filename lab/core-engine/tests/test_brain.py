from swingbot.types import MarketContext
from core_engine.contracts import Action
from core_engine.brain import decide
from core_engine.config import PROFILE


def test_holds_when_already_in_position(uptrend_window):
    ctx = MarketContext(candles=uptrend_window)
    d = decide(ctx, has_position=True, profile=PROFILE, kronos=None)
    assert d.action == Action.HOLD
    assert "in position" in d.reason.lower()


def test_decide_is_pure_no_side_effects(uptrend_window, monkeypatch):
    ctx = MarketContext(candles=uptrend_window)
    from tests.conftest import FakeKronos
    d1 = decide(ctx, has_position=False, profile=PROFILE, kronos=FakeKronos(0.9))
    d2 = decide(ctx, has_position=False, profile=PROFILE, kronos=FakeKronos(0.9))
    assert d1 == d2  # deterministic
    assert d1.action in (Action.ENTER_LONG, Action.HOLD)
