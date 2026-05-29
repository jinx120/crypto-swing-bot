from fastapi.testclient import TestClient
from swingbot.web import create_app
from swingbot.credentials import CredentialStore


class FakeController:
    def status(self): return {}
    def journal(self): return []
    def metrics(self): return {}
    def halt(self): pass
    def reset(self): pass
    def pause(self): pass
    def resume(self): pass
    def flatten(self): pass
    def set_mode(self, m): return (True, "")
    def start(self): pass
    def stop(self): pass


def _client(tmp_path, token="tok"):
    creds = CredentialStore(str(tmp_path / "creds.json"))
    app = create_app(controller=FakeController(), profiles=None, creds=creds, token=token)
    return TestClient(app), creds


def test_credentials_status_and_set(tmp_path):
    c, _ = _client(tmp_path)
    assert c.get("/api/credentials").json()["has_secret"] is False
    r = c.put("/api/credentials", headers={"X-Token": "tok"},
              json={"key_id": "KID", "secret_key": "SEC",
                    "base_url": "https://paper-api.alpaca.markets"})
    assert r.status_code == 200
    st = c.get("/api/credentials").json()
    assert st["key_id"] == "KID" and st["has_secret"] is True
    assert "SEC" not in r.text

def test_set_credentials_requires_token(tmp_path):
    c, _ = _client(tmp_path)
    assert c.put("/api/credentials", json={"key_id": "K", "secret_key": "S",
                 "base_url": "x"}).status_code == 401
