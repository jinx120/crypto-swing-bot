import pytest

from swingbot.config import load_dotenv, load_alpaca_credentials, AlpacaCredentials


def test_load_dotenv_sets_missing_keys(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# comment\nFOO_KEY=abc123\nBAR='quoted val'\n\nEMPTY=\n")
    monkeypatch.delenv("FOO_KEY", raising=False)
    monkeypatch.delenv("BAR", raising=False)
    load_dotenv(str(env))
    import os
    assert os.environ["FOO_KEY"] == "abc123"
    assert os.environ["BAR"] == "quoted val"

def test_load_dotenv_does_not_override_existing(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("FOO_KEY=fromfile\n")
    monkeypatch.setenv("FOO_KEY", "fromenv")
    load_dotenv(str(env))
    import os
    assert os.environ["FOO_KEY"] == "fromenv"

def test_load_credentials_reads_env(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY_ID", "kid")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "sec")
    monkeypatch.setenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    creds = load_alpaca_credentials()
    assert isinstance(creds, AlpacaCredentials)
    assert creds.key_id == "kid"
    assert creds.secret_key == "sec"
    assert creds.paper is True

def test_load_credentials_missing_raises(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
    with pytest.raises(ValueError, match="ALPACA_API_KEY_ID"):
        load_alpaca_credentials()
