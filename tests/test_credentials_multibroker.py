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
