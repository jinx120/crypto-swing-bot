import os
import stat
from swingbot.credentials import CredentialStore


def test_set_and_status_hides_secret(tmp_path):
    c = CredentialStore(str(tmp_path / "creds.json"))
    assert c.status() == {"key_id": None, "has_secret": False, "paper": True}
    c.set("KID", "SECRET", "https://paper-api.alpaca.markets")
    st = c.status()
    assert st["key_id"] == "KID"
    assert st["has_secret"] is True
    assert st["paper"] is True
    assert "SECRET" not in str(st)


def test_file_is_chmod_600(tmp_path):
    path = tmp_path / "creds.json"
    CredentialStore(str(path)).set("KID", "SECRET", "https://paper-api.alpaca.markets")
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600


def test_get_returns_full_credentials(tmp_path):
    c = CredentialStore(str(tmp_path / "creds.json"))
    c.set("KID", "SECRET", "https://api.alpaca.markets")
    full = c.get()
    assert full.key_id == "KID" and full.secret_key == "SECRET"
    assert full.paper is False


def test_get_none_when_unset(tmp_path):
    assert CredentialStore(str(tmp_path / "creds.json")).get() is None
