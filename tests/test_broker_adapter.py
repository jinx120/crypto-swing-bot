import pytest
from swingbot.broker.adapter import (
    CredentialField, get_adapter, BROKER_REGISTRY,
)


def test_alpaca_adapter_schema():
    a = get_adapter("alpaca")
    assert a.id == "alpaca"
    assert a.label
    assert a.modes == ["paper", "live"]
    names = [f.name for f in a.fields]
    assert names == ["key_id", "secret_key"]
    secret_flags = {f.name: f.secret for f in a.fields}
    assert secret_flags == {"key_id": False, "secret_key": True}
    assert all(isinstance(f, CredentialField) for f in a.fields)


def test_alpaca_base_url_for_mode():
    a = get_adapter("alpaca")
    assert "paper" in a.base_url_for("paper")
    assert "paper" not in a.base_url_for("live")


def test_alpaca_validate_rejects_missing_fields():
    a = get_adapter("alpaca")
    with pytest.raises(ValueError):
        a.validate({"key_id": "K"})            # secret_key missing
    a.validate({"key_id": "K", "secret_key": "S"})   # ok, no raise


def test_make_broker_and_data_use_values(monkeypatch):
    a = get_adapter("alpaca")
    captured = {}

    class FakeClient:
        def __init__(self, *args, **kw): captured["args"] = args; captured["kw"] = kw

    monkeypatch.setattr("swingbot.broker.alpaca.TradingClient", FakeClient)
    monkeypatch.setattr("swingbot.data.alpaca.CryptoHistoricalDataClient", FakeClient)
    a.make_broker({"key_id": "K", "secret_key": "S"}, "paper")
    a.make_data({"key_id": "K", "secret_key": "S"})
    assert ("K", "S") == captured["args"][:2]


def test_registry_unknown_broker_raises():
    with pytest.raises(ValueError):
        get_adapter("nope")
    assert "alpaca" in BROKER_REGISTRY


def test_test_connection_reports_ok_and_failure(monkeypatch):
    a = get_adapter("alpaca")

    class GoodBroker:
        def __init__(self, *a, **k): pass
        def get_account(self): return {"equity": 1000.0}

    monkeypatch.setattr("swingbot.broker.adapter.AlpacaBroker", GoodBroker)
    res = a.test_connection({"key_id": "K", "secret_key": "S"}, "paper")
    assert res["ok"] is True
    assert "1000" in res["detail"]

    class BadBroker:
        def __init__(self, *a, **k): pass
        def get_account(self): raise RuntimeError("401 unauthorized")

    monkeypatch.setattr("swingbot.broker.adapter.AlpacaBroker", BadBroker)
    res = a.test_connection({"key_id": "K", "secret_key": "S"}, "paper")
    assert res["ok"] is False
    assert "401" in res["detail"]
