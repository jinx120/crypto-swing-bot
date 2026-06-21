from swingbot.advisor.schema import validate_proposal


def test_in_band_change_is_kept():
    raw = {"BTC/USD": {"tp_pct": 0.02, "rationale": "winners run"}}
    applied, dropped = validate_proposal(raw, dial="balanced")
    assert applied["BTC/USD"]["tp_pct"] == 0.02
    assert not dropped


def test_out_of_band_is_clamped():
    raw = {"BTC/USD": {"tp_pct": 0.99}}
    applied, dropped = validate_proposal(raw, dial="balanced")
    assert applied["BTC/USD"]["tp_pct"] <= 0.05
    assert any("clamped" in item for item in dropped)


def test_unknown_param_dropped():
    raw = {"BTC/USD": {"leverage": 10}}
    applied, dropped = validate_proposal(raw, dial="balanced")
    assert "BTC/USD" not in applied or "leverage" not in applied.get("BTC/USD", {})
    assert any("leverage" in item for item in dropped)


def test_unparseable_dropped_not_raised():
    applied, dropped = validate_proposal({"BTC/USD": "not-a-dict"}, dial="balanced")
    assert applied == {}
    assert dropped
