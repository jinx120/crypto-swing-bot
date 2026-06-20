import json
from swingbot.credentials import CredentialStore


def test_legacy_v1_file_migrates_on_load(tmp_path):
    path = tmp_path / "creds.json"
    path.write_text(json.dumps({"key_id": "OLD", "secret_key": "S",
                                "base_url": "https://api.alpaca.markets"}))
    c = CredentialStore(str(path))
    assert c.active() == "alpaca"
    st = c.status()                      # legacy shape preserved
    assert st["key_id"] == "OLD"
    assert st["has_secret"] is True
    assert st["paper"] is False
    full = c.get()
    assert full.key_id == "OLD" and full.paper is False


def test_set_writes_v2_schema_under_active_broker(tmp_path):
    path = tmp_path / "creds.json"
    c = CredentialStore(str(path))
    c.set("KID", "SECRET", "https://paper-api.alpaca.markets")
    raw = json.loads(path.read_text())
    assert raw["version"] == 2
    assert raw["active"] == "alpaca"
    assert raw["brokers"]["alpaca"]["key_id"] == "KID"


def test_active_defaults_to_alpaca_when_unset(tmp_path):
    c = CredentialStore(str(tmp_path / "creds.json"))
    assert c.active() == "alpaca"


def test_set_broker_and_status_hides_secret(tmp_path):
    c = CredentialStore(str(tmp_path / "creds.json"))
    c.set_broker("alpaca", {"key_id": "KID", "secret_key": "SECRET",
                            "base_url": "https://paper-api.alpaca.markets"})
    st = c.broker_status("alpaca")
    assert st["configured"] is True
    assert st["fields"]["key_id"]["set"] is True
    assert st["fields"]["key_id"]["value"] == "KID"      # public field shown
    assert st["fields"]["secret_key"]["set"] is True
    assert st["fields"]["secret_key"]["value"] is None   # secret never shown
    assert "SECRET" not in str(st)


def test_set_active_validates_and_persists(tmp_path):
    import pytest
    c = CredentialStore(str(tmp_path / "creds.json"))
    with pytest.raises(ValueError):
        c.set_active("nope")
    c.set_active("alpaca")
    assert c.active() == "alpaca"


def test_list_brokers_returns_registry_with_schema(tmp_path):
    c = CredentialStore(str(tmp_path / "creds.json"))
    out = c.list_brokers()
    assert out["active"] == "alpaca"
    ids = [b["id"] for b in out["brokers"]]
    assert "alpaca" in ids
    alpaca = next(b for b in out["brokers"] if b["id"] == "alpaca")
    assert alpaca["configured"] is False
    assert [f["name"] for f in alpaca["fields"]] == ["key_id", "secret_key"]
    assert {f["name"]: f["secret"] for f in alpaca["fields"]}["secret_key"] is True
