from fastapi.testclient import TestClient

from swingbot.kronos_preset import kronos_bracket_profile
from swingbot.profile import StrategyProfile
from swingbot.profiles import ProfileStore
from swingbot.web import create_app


def test_preset_is_a_valid_kronos_pct_strategy():
    d = kronos_bracket_profile("ETH/USD")
    p = StrategyProfile.from_dict(d)
    assert p.symbol == "ETH/USD"
    assert p.timeframe == "15m"
    assert p.bracket_mode == "pct" and p.tp_pct == 0.006 and p.sl_pct == 0.005
    assert "kronos_forecast" in p.signals
    sig = p.signals["kronos_forecast"]
    assert sig["threshold_pct"] == 0.0075 and sig["neutral_on_error"] is False
    assert p.entry_threshold == 0.05


def test_high_frequency_preset_is_aggressive():
    d = kronos_bracket_profile("BTC/USD")
    # low threshold + single full-weight signal => fires on almost any up-forecast
    assert d["entry_threshold"] == 0.05
    assert d["signals"]["kronos_forecast"]["weight"] == 1.0
    # fast recycle + no self-halting so trades stay frequent
    assert d["max_hold_bars"] == 8
    assert d["cooldown_minutes"] == 0
    assert d["daily_loss_limit_pct"] >= 0.95
    assert d["max_consecutive_losses"] >= 100


class FakeController:
    def __init__(self):
        self.reloaded = 0

    def status(self):
        return {"portfolio": {"mode": "paper", "open_positions": 0}, "strategies": []}

    def journal(self, strategy=None):
        return []

    def metrics(self, strategy=None):
        return {}

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


def test_watchlist_add_creates_and_arms_kronos_profile(tmp_path):
    profiles = ProfileStore(str(tmp_path / "profiles.db"))
    controller = FakeController()
    app = create_app(controller=controller, profiles=profiles, creds=None, token="t")
    client = TestClient(app)

    r = client.put(
        "/api/watchlist",
        json={"symbols": ["ETH/USD"]},
        headers={"X-Token": "t"},
    )

    assert r.status_code == 200
    assert r.json()["symbols"] == ["ETH/USD"]
    assert profiles.get("kronos-eth-usd") == kronos_bracket_profile("ETH/USD")
    assert profiles.is_armed("kronos-eth-usd") is True
    assert controller.reloaded == 1
