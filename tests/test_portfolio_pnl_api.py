from datetime import datetime, timezone, timedelta

from fastapi.testclient import TestClient

from swingbot.equity_store import EquitySnapshotStore
from swingbot.profiles import ProfileStore
from swingbot.web import create_app


class _Ctl:
    def status(self):
        return {}


def test_pnl_windows(tmp_path):
    es = EquitySnapshotStore(str(tmp_path / "e.db"))
    now = datetime.now(timezone.utc)
    es.record(10000.0, now - timedelta(hours=20))
    es.record(10500.0, now - timedelta(minutes=1))
    profiles = ProfileStore(str(tmp_path / "p.db"))
    app = create_app(
        controller=_Ctl(),
        profiles=profiles,
        creds=None,
        token="",
        equity_store=es,
    )
    body = TestClient(app).get("/api/portfolio/pnl").json()
    assert round(body["24h"]["abs"], 2) == 500.0
    assert round(body["24h"]["pct"], 4) == 0.05
    assert "7d" in body and "30d" in body


def test_pnl_zero_without_store(tmp_path):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    app = create_app(controller=_Ctl(), profiles=profiles, creds=None, token="")
    body = TestClient(app).get("/api/portfolio/pnl").json()
    assert body["24h"] == {"abs": 0.0, "pct": 0.0}
