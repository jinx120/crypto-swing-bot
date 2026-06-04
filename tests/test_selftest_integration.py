"""Integration test — drives a real running :8000 instance + real Ollama.
Skipped unconditionally in the normal suite.

To run manually:
  docker compose up -d swingbot
  DATA_DIR=~/.swingbot .venv/bin/python -m pytest -m integration \
      tests/test_selftest_integration.py -v
"""
import os
import tempfile
import pytest
from swingbot.selftest.runner import SelfTestConfig, run

pytestmark = pytest.mark.integration


@pytest.mark.integration
def test_real_selftest_against_running_app():
    pytest.skip("opt-in only — start :8000 and pass -m integration to run")
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        cfg = SelfTestConfig(
            project_root=root,
            base_url="http://localhost:8000",
            screenshot_dir=os.path.join(tmp, "shots"),
            report_path=os.path.join(tmp, "report.md"),
            devlog_path=os.path.join(tmp, "DEVLOG.md"),
            ollama_url=os.environ.get("OLLAMA_URL", "http://172.17.0.1:11434"),
            ollama_model="qwen3.5:9b",
            ollama_timeout_s=120.0,
            proposal_store_path=os.path.join(tmp, "proposals.json"),
            discord_webhook_getter=lambda: None,
            skip_llm=False,
        )
        exit_code = run(cfg)
        assert exit_code in (0, 1)   # 2 = runner crash = bug
