from swingbot.decision.guardrails import evaluate
from swingbot.decision.proposals import make_proposal

ELIGIBLE = [{"symbol": "BTC/USD", "archetype": "balanced"}]
CTX = {"open_position_count": 1, "max_concurrent": 5, "deployed_frac": 0.2,
       "max_total_deployed_frac": 0.80, "armed": ["disc-ethusd-momo"], "kill_switch": False}


def _ev(p, **over):
    ctx = {**CTX, **over.pop("ctx", {})}
    return evaluate(p, ctx, ELIGIBLE, backtest_ok=over.get("backtest_ok", lambda *a: True))


def test_arm_approved_for_eligible_candidate():
    p = make_proposal("arm", {"symbol": "BTC/USD", "archetype": "balanced"}, "r", 0.9, now=1)
    assert _ev(p) == ("approved", "")


def test_arm_blocked_when_not_eligible():
    p = make_proposal("arm", {"symbol": "DOGE/USD", "archetype": "balanced"}, "r", 0.9, now=1)
    assert _ev(p)[0] == "blocked"


def test_arm_blocked_at_max_concurrent():
    p = make_proposal("arm", {"symbol": "BTC/USD", "archetype": "balanced"}, "r", 0.9, now=1)
    assert _ev(p, ctx={"open_position_count": 5})[0] == "blocked"


def test_arm_blocked_when_kill_switch():
    p = make_proposal("arm", {"symbol": "BTC/USD", "archetype": "balanced"}, "r", 0.9, now=1)
    assert _ev(p, ctx={"kill_switch": True})[0] == "blocked"


def test_disarm_requires_armed():
    ok = make_proposal("disarm", {"name": "disc-ethusd-momo"}, "r", 0.5, now=1)
    bad = make_proposal("disarm", {"name": "ghost"}, "r", 0.5, now=1)
    assert _ev(ok)[0] == "approved" and _ev(bad)[0] == "blocked"


def test_tune_param_bounds_and_backtest():
    inb = make_proposal("tune", {"symbol": "BTC/USD", "archetype": "balanced",
                                  "params": {"entry_threshold": 0.7}}, "r", 0.8, now=1)
    oob = make_proposal("tune", {"symbol": "BTC/USD", "archetype": "balanced",
                                 "params": {"entry_threshold": 5.0}}, "r", 0.8, now=1)
    fails = make_proposal("tune", {"symbol": "BTC/USD", "archetype": "balanced",
                                   "params": {"entry_threshold": 0.7}}, "r", 0.8, now=1)
    assert _ev(inb)[0] == "approved"
    assert _ev(oob)[0] == "blocked"
    assert _ev(fails, backtest_ok=lambda *a: False)[0] == "blocked"


def test_portfolio_settings_clamp():
    ok = make_proposal("portfolio_settings", {"max_concurrent": 4}, "r", 0.5, now=1)
    bad = make_proposal("portfolio_settings", {"max_total_deployed_frac": 0.99}, "r", 0.5, now=1)
    assert _ev(ok)[0] == "approved" and _ev(bad)[0] == "blocked"
