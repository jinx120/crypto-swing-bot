from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass

from swingbot.decision.ollama import OllamaClient
from swingbot.decision.proposals import Proposal, ProposalStore
from swingbot.notify import DiscordNotifier
from swingbot.selftest import HealthSummary, UIFinding
from swingbot.selftest.checks import run_checks
from swingbot.selftest.llm import propose_from_health
from swingbot.selftest.report import write_report
from swingbot.selftest.uiprobe import ROUTES, UIProbe


@dataclass
class SelfTestConfig:
    project_root: str
    base_url: str
    screenshot_dir: str
    report_path: str
    devlog_path: str
    ollama_url: str
    ollama_model: str
    ollama_timeout_s: float
    proposal_store_path: str
    discord_webhook_getter: object   # callable () -> str | None
    skip_llm: bool = False


def _default_subprocess_runner(cmd: list[str], cwd: str) -> tuple[int, str]:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=300)
    return r.returncode, r.stdout + r.stderr


def _get_diffstat(project_root: str) -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", project_root, "diff", "--stat", "HEAD~1", "HEAD"],
            stderr=subprocess.DEVNULL, text=True, timeout=10,
        )
        return out[:1000].strip()
    except Exception:
        return ""


def _real_probe(base_url: str, screenshot_dir: str) -> list[UIFinding]:
    from playwright.sync_api import sync_playwright  # lazy: only when real probe runs
    os.makedirs(screenshot_dir, exist_ok=True)
    probe = UIProbe(base_url, screenshot_dir)
    findings: list[UIFinding] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        for route in ROUTES:
            findings.extend(probe.probe_route(route, ctx.new_page()))
        browser.close()
    return findings


def run(
    config: SelfTestConfig,
    *,
    runner_fn=None,
    probe_fn=None,
    llm_fn=None,
) -> int:
    """Returns 0 (green), 1 (red), 2 (runner crash)."""
    runner_fn = runner_fn or _default_subprocess_runner
    probe_fn  = probe_fn  or _real_probe
    llm_fn    = llm_fn    or propose_from_health

    started_at = time.time()
    notifier = DiscordNotifier(config.discord_webhook_getter)

    try:
        checks      = run_checks(config.project_root, runner_fn)
        ui_findings = probe_fn(config.base_url, config.screenshot_dir)

        green = (
            all(c.ok for c in checks)
            and not any(f.severity == "fatal" for f in ui_findings)
        )

        summary = HealthSummary(
            green=green,
            checks=checks,
            ui_findings=ui_findings,
            started_at=started_at,
            duration_s=round(time.time() - started_at, 2),
            diffstat=_get_diffstat(config.project_root),
        )

        proposals: list[Proposal] = []
        if green and not config.skip_llm:
            client = OllamaClient(config.ollama_url, config.ollama_model,
                                  config.ollama_timeout_s)
            store = ProposalStore(config.proposal_store_path)
            proposals = llm_fn(summary, client, store, notifier)
        elif not green:
            notifier.send("selftest_red", {
                "failed_checks": [c.name for c in checks if not c.ok],
                "fatal_ui": sum(1 for f in ui_findings if f.severity == "fatal"),
            })

        write_report(summary, proposals, config.report_path, config.devlog_path)
        return 0 if green else 1

    except Exception as e:
        notifier.send("selftest_error", {"error": str(e)[:200]})
        return 2
