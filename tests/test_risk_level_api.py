from fastapi.testclient import TestClient

from swingbot.profiles import ProfileStore
from swingbot.web import create_app


class _Ctl:
    def __init__(self):
        self.reloaded = 0

    def reload(self):
        self.reloaded += 1

    def status(self):
        return {}


def _app(tmp_path):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    profiles.save(
        "kronos-btc-usd",
        {
            "symbol": "BTC/USD",
            "signals": {"kronos_forecast": {"weight": 1.0}},
            "entry_threshold": 0.05,
            "max_position_frac": 0.25,
        },
    )
    profiles.arm("kronos-btc-usd")
    ctl = _Ctl()
    app = create_app(controller=ctl, profiles=profiles, creds=None, token="")
    return TestClient(app), profiles, ctl


def test_get_risk_level_default(tmp_path):
    client, _, _ = _app(tmp_path)
    body = client.get("/api/risk-level").json()
    assert body["risk_level"] == "Moderate"
    assert body["choices"] == ["Conservative", "Moderate", "Aggressive"]


def test_put_risk_level_applies_params_to_armed(tmp_path):
    client, profiles, ctl = _app(tmp_path)
    res = client.put("/api/risk-level", json={"risk_level": "Conservative"})
    assert res.status_code == 200
    p = profiles.get("kronos-btc-usd")
    assert p["entry_threshold"] == 0.70
    assert p["max_position_frac"] == 0.05
    assert p["symbol"] == "BTC/USD"  # non-risk keys preserved
    assert profiles.get_risk_level() == "Conservative"
    assert profiles.get_meta("autotuner_tier") == "0"  # overlay reset
    assert ctl.reloaded >= 1


def test_put_risk_level_rejects_unknown(tmp_path):
    client, _, _ = _app(tmp_path)
    assert client.put("/api/risk-level", json={"risk_level": "nope"}).status_code == 400
