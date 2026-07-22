from fastapi.testclient import TestClient

from swingbot.profiles import ProfileStore
from swingbot.web import create_app


class _Ctl:
    def __init__(self):
        self.flattened = []
        self.reloaded = 0

    def reload(self):
        self.reloaded += 1

    def flatten(self, name=None):
        self.flattened.append(name)

    def status(self):
        return {}


def _app(tmp_path):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    profiles.set_risk_level("Conservative")
    ctl = _Ctl()
    return (
        TestClient(create_app(controller=ctl, profiles=profiles, creds=None, token="")),
        profiles,
        ctl,
    )


def test_add_coin_creates_armed_profile_at_risk_level(tmp_path):
    client, profiles, ctl = _app(tmp_path)
    res = client.post("/api/coins", json={"symbol": "btc"})
    assert res.status_code == 200
    name = res.json()["name"]
    assert res.json()["symbol"] == "BTC/USD"
    assert name in profiles.list_armed()
    p = profiles.get(name)
    assert p["symbol"] == "BTC/USD"
    assert p["entry_threshold"] == 0.70  # Conservative applied
    assert p["max_position_frac"] == 0.05
    assert p["signals"]["kronos_forecast"]["weight"] == 1.0
    assert ctl.reloaded >= 1


def test_list_coins(tmp_path):
    client, _, _ = _app(tmp_path)
    client.post("/api/coins", json={"symbol": "ETH/USD"})
    coins = client.get("/api/coins").json()
    assert coins == [{"name": "kronos-eth-usd", "symbol": "ETH/USD"}]


def test_remove_coin_flattens_and_disarms(tmp_path):
    client, profiles, ctl = _app(tmp_path)
    client.post("/api/coins", json={"symbol": "BTC/USD"})
    res = client.delete("/api/coins/kronos-btc-usd")
    assert res.status_code == 200
    assert "kronos-btc-usd" not in profiles.list_armed()
    assert "kronos-btc-usd" in ctl.flattened


def test_remove_unknown_coin_404(tmp_path):
    client, _, _ = _app(tmp_path)
    assert client.delete("/api/coins/kronos-doge-usd").status_code == 404
