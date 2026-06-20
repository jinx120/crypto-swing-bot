# tests/test_auth_bootstrap.py
from fastapi.testclient import TestClient
from swingbot.web import create_app
from swingbot.webmain import _ensure_token


class FakeController:
    def status(self): return {}


def _app(tmp_path, local_trust):
    creds = None
    return create_app(controller=FakeController(), profiles=None, creds=_NullCreds(),
                      token="secret-tok", local_trust=local_trust)


class _NullCreds:
    def status(self): return {"key_id": None, "has_secret": False, "paper": True}


def test_bootstrap_returns_token_when_trusted(tmp_path):
    c = TestClient(_app(tmp_path, local_trust=True))
    r = c.get("/api/auth/bootstrap")
    assert r.status_code == 200
    assert r.json()["token"] == "secret-tok"


def test_bootstrap_forbidden_when_untrusted(tmp_path):
    c = TestClient(_app(tmp_path, local_trust=False))
    r = c.get("/api/auth/bootstrap")
    assert r.status_code == 403


def test_ensure_token_prefers_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SWINGBOT_TOKEN", "pinned-token")
    tok = _ensure_token(str(tmp_path / "token"))
    assert tok == "pinned-token"
    assert not (tmp_path / "token").exists()   # env path writes no file


def test_ensure_token_falls_back_to_file(tmp_path, monkeypatch):
    monkeypatch.delenv("SWINGBOT_TOKEN", raising=False)
    tok = _ensure_token(str(tmp_path / "token"))
    assert tok and (tmp_path / "token").exists()
