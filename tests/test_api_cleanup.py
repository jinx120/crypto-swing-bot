from fastapi.testclient import TestClient

from swingbot.profiles import ProfileStore
from swingbot.web import create_app


class _Ctl:
    def status(self):
        return {}


def _client(tmp_path):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    return TestClient(create_app(controller=_Ctl(), profiles=profiles, creds=None, token=""))


def test_removed_routes_are_gone(tmp_path):
    c = _client(tmp_path)
    for path in [
        "/api/advisor/notes",
        "/api/advisor/journal",
        "/api/risk-dial",
        "/api/strategies/researched",
        "/api/rebalance/run",
        "/api/rebalance/targets",
        "/api/rebalance/settings",
    ]:
        assert c.get(path).status_code == 404, path


def test_thermostat_routes_still_present(tmp_path):
    c = _client(tmp_path)
    assert c.get("/api/risk-level").status_code == 200
    assert c.get("/api/coins").status_code == 200
    assert c.get("/api/portfolio/pnl").status_code == 200
