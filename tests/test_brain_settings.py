from swingbot.profiles import ProfileStore


def test_brain_defaults_present(tmp_path):
    s = ProfileStore(str(tmp_path / "db.sqlite")).get_portfolio_settings()
    assert s["brain_model"] == "qwen3.5:9b"
    assert s["brain_ollama_url"] == "http://172.17.0.1:11434"
    assert s["brain_confidence_threshold"] == 0.7
    assert s["brain_timeout_s"] == 30
    assert s["brain_autonomous_mode"] is False
    assert s["brain_auto_recommend"] is False


def test_brain_settings_are_writable(tmp_path):
    p = ProfileStore(str(tmp_path / "db.sqlite"))
    p.set_portfolio_settings({"brain_model": "llama3", "brain_autonomous_mode": True})
    s = p.get_portfolio_settings()
    assert s["brain_model"] == "llama3" and s["brain_autonomous_mode"] is True


def test_discord_webhook_roundtrip_write_only(tmp_path):
    p = ProfileStore(str(tmp_path / "db.sqlite"))
    assert p.get_discord_webhook() is None
    p.set_discord_webhook("http://hook")
    assert p.get_discord_webhook() == "http://hook"
