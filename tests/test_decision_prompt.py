from swingbot.decision.prompt import PROPOSAL_SCHEMA, build_prompt, parse_proposals


def test_build_prompt_includes_context():
    rows = [{"symbol": "BTC/USD", "archetype": "balanced",
             "metrics": {"expectancy": 0.5}, "regime": "uptrend"}]
    ctx = {"equity": 1000, "open_position_count": 1, "max_concurrent": 5,
           "deployed_frac": 0.2, "armed": ["disc-ethusd-momo"]}
    p = build_prompt(rows, ctx)
    assert "BTC/USD" in p and "balanced" in p and "disc-ethusd-momo" in p
    assert "arm" in p and "disarm" in p and "tune" in p and "portfolio_settings" in p


def test_parse_proposals_keeps_valid_drops_invalid():
    data = {"proposals": [
        {"action": "arm", "target": {"symbol": "BTC/USD", "archetype": "balanced"},
         "rationale": "ok", "confidence": 0.9},
        {"action": "fly", "target": {}, "rationale": "bad action", "confidence": 0.5},
        {"action": "disarm", "rationale": "missing target", "confidence": 0.5},
    ]}
    good, dropped = parse_proposals(data, now=1)
    assert len(good) == 1 and good[0].action == "arm"
    assert len(dropped) == 2


def test_parse_proposals_handles_garbage():
    good, dropped = parse_proposals({"nope": 1}, now=1)
    assert good == [] and dropped == ["missing 'proposals' list"]


def test_schema_is_object():
    assert PROPOSAL_SCHEMA["type"] == "object"
