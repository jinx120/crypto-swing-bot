# tests/test_web_brokers.py
from fastapi.testclient import TestClient
from swingbot.web import create_app
from swingbot.credentials import CredentialStore


class FakeController:
    def __init__(self): self.reconnected = False
    def status(self): return {}
    def reconnect(self): self.reconnected = True; return (True, "reconnected")


def _client(tmp_path, token="tok"):
    creds = CredentialStore(str(tmp_path / "creds.json"))
    ctl = FakeController()
    app = create_app(controller=ctl, profiles=None, creds=creds, token=token)
    return TestClient(app), creds, ctl


def test_list_brokers(tmp_path):
    c, _, _ = _client(tmp_path)
    body = c.get("/api/brokers").json()
    assert body["active"] == "alpaca"
    assert any(b["id"] == "alpaca" for b in body["brokers"])


def test_put_broker_credentials_requires_token(tmp_path):
    c, _, _ = _client(tmp_path)
    r = c.put("/api/brokers/alpaca/credentials",
              json={"values": {"key_id": "K", "secret_key": "S"}})
    assert r.status_code == 401


def test_put_broker_credentials_saves(tmp_path):
    c, creds, _ = _client(tmp_path)
    r = c.put("/api/brokers/alpaca/credentials", headers={"X-Token": "tok"},
              json={"values": {"key_id": "K", "secret_key": "S",
                               "base_url": "https://paper-api.alpaca.markets"}})
    assert r.status_code == 200
    assert creds.broker_status("alpaca")["configured"] is True
    assert "S" not in r.text


def test_set_active_broker(tmp_path):
    c, creds, _ = _client(tmp_path)
    r = c.post("/api/brokers/active", headers={"X-Token": "tok"},
               json={"broker_id": "alpaca"})
    assert r.status_code == 200
    assert creds.active() == "alpaca"
    bad = c.post("/api/brokers/active", headers={"X-Token": "tok"},
                 json={"broker_id": "nope"})
    assert bad.status_code == 400


def test_reconnect_calls_controller(tmp_path):
    c, _, ctl = _client(tmp_path)
    r = c.post("/api/brokers/reconnect", headers={"X-Token": "tok"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert ctl.reconnected is True


def test_test_connection_endpoint(tmp_path, monkeypatch):
    c, _, _ = _client(tmp_path)

    class GoodBroker:
        def __init__(self, *a, **k): pass
        def get_account(self): return {"equity": 123.0}

    monkeypatch.setattr("swingbot.broker.adapter.AlpacaBroker", GoodBroker)
    r = c.post("/api/brokers/alpaca/test", headers={"X-Token": "tok"},
               json={"values": {"key_id": "K", "secret_key": "S"}, "mode": "paper"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_test_connection_redacts_submitted_secret_from_error(tmp_path, monkeypatch):
    c, _, _ = _client(tmp_path)
    secret = "SENSITIVE_SECRET_123"

    class LeakyBroker:
        def __init__(self, *a, **k): pass
        def get_account(self): raise RuntimeError(f"auth failed for {secret}")

    monkeypatch.setattr("swingbot.broker.adapter.AlpacaBroker", LeakyBroker)
    r = c.post("/api/brokers/alpaca/test", headers={"X-Token": "tok"},
               json={"values": {"key_id": "K", "secret_key": secret}, "mode": "paper"})
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert secret not in r.text
