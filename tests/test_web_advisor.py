from fastapi.testclient import TestClient

from swingbot.advisor.journal import TuningJournal
from swingbot.profiles import ProfileStore
from swingbot.web import create_app


class FakeController:
    def status(self):
        return {}

    def journal(self, strategy=None):
        return []

    def metrics(self, strategy=None):
        return {}

    def reload(self):
        pass

    def stop(self):
        pass


def _profile(symbol="BTC/USD"):
    return {
        "symbol": symbol,
        "timeframe": "15m",
        "signals": {"kronos": {"weight": 1.0, "threshold_pct": 0.0075}},
        "entry_threshold": 1.0,
        "bracket_mode": "pct",
        "tp_pct": 0.02,
        "sl_pct": 0.01,
    }


def _client(tmp_path, journal=None):
    profiles = ProfileStore(str(tmp_path / "profiles.db"))
    profiles.save("btc", _profile())
    journal = journal or TuningJournal(str(tmp_path / "tuning.db"))
    app = create_app(
        controller=FakeController(),
        profiles=profiles,
        creds=None,
        token="t",
        advisor_journal=journal,
    )
    return TestClient(app, headers={"X-Token": "t"}), profiles, journal


def test_risk_dial_defaults_and_persists(tmp_path):
    client, profiles, _journal = _client(tmp_path)
    assert client.get("/api/risk-dial").json() == {"risk_dial": "balanced"}

    response = client.put("/api/risk-dial", json={"risk_dial": "aggressive"})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "risk_dial": "aggressive"}
    assert profiles.get_risk_dial() == "aggressive"


def test_risk_dial_rejects_unknown(tmp_path):
    client, _profiles, _journal = _client(tmp_path)

    response = client.put("/api/risk-dial", json={"risk_dial": "wild"})

    assert response.status_code == 400


def test_advisor_journal_and_notes_return_entries(tmp_path):
    client, _profiles, journal = _client(tmp_path)
    journal.record(
        [
            {
                "symbol": "BTC/USD",
                "param": "tp_pct",
                "before": 0.015,
                "after": 0.02,
                "rationale": "winners run",
            }
        ]
    )

    notes = client.get("/api/advisor/notes").json()
    rows = client.get("/api/advisor/journal").json()

    assert notes[0]["rationale"] == "winners run"
    assert rows[0]["param"] == "tp_pct"


def test_advisor_revert_applies_inverse_to_profile(tmp_path):
    client, profiles, journal = _client(tmp_path)
    batch_id = journal.record(
        [
            {
                "symbol": "BTC/USD",
                "param": "tp_pct",
                "before": 0.015,
                "after": 0.02,
                "rationale": "revert me",
            }
        ]
    )

    response = client.post("/api/advisor/revert", json={"batch_id": batch_id})

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert profiles.get("btc")["tp_pct"] == 0.015
    assert journal.list_entries()[0]["reverted"] is True


def test_advisor_revert_all_applies_all_inverse_changes(tmp_path):
    client, profiles, journal = _client(tmp_path)
    journal.record(
        [
            {
                "symbol": "BTC/USD",
                "param": "tp_pct",
                "before": 0.015,
                "after": 0.02,
                "rationale": "revert all",
            }
        ]
    )

    response = client.post("/api/advisor/revert-all")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert profiles.get("btc")["tp_pct"] == 0.015
