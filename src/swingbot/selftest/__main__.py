from __future__ import annotations

import argparse
import os
import sys

from swingbot.profiles import ProfileStore
from swingbot.selftest.runner import SelfTestConfig, run

DATA_DIR = os.environ.get("SWINGBOT_DATA_DIR", os.path.expanduser("~/.swingbot"))
# Walk up 3 dirs from src/swingbot/selftest/__main__.py to reach project root
_HERE = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))


def main() -> None:
    parser = argparse.ArgumentParser(description="swingbot self-test gate + LLM proposals")
    parser.add_argument("--base-url",       default="http://localhost:8000")
    parser.add_argument("--no-llm",         action="store_true")
    parser.add_argument("--ollama-url",     default="http://172.17.0.1:11434")
    parser.add_argument("--ollama-model",   default="qwen3.5:9b")
    parser.add_argument("--ollama-timeout", type=float, default=120.0)
    parser.add_argument("--no-sessions",    action="store_true")
    parser.add_argument("--ephemeral-port", type=int, default=8001)
    args = parser.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    profiles = ProfileStore(os.path.join(DATA_DIR, "swingbot.db"))

    config = SelfTestConfig(
        project_root=PROJECT_ROOT,
        base_url=args.base_url,
        screenshot_dir=os.path.join(PROJECT_ROOT, "docs", "selftest-artifacts"),
        report_path=os.path.join(PROJECT_ROOT, "docs", "SELFTEST_REPORT.md"),
        devlog_path=os.path.join(PROJECT_ROOT, "docs", "DEVLOG.md"),
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model,
        ollama_timeout_s=args.ollama_timeout,
        # The web app's brain inbox reads brain_proposals.json — writing to
        # proposals.json would hide selftest/usage-agent proposals from the UI.
        proposal_store_path=os.path.join(DATA_DIR, "brain_proposals.json"),
        discord_webhook_getter=profiles.get_discord_webhook,
        skip_llm=args.no_llm,
        agent_dir=os.path.join(DATA_DIR, "agent"),
        roadmap_path=os.path.join(PROJECT_ROOT, "docs", "ROADMAP_STATUS.md"),
        run_sessions=not args.no_sessions,
        ephemeral_port=args.ephemeral_port,
    )
    sys.exit(run(config))


if __name__ == "__main__":
    main()
