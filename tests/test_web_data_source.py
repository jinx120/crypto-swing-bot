from fastapi.testclient import TestClient

from swingbot.profiles import ProfileStore
from swingbot.web import create_app


class FakeController:
    def __init__(self):
        self.reloaded = 0

    def status(self):
        return {"portfolio": {"mode": "paper", "open_positions": 0}, "strategies": []}

    def journal(self, strategy=None):
        return []

    def metrics(self, strategy=None):
        return {"n_trades": 0}

    def halt(self):
        pass

    def reset(self):
        pass

    def pause(self):
        pass

    def resume(self):
        pass

    def flatten(self, name=None):
        pass

    def set_mode(self, mode):
        return True, "ok"

    def start(self):
        pass

    def stop(self):
        pass

    def reload(self):
        self.reloaded += 1


class FakeMarket:
    def __init__(self):
        self.data_source = "coinbase"


def _client(tmp_path):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    controller = FakeController()
    market = FakeMarket()
    app = create_app(
        controller=controller,
        profiles=profiles,
        creds=None,
        token="t",
        market=market,
    )
    return TestClient(app, headers={"X-Token": "t"}), profiles, controller, market


def test_get_data_source_defaults_coinbase(tmp_path):
    client, _, _, _ = _client(tmp_path)
    r = client.get("/api/data-source")
    assert r.status_code == 200
    body = r.json()
    assert body["data_source"] == "coinbase"
    assert set(body["choices"]) == {"coinbase", "kraken", "alpaca"}


def test_put_data_source_persists_and_reloads(tmp_path):
    client, profiles, controller, market = _client(tmp_path)
    r = client.put("/api/data-source", json={"data_source": "kraken"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "data_source": "kraken"}
    assert profiles.get_data_source() == "kraken"
    assert market.data_source == "kraken"
    assert controller.reloaded == 1


def test_put_data_source_rejects_unknown(tmp_path):
    client, _, _, _ = _client(tmp_path)
    r = client.put("/api/data-source", json={"data_source": "binance"})
    assert r.status_code == 400
