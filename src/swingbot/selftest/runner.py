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
    agent_dir: str = ""
    roadmap_path: str = ""
    run_sessions: bool = True
    ephemeral_port: int = 8001


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


def _real_sessions(config: "SelfTestConfig") -> tuple[list, bool]:
    """Returns (traces, infra_ok). Assertion failures live inside the traces;
    infra_ok=False means browser/ephemeral-app failure -> RED."""
    from playwright.sync_api import sync_playwright  # lazy
    from swingbot.selftest.agentstore import AgentRunStore
    from swingbot.selftest.ephemeral import EphemeralApp
    from swingbot.selftest.sessions import (EPHEMERAL_SESSIONS, LIVE_SESSIONS,
                                            SessionContext)
    shots = AgentRunStore(config.agent_dir).screenshot_dir if config.agent_dir else ""
    traces, infra_ok = [], True
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            bctx = browser.new_context()
            live = SessionContext(base_url=config.base_url, screenshot_dir=shots)
            for s in LIVE_SESSIONS:
                traces.append(s.run(bctx.new_page(), live))
            try:
                with EphemeralApp(port=config.ephemeral_port,
                                  agent_dir=config.agent_dir) as app:
                    ectx = SessionContext(base_url=app.base_url, token=app.token,
                                          screenshot_dir=shots,
                                          seed_proposals=app.seed_proposals)
                    for s in EPHEMERAL_SESSIONS:
                        traces.append(s.run(bctx.new_page(), ectx))
            except Exception:
                infra_ok = False
            browser.close()
    except Exception:
        infra_ok = False
    return traces, infra_ok


def run(
    config: SelfTestConfig,
    *,
    runner_fn=None,
    probe_fn=None,
    llm_fn=None,
    sessions_fn=None,
) -> int:
    """Returns 0 (green), 1 (red), 2 (runner crash)."""
    runner_fn = runner_fn or _default_subprocess_runner
    probe_fn  = probe_fn  or _real_probe
    llm_fn    = llm_fn    or propose_from_health
    sessions_fn = sessions_fn or _real_sessions

    started_at = time.time()
    notifier = DiscordNotifier(config.discord_webhook_getter)

    try:
        checks      = run_checks(config.project_root, runner_fn)
        ui_findings = probe_fn(config.base_url, config.screenshot_dir)

        traces, session_infra_ok = ([], True)
        if config.run_sessions:
            traces, session_infra_ok = sessions_fn(config)

        green = (
            all(c.ok for c in checks)
            and not any(f.severity == "fatal" for f in ui_findings)
            and session_infra_ok
        )

        summary = HealthSummary(
            green=green,
            checks=checks,
            ui_findings=ui_findings,
            started_at=started_at,
            duration_s=round(time.time() - started_at, 2),
            diffstat=_get_diffstat(config.project_root),
        )

        from dataclasses import asdict

        from swingbot.selftest.drift import findings_to_proposals, reconcile

        drift = reconcile(traces)
        drift_proposals = findings_to_proposals(drift)
        store = ProposalStore(config.proposal_store_path)
        if green and drift_proposals:
            known = {p.id for p in store.all()}
            new = [p for p in drift_proposals if p.id not in known]
            store.add_many(drift_proposals)
            if new:
                notifier.send("usage_drift", {"count": len(new),
                                              "sessions": sorted({f.session for f in drift})})

        proposals: list[Proposal] = []
        if green and not config.skip_llm:
            client = OllamaClient(config.ollama_url, config.ollama_model,
                                  config.ollama_timeout_s)
            proposals = llm_fn(summary, client, store, notifier)
        elif not green:
            notifier.send("selftest_red", {
                "failed_checks": [c.name for c in checks if not c.ok],
                "fatal_ui": sum(1 for f in ui_findings if f.severity == "fatal"),
                "session_infra_ok": session_infra_ok,
            })

        if config.agent_dir:
            from swingbot.selftest.agentstore import AgentRunStore
            AgentRunStore(config.agent_dir).add({
                "ts": started_at, "green": green,
                "duration_s": summary.duration_s,
                "checks": [asdict(c) for c in checks],
                "route_findings": [asdict(f) for f in ui_findings],
                "traces": [asdict(t) for t in traces],
                "drift": [asdict(d) for d in drift],
                "proposal_ids": [p.id for p in drift_proposals],
            })

        write_report(summary, proposals, config.report_path, config.devlog_path,
                     traces=traces, drift=drift)
        if config.roadmap_path and green and drift:
            from swingbot.selftest.report import update_roadmap_next_action
            update_roadmap_next_action(config.roadmap_path, len(drift))
        return 0 if green else 1

    except Exception as e:
        notifier.send("selftest_error", {"error": str(e)[:200]})
        return 2
