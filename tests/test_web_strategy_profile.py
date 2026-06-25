from fastapi.testclient import TestClient

from swingbot.kronos_preset import kronos_bracket_profile
from swingbot.profiles import ProfileStore
from swingbot.web import create_app


class FakeController:
    def __init__(self):
        self.reloaded = 0

    def status(self):
        return {}

    def reload(self):
        self.reloaded += 1


def _client(tmp_path, token="tok"):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    profiles.save("kronos-btc-usd", kronos_bracket_profile("BTC/USD"))
    profiles.arm("kronos-btc-usd")
    ctl = FakeController()
    app = create_app(controller=ctl, profiles=profiles, creds=None, token=token)
    return TestClient(app), profiles, ctl


def test_get_strategy_profile_returns_full_profile(tmp_path):
    c, _, _ = _client(tmp_path)
    r = c.get("/api/strategies/kronos-btc-usd/profile")
    assert r.status_code == 200
    assert r.json()["profile"]["symbol"] == "BTC/USD"
    assert c.get("/api/strategies/nope/profile").status_code == 404


def test_put_profile_patch_merges_validates_and_reloads(tmp_path):
    c, profiles, ctl = _client(tmp_path)
    h = {"X-Token": "tok"}
    r = c.put(
        "/api/strategies/kronos-btc-usd/profile",
        json={"patch": {"entry_threshold": 0.2}},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["profile"]["entry_threshold"] == 0.2
    assert profiles.get("kronos-btc-usd")["entry_threshold"] == 0.2
    assert ctl.reloaded == 1


def test_put_regime_off_persists_all_three_regimes(tmp_path):
    c, profiles, _ = _client(tmp_path)
    h = {"X-Token": "tok"}
    r = c.put(
        "/api/strategies/kronos-btc-usd/profile",
        json={"patch": {"allowed_regimes": ["uptrend", "neutral", "downtrend"]}},
        headers=h,
    )
    assert r.status_code == 200
    assert profiles.get("kronos-btc-usd")["allowed_regimes"] == [
        "uptrend",
        "neutral",
        "downtrend",
    ]


def test_put_profile_rejects_unknown_key_404_and_400(tmp_path):
    c, _, _ = _client(tmp_path)
    h = {"X-Token": "tok"}
    assert (
        c.put(
            "/api/strategies/nope/profile",
            json={"patch": {"entry_threshold": 0.2}},
            headers=h,
        ).status_code
        == 404
    )
    assert (
        c.put(
            "/api/strategies/kronos-btc-usd/profile",
            json={"patch": {"poll_seconds": 5}},
            headers=h,
        ).status_code
        == 400
    )
    assert (
        c.put(
            "/api/strategies/kronos-btc-usd/profile",
            json={"patch": {"allowed_regimes": ["sideways"]}},
            headers=h,
        ).status_code
        == 400
    )


def test_put_profile_requires_token(tmp_path):
    c, _, _ = _client(tmp_path)
    assert (
        c.put(
            "/api/strategies/kronos-btc-usd/profile",
            json={"patch": {"entry_threshold": 0.2}},
        ).status_code
        == 401
    )
