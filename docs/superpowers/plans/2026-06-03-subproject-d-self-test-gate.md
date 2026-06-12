# Sub-project D — Self-test Gate + LLM Proposals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `python -m swingbot.selftest` — a scheduled CLI that runs deterministic checks + a real headless Playwright probe, then (only when fully green) asks a local LLM for improvement proposals that land in Sub-project C's existing proposal inbox.

**Architecture:** New `src/swingbot/selftest/` package with six focused modules. Gate-first pipeline: `checks.py` → `uiprobe.py` → gate decision → (green only) `llm.py` → `report.py`. All external dependencies (subprocess, Playwright page, OllamaClient) are injected so unit tests run offline with no browser or GPU. Reuses `decision/ollama.py`, `decision/proposals.py`, `decision/guardrails.py`, and `notify.py` from Sub-project C unchanged (except adding the `ui_fix` action type to guardrails).

**Tech Stack:** Python 3.11, `playwright` + `pytest-playwright` (new dev deps), existing FastAPI/SQLite app on `:8000`, Ollama `qwen3.5:9b` Q4_K_M (configurable).

---

## File Map

**Create:**
- `src/swingbot/selftest/__init__.py` — `CheckResult`, `UIFinding`, `HealthSummary` dataclasses
- `src/swingbot/selftest/checks.py` — `run_checks(project_root, runner_fn) -> list[CheckResult]`
- `src/swingbot/selftest/uiprobe.py` — `UIProbe` class, `probe_route(route, page)`, `ROUTES`
- `src/swingbot/selftest/report.py` — `write_report(summary, proposals, report_path, devlog_path)`
- `src/swingbot/selftest/llm.py` — `propose_from_health(summary, client, store, notifier) -> list[Proposal]`
- `src/swingbot/selftest/runner.py` — `SelfTestConfig`, `run(config, *, runner_fn, probe_fn, llm_fn) -> int`
- `src/swingbot/selftest/__main__.py` — CLI entry point
- `tests/test_selftest_types.py`
- `tests/test_selftest_checks.py`
- `tests/test_selftest_uiprobe.py`
- `tests/test_selftest_report.py`
- `tests/test_selftest_llm.py`
- `tests/test_selftest_runner.py`
- `tests/test_selftest_integration.py` — skipped by default

**Modify:**
- `src/swingbot/decision/guardrails.py` — add `ui_fix` action branch
- `tests/test_decision_guardrails.py` — add `ui_fix` test
- `pyproject.toml` — add `playwright` and `pytest-playwright` to dev deps

---

## Task 1: Package skeleton + shared dataclasses + ui_fix in guardrails

**Files:**
- Create: `src/swingbot/selftest/__init__.py`
- Modify: `src/swingbot/decision/guardrails.py` (add `ui_fix` branch before final `return _block`)
- Modify: `pyproject.toml` (add playwright to dev deps)
- Create: `tests/test_selftest_types.py`
- Modify: `tests/test_decision_guardrails.py` (add one test)

- [ ] **Step 1: Write failing tests for dataclasses and ui_fix guardrail**

`tests/test_selftest_types.py`:
```python
from swingbot.selftest import CheckResult, UIFinding, HealthSummary


def test_check_result_fields():
    c = CheckResult(name="pytest", ok=True, duration_s=1.5, key_output="5 passed")
    assert c.name == "pytest" and c.ok is True and c.duration_s == 1.5


def test_ui_finding_fields():
    f = UIFinding(route="/", severity="fatal", kind="exception",
                  detail="err", screenshot_path="/tmp/x.png")
    assert f.route == "/" and f.severity == "fatal"


def test_health_summary_fields():
    s = HealthSummary(green=True, checks=[], ui_findings=[],
                      started_at=1000.0, duration_s=1.5, diffstat="")
    assert s.green is True and s.checks == []
```

Add to `tests/test_decision_guardrails.py` (append after existing tests):
```python
def test_ui_fix_always_approved():
    p = make_proposal("ui_fix", {"route": "/", "issue": "console error"}, "r", 0.8, now=1)
    assert _ev(p) == ("approved", "")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/redji/crypto-swing-bot && .venv/bin/python -m pytest tests/test_selftest_types.py tests/test_decision_guardrails.py::test_ui_fix_always_approved -v
```
Expected: `ModuleNotFoundError: No module named 'swingbot.selftest'` and `FAILED test_decision_guardrails.py::test_ui_fix_always_approved`

- [ ] **Step 3: Create `src/swingbot/selftest/__init__.py`**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CheckResult:
    name: str
    ok: bool
    duration_s: float
    key_output: str


@dataclass
class UIFinding:
    route: str
    severity: str    # "fatal" | "warn" | "info"
    kind: str        # "console" | "network" | "exception"
    detail: str
    screenshot_path: str


@dataclass
class HealthSummary:
    green: bool
    checks: list[CheckResult]
    ui_findings: list[UIFinding]
    started_at: float
    duration_s: float
    diffstat: str
```

- [ ] **Step 4: Add `ui_fix` to `src/swingbot/decision/guardrails.py`**

Insert before the final `return _block(f"unknown action {p.action!r}")` line:
```python
    if p.action == "ui_fix":
        return _OPEN   # always recommend-only; selftest never auto-applies
```

- [ ] **Step 5: Add playwright to `pyproject.toml` dev deps**

Change:
```toml
dev = ["pytest>=8.0", "httpx>=0.27"]
```
To:
```toml
dev = ["pytest>=8.0", "httpx>=0.27", "playwright>=1.40", "pytest-playwright>=0.4"]
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd /home/redji/crypto-swing-bot && .venv/bin/python -m pytest tests/test_selftest_types.py tests/test_decision_guardrails.py::test_ui_fix_always_approved -v
```
Expected: `4 passed`

- [ ] **Step 7: Commit**

```bash
git add src/swingbot/selftest/__init__.py src/swingbot/decision/guardrails.py pyproject.toml tests/test_selftest_types.py tests/test_decision_guardrails.py
git commit -m "feat(selftest): package skeleton, shared dataclasses, ui_fix guardrail action"
```

---

## Task 2: checks.py — deterministic gate wrappers

**Files:**
- Create: `src/swingbot/selftest/checks.py`
- Create: `tests/test_selftest_checks.py`

- [ ] **Step 1: Write failing tests**

`tests/test_selftest_checks.py`:
```python
from swingbot.selftest.checks import run_checks


def test_all_pass_when_rc_zero():
    results = run_checks("/fake/root", lambda cmd, cwd: (0, "ok"))
    assert len(results) == 3
    assert all(r.ok for r in results)


def test_nonzero_rc_yields_not_ok():
    def fake_runner(cmd, cwd):
        return (1, "FAILED") if "ruff" in " ".join(cmd) else (0, "ok")
    results = run_checks("/fake/root", fake_runner)
    ruff = next(r for r in results if r.name == "ruff")
    assert ruff.ok is False


def test_output_truncated_to_500_chars():
    results = run_checks("/fake/root", lambda cmd, cwd: (0, "x" * 600))
    assert all(len(r.key_output) <= 500 for r in results)


def test_tail_of_output_is_kept():
    results = run_checks("/fake/root", lambda cmd, cwd: (0, "a" * 600 + "TAIL"))
    assert all(r.key_output.endswith("TAIL") for r in results)


def test_npm_build_runs_in_frontend_subdir():
    seen = []
    def fake_runner(cmd, cwd):
        seen.append((cmd, cwd))
        return 0, ""
    run_checks("/root", fake_runner)
    npm_cwd = next(cwd for cmd, cwd in seen if "npm" in " ".join(cmd))
    assert npm_cwd.endswith("frontend")


def test_result_names_are_pytest_ruff_npm():
    results = run_checks("/fake/root", lambda cmd, cwd: (0, ""))
    assert [r.name for r in results] == ["pytest", "ruff", "npm-build"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/redji/crypto-swing-bot && .venv/bin/python -m pytest tests/test_selftest_checks.py -v
```
Expected: `ModuleNotFoundError: No module named 'swingbot.selftest.checks'`

- [ ] **Step 3: Create `src/swingbot/selftest/checks.py`**

```python
from __future__ import annotations

import os
import time

from swingbot.selftest import CheckResult

_OUTPUT_LIMIT = 500

_CHECKS = [
    ("pytest",    [".venv/bin/python", "-m", "pytest", "-q"],       None),
    ("ruff",      [".venv/bin/python", "-m", "ruff", "check", "."], None),
    ("npm-build", ["npm", "run", "build"],                          "frontend"),
]


def run_checks(project_root: str, runner_fn) -> list[CheckResult]:
    results = []
    for name, cmd, subdir in _CHECKS:
        cwd = os.path.join(project_root, subdir) if subdir else project_root
        t0 = time.monotonic()
        rc, out = runner_fn(cmd, cwd)
        results.append(CheckResult(
            name=name,
            ok=(rc == 0),
            duration_s=round(time.monotonic() - t0, 2),
            key_output=(out or "")[-_OUTPUT_LIMIT:].strip(),
        ))
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/redji/crypto-swing-bot && .venv/bin/python -m pytest tests/test_selftest_checks.py -v
```
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/selftest/checks.py tests/test_selftest_checks.py
git commit -m "feat(selftest): checks.py — pytest/ruff/npm-build gate with injected subprocess runner"
```

---

## Task 3: uiprobe.py — headless Playwright route probe

**Files:**
- Create: `src/swingbot/selftest/uiprobe.py`
- Create: `tests/test_selftest_uiprobe.py`

- [ ] **Step 1: Write failing tests**

`tests/test_selftest_uiprobe.py`:
```python
from swingbot.selftest.uiprobe import UIProbe, ROUTES


class FakePage:
    def __init__(self):
        self._handlers = {}

    def on(self, event, handler):
        self._handlers.setdefault(event, []).append(handler)

    def emit(self, event, *args):
        for h in self._handlers.get(event, []):
            h(*args)

    def goto(self, url, **kwargs):
        pass

    def screenshot(self, **kwargs):
        pass


class _ConsoleMsgError:
    type = "error"
    text = "Uncaught TypeError"


class _ConsoleMsgWarning:
    type = "warning"
    text = "Deprecated API"


class _Resp500:
    status = 500
    url = "http://localhost:8000/api/brain"


class _Resp404:
    status = 404
    url = "http://localhost:8000/api/missing"


def _make_probe():
    return UIProbe("http://localhost:8000", "/tmp/shots")


def _fire_during_goto(page, event, obj):
    """Patch page.goto to emit an event before returning."""
    def patched_goto(url, **kw):
        page.emit(event, obj)
    page.goto = patched_goto


def test_console_error_becomes_warn_finding():
    probe = _make_probe()
    page = FakePage()
    _fire_during_goto(page, "console", _ConsoleMsgError())
    result = probe.probe_route("/", page)
    assert any(f.severity == "warn" and f.kind == "console" for f in result)


def test_console_warning_becomes_info_finding():
    probe = _make_probe()
    page = FakePage()
    _fire_during_goto(page, "console", _ConsoleMsgWarning())
    result = probe.probe_route("/", page)
    assert any(f.severity == "info" and f.kind == "console" for f in result)


def test_pageerror_becomes_fatal_finding():
    probe = _make_probe()
    page = FakePage()
    _fire_during_goto(page, "pageerror", Exception("uncaught!"))
    result = probe.probe_route("/brain", page)
    assert any(f.severity == "fatal" and f.kind == "exception" for f in result)


def test_5xx_response_becomes_fatal_network_finding():
    probe = _make_probe()
    page = FakePage()
    _fire_during_goto(page, "response", _Resp500())
    result = probe.probe_route("/", page)
    assert any(f.severity == "fatal" and f.kind == "network" for f in result)


def test_4xx_response_becomes_warn_network_finding():
    probe = _make_probe()
    page = FakePage()
    _fire_during_goto(page, "response", _Resp404())
    result = probe.probe_route("/", page)
    assert any(f.severity == "warn" and f.kind == "network" for f in result)


def test_navigation_exception_becomes_fatal_finding():
    probe = _make_probe()
    page = FakePage()
    page.goto = lambda url, **kw: (_ for _ in ()).throw(ConnectionRefusedError("refused"))
    result = probe.probe_route("/", page)
    assert any(f.severity == "fatal" and f.kind == "exception" for f in result)


def test_screenshot_path_set_on_finding():
    probe = _make_probe()
    page = FakePage()
    _fire_during_goto(page, "pageerror", Exception("oops"))
    result = probe.probe_route("/discover", page)
    assert all(f.screenshot_path != "" for f in result)
    assert all("discover" in f.screenshot_path for f in result)


def test_run_visits_all_routes():
    probe = _make_probe()
    visited = []
    original = probe.probe_route
    probe.probe_route = lambda route, page: visited.append(route) or []
    probe.run(FakePage)
    assert set(visited) == set(ROUTES)


def test_routes_are_dashboard_discover_brain():
    assert ROUTES == ["/", "/discover", "/brain"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/redji/crypto-swing-bot && .venv/bin/python -m pytest tests/test_selftest_uiprobe.py -v
```
Expected: `ModuleNotFoundError: No module named 'swingbot.selftest.uiprobe'`

- [ ] **Step 3: Create `src/swingbot/selftest/uiprobe.py`**

```python
from __future__ import annotations

import os

from swingbot.selftest import UIFinding

ROUTES = ["/", "/discover", "/brain"]


class UIProbe:
    def __init__(self, base_url: str, screenshot_dir: str):
        self.base_url = base_url.rstrip("/")
        self.screenshot_dir = screenshot_dir

    def probe_route(self, route: str, page) -> list[UIFinding]:
        findings: list[UIFinding] = []
        shot_name = route.strip("/") or "index"
        shot_path = os.path.join(self.screenshot_dir, f"{shot_name}.png")

        def on_console(msg):
            if msg.type == "error":
                findings.append(UIFinding(route=route, severity="warn", kind="console",
                                          detail=msg.text, screenshot_path=""))
            elif msg.type == "warning":
                findings.append(UIFinding(route=route, severity="info", kind="console",
                                          detail=msg.text, screenshot_path=""))

        def on_pageerror(exc):
            findings.append(UIFinding(route=route, severity="fatal", kind="exception",
                                      detail=str(exc), screenshot_path=""))

        def on_response(resp):
            if resp.status >= 500:
                findings.append(UIFinding(route=route, severity="fatal", kind="network",
                                          detail=f"HTTP {resp.status} {resp.url}", screenshot_path=""))
            elif resp.status >= 400:
                findings.append(UIFinding(route=route, severity="warn", kind="network",
                                          detail=f"HTTP {resp.status} {resp.url}", screenshot_path=""))

        page.on("console", on_console)
        page.on("pageerror", on_pageerror)
        page.on("response", on_response)

        try:
            page.goto(f"{self.base_url}{route}", wait_until="networkidle")
        except Exception as e:
            findings.append(UIFinding(route=route, severity="fatal", kind="exception",
                                      detail=f"navigation failed: {e}", screenshot_path=""))

        try:
            page.screenshot(path=shot_path, full_page=True)
        except Exception:
            pass

        for f in findings:
            if not f.screenshot_path:
                f.screenshot_path = shot_path

        return findings

    def run(self, page_factory) -> list[UIFinding]:
        all_findings: list[UIFinding] = []
        for route in ROUTES:
            page = page_factory()
            all_findings.extend(self.probe_route(route, page))
        return all_findings
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/redji/crypto-swing-bot && .venv/bin/python -m pytest tests/test_selftest_uiprobe.py -v
```
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/selftest/uiprobe.py tests/test_selftest_uiprobe.py
git commit -m "feat(selftest): uiprobe.py — headless Playwright route probe with injectable page"
```

---

## Task 4: report.py — SELFTEST_REPORT.md + DEVLOG one-liner

**Files:**
- Create: `src/swingbot/selftest/report.py`
- Create: `tests/test_selftest_report.py`

- [ ] **Step 1: Write failing tests**

`tests/test_selftest_report.py`:
```python
import tempfile
from swingbot.selftest import CheckResult, UIFinding, HealthSummary
from swingbot.selftest.report import write_report
from swingbot.decision.proposals import make_proposal


def _summary(green=True):
    return HealthSummary(
        green=green,
        checks=[
            CheckResult("pytest",    green, 1.5, "288 passed" if green else "1 failed"),
            CheckResult("ruff",      True,  0.1, "All checks passed."),
            CheckResult("npm-build", True,  0.2, "built"),
        ],
        ui_findings=[] if green else [
            UIFinding("/", "fatal", "exception", "page crashed", "/tmp/index.png")
        ],
        started_at=1717497131.0,
        duration_s=2.1,
        diffstat=" src/swingbot/selftest/__init__.py | 15 +++",
    )


def test_green_report_contains_status_and_check_names():
    s = _summary(green=True)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as rf, \
         tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as df:
        rp, dp = rf.name, df.name
    write_report(s, [], rp, dp)
    content = open(rp).read()
    assert "GREEN" in content
    assert "pytest" in content and "ruff" in content and "npm-build" in content
    assert "288 passed" in content


def test_red_report_shows_red_in_report_and_devlog():
    s = _summary(green=False)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as rf, \
         tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as df:
        rp, dp = rf.name, df.name
    write_report(s, [], rp, dp)
    assert "RED" in open(rp).read()
    assert "RED" in open(dp).read()


def test_devlog_line_appended_not_overwritten():
    s = _summary(green=True)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as rf, \
         tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as df:
        rp, dp = rf.name, df.name
    open(dp, "w").write("EXISTING LINE\n")
    write_report(s, [], rp, dp)
    devlog = open(dp).read()
    assert "EXISTING LINE" in devlog
    assert "GREEN" in devlog


def test_devlog_contains_check_status_icons():
    s = _summary(green=True)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as rf, \
         tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as df:
        rp, dp = rf.name, df.name
    write_report(s, [], rp, dp)
    devlog = open(dp).read()
    assert "pytest✓" in devlog


def test_proposals_shown_in_report():
    s = _summary(green=True)
    p = make_proposal("ui_fix", {"route": "/", "issue": "console error"}, "Fix it", 0.8, now=1)
    p.guardrail_status = "approved"
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as rf, \
         tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as df:
        rp, dp = rf.name, df.name
    write_report(s, [p], rp, dp)
    content = open(rp).read()
    assert "ui_fix" in content
    assert "Proposals" in content


def test_diffstat_included_in_report():
    s = _summary(green=True)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as rf, \
         tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as df:
        rp, dp = rf.name, df.name
    write_report(s, [], rp, dp)
    assert "selftest/__init__.py" in open(rp).read()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/redji/crypto-swing-bot && .venv/bin/python -m pytest tests/test_selftest_report.py -v
```
Expected: `ModuleNotFoundError: No module named 'swingbot.selftest.report'`

- [ ] **Step 3: Create `src/swingbot/selftest/report.py`**

```python
from __future__ import annotations

import datetime

from swingbot.decision.proposals import Proposal
from swingbot.selftest import HealthSummary

_CHECK_ICON = {True: "✅", False: "❌"}
_SEV_ICON = {"fatal": "🔴", "warn": "⚠️", "info": "ℹ️"}


def write_report(summary: HealthSummary, proposals: list[Proposal],
                 report_path: str, devlog_path: str) -> None:
    status = "GREEN" if summary.green else "RED"
    status_emoji = "🟢" if summary.green else "🔴"
    dt_str = datetime.datetime.utcfromtimestamp(summary.started_at).strftime(
        "%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# Self-test Report",
        "",
        f"**Run:** {dt_str}  |  **Status:** {status_emoji} {status}"
        f"  |  **Duration:** {summary.duration_s}s",
        "",
        "## Deterministic Checks",
        "",
        "| Check | Status | Duration | Output |",
        "|-------|--------|----------|--------|",
    ]
    for c in summary.checks:
        out = c.key_output.replace("\n", " ")[:120]
        lines.append(f"| {c.name} | {_CHECK_ICON[c.ok]} | {c.duration_s}s | {out} |")

    lines += ["", "## UI Probe Findings", ""]
    if summary.ui_findings:
        lines += [
            "| Route | Severity | Kind | Detail | Screenshot |",
            "|-------|----------|------|--------|------------|",
        ]
        for f in summary.ui_findings:
            icon = _SEV_ICON.get(f.severity, "")
            shot = f"[screenshot]({f.screenshot_path})" if f.screenshot_path else ""
            lines.append(
                f"| {f.route} | {icon} {f.severity} | {f.kind}"
                f" | {f.detail[:80]} | {shot} |"
            )
    else:
        lines.append("_No UI findings._")

    if proposals:
        lines += [
            "", f"## Proposals ({len(proposals)})", "",
            "| Action | Target | Rationale | Confidence | Guardrail |",
            "|--------|--------|-----------|------------|-----------|",
        ]
        for p in proposals:
            lines.append(
                f"| {p.action} | {str(p.target)[:40]} | {p.rationale[:60]}"
                f" | {p.confidence:.2f} | {p.guardrail_status} |"
            )

    if summary.diffstat:
        lines += ["", "## Git Diff Stat", "", "```", summary.diffstat, "```"]

    with open(report_path, "w") as fh:
        fh.write("\n".join(lines) + "\n")

    fatal_count = sum(1 for f in summary.ui_findings if f.severity == "fatal")
    check_icons = " ".join(
        f"{c.name}{'✓' if c.ok else '✗'}" for c in summary.checks
    )
    devlog_line = (
        f"\n{dt_str}  {status}  {summary.duration_s}s  "
        f"{check_icons}  ui:{fatal_count}fatal  proposals:{len(proposals)}"
    )
    with open(devlog_path, "a") as fh:
        fh.write(devlog_line)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/redji/crypto-swing-bot && .venv/bin/python -m pytest tests/test_selftest_report.py -v
```
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/selftest/report.py tests/test_selftest_report.py
git commit -m "feat(selftest): report.py — SELFTEST_REPORT.md writer + DEVLOG one-liner"
```

---

## Task 5: llm.py — LLM proposal pass (green-only)

**Files:**
- Create: `src/swingbot/selftest/llm.py`
- Create: `tests/test_selftest_llm.py`

- [ ] **Step 1: Write failing tests**

`tests/test_selftest_llm.py`:
```python
import json
import tempfile
from swingbot.selftest import CheckResult, HealthSummary
from swingbot.selftest.llm import propose_from_health
from swingbot.decision.ollama import OllamaClient
from swingbot.decision.proposals import ProposalStore
from swingbot.notify import DiscordNotifier


def _summary():
    return HealthSummary(
        green=True, checks=[CheckResult("pytest", True, 1.5, "288 passed")],
        ui_findings=[], started_at=1000.0, duration_s=2.0, diffstat="",
    )


def _client(data):
    def fake_transport(url, payload, timeout):
        return {"response": json.dumps(data)}
    return OllamaClient("http://x:11434", "qwen3.5:9b", 10.0, transport=fake_transport)


def _store():
    f = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    return ProposalStore(f.name)


def _notifier():
    return DiscordNotifier(lambda: None)


def test_ui_fix_proposal_stored_and_approved():
    data = {"proposals": [{"action": "ui_fix",
                           "target": {"route": "/", "issue": "console error"},
                           "rationale": "Fix it", "confidence": 0.8}]}
    store = _store()
    proposals = propose_from_health(_summary(), _client(data), store, _notifier())
    assert len(proposals) == 1
    assert proposals[0].action == "ui_fix"
    assert proposals[0].source == "selftest"
    assert proposals[0].guardrail_status == "approved"
    assert len(store.all()) == 1


def test_ollama_failure_returns_empty_list_no_crash():
    def boom(url, payload, timeout):
        raise OSError("connection refused")
    client = OllamaClient("http://x", "qwen3.5:9b", 1.0, transport=boom)
    proposals = propose_from_health(_summary(), client, _store(), _notifier())
    assert proposals == []


def test_arm_action_filtered_out():
    data = {"proposals": [{"action": "arm",
                           "target": {"symbol": "BTC/USD", "archetype": "balanced"},
                           "rationale": "buy", "confidence": 0.9}]}
    proposals = propose_from_health(_summary(), _client(data), _store(), _notifier())
    assert proposals == []


def test_tune_proposal_runs_through_guardrails():
    data = {"proposals": [{"action": "tune",
                           "target": {"symbol": "BTC/USD", "archetype": "balanced",
                                      "params": {"entry_threshold": 0.6}},
                           "rationale": "tighten entry", "confidence": 0.7}]}
    proposals = propose_from_health(_summary(), _client(data), _store(), _notifier())
    assert len(proposals) == 1
    assert proposals[0].guardrail_status in ("approved", "blocked")


def test_empty_proposals_list_from_llm_returns_empty():
    data = {"proposals": []}
    proposals = propose_from_health(_summary(), _client(data), _store(), _notifier())
    assert proposals == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/redji/crypto-swing-bot && .venv/bin/python -m pytest tests/test_selftest_llm.py -v
```
Expected: `ModuleNotFoundError: No module named 'swingbot.selftest.llm'`

- [ ] **Step 3: Create `src/swingbot/selftest/llm.py`**

```python
from __future__ import annotations

import datetime

from swingbot.decision.guardrails import evaluate
from swingbot.decision.ollama import OllamaClient
from swingbot.decision.proposals import Proposal, ProposalStore, make_proposal
from swingbot.notify import DiscordNotifier
from swingbot.selftest import HealthSummary

_ALLOWED_ACTIONS = {"tune", "ui_fix", "portfolio_settings"}

_SCHEMA = {
    "type": "object",
    "properties": {
        "proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action":     {"type": "string"},
                    "target":     {"type": "object"},
                    "rationale":  {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["action", "target", "rationale", "confidence"],
            },
        }
    },
    "required": ["proposals"],
}


def _build_prompt(summary: HealthSummary) -> str:
    dt = datetime.datetime.utcfromtimestamp(summary.started_at).strftime("%Y-%m-%d %H:%M UTC")
    check_lines = "\n".join(
        f"  {c.name}: {'PASS' if c.ok else 'FAIL'} ({c.duration_s}s)"
        + (f" — {c.key_output[:200]}" if c.key_output else "")
        for c in summary.checks
    )
    finding_lines = "\n".join(
        f"  [{f.severity}] {f.kind} on {f.route}: {f.detail[:200]}"
        for f in summary.ui_findings
    ) or "  None"
    return (
        f"You are reviewing a green self-test run of a crypto swing trading bot web app.\n"
        f"Run time: {dt}\n\n"
        f"Deterministic checks (all passed):\n{check_lines}\n\n"
        f"UI probe findings:\n{finding_lines}\n\n"
        f"Recent code changes:\n{summary.diffstat or '(none)'}\n\n"
        f"Propose targeted improvements. Allowed actions: tune (strategy params), "
        f"ui_fix (UI route + issue), portfolio_settings (risk settings). "
        f"Be conservative — only propose changes with clear evidence. "
        f"Return JSON with a 'proposals' array (max 5 items). "
        f"Each item: action, target (object), rationale, confidence (0-1). "
        f"If nothing needs changing, return {{\"proposals\": []}}."
    )


def propose_from_health(
    summary: HealthSummary,
    client: OllamaClient,
    store: ProposalStore,
    notifier: DiscordNotifier,
) -> list[Proposal]:
    result = client.generate_json(_build_prompt(summary), _SCHEMA)
    if not result.ok:
        return []

    raw_items = result.data.get("proposals") or []
    proposals: list[Proposal] = []
    for item in raw_items:
        action = str(item.get("action", ""))
        if action not in _ALLOWED_ACTIONS:
            continue
        p = make_proposal(
            action=action,
            target=item.get("target") or {},
            rationale=str(item.get("rationale", ""))[:500],
            confidence=float(item.get("confidence", 0.5)),
        )
        p.source = "selftest"
        if action == "ui_fix":
            p.guardrail_status, p.guardrail_reason = "approved", ""
        else:
            p.guardrail_status, p.guardrail_reason = evaluate(
                p, {}, [], backtest_ok=lambda *_: True
            )
        proposals.append(p)

    if proposals:
        store.add_many(proposals)
        notifier.send("selftest_proposals", {"count": len(proposals)})

    return proposals
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/redji/crypto-swing-bot && .venv/bin/python -m pytest tests/test_selftest_llm.py -v
```
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/selftest/llm.py tests/test_selftest_llm.py
git commit -m "feat(selftest): llm.py — green-only LLM proposal pass via OllamaClient"
```

---

## Task 6: runner.py — gate orchestrator

**Files:**
- Create: `src/swingbot/selftest/runner.py`
- Create: `tests/test_selftest_runner.py`

- [ ] **Step 1: Write failing tests**

`tests/test_selftest_runner.py`:
```python
import os
import tempfile
from swingbot.selftest import UIFinding
from swingbot.selftest.runner import SelfTestConfig, run


def _cfg(tmp: str, skip_llm: bool = True) -> SelfTestConfig:
    return SelfTestConfig(
        project_root="/fake/root",
        base_url="http://localhost:8000",
        screenshot_dir=os.path.join(tmp, "shots"),
        report_path=os.path.join(tmp, "report.md"),
        devlog_path=os.path.join(tmp, "DEVLOG.md"),
        ollama_url="http://localhost:11434",
        ollama_model="qwen3.5:9b",
        ollama_timeout_s=5.0,
        proposal_store_path=os.path.join(tmp, "proposals.json"),
        discord_webhook_getter=lambda: None,
        skip_llm=skip_llm,
    )


_OK_RUNNER = lambda cmd, cwd: (0, "ok")
_FAIL_PYTEST = lambda cmd, cwd: (1, "1 failed") if "pytest" in " ".join(cmd) else (0, "ok")
_NO_FINDINGS = lambda url, d: []
_FATAL_FINDING = lambda url, d: [UIFinding("/", "fatal", "exception", "crash", "/tmp/x.png")]
_WARN_FINDING  = lambda url, d: [UIFinding("/", "warn",  "console",   "warn",  "/tmp/x.png")]
_NO_LLM = lambda s, c, st, n: []


def test_all_pass_returns_0():
    with tempfile.TemporaryDirectory() as tmp:
        assert run(_cfg(tmp), runner_fn=_OK_RUNNER, probe_fn=_NO_FINDINGS, llm_fn=_NO_LLM) == 0


def test_failing_check_returns_1():
    with tempfile.TemporaryDirectory() as tmp:
        assert run(_cfg(tmp), runner_fn=_FAIL_PYTEST, probe_fn=_NO_FINDINGS, llm_fn=_NO_LLM) == 1


def test_fatal_ui_finding_returns_1():
    with tempfile.TemporaryDirectory() as tmp:
        assert run(_cfg(tmp), runner_fn=_OK_RUNNER, probe_fn=_FATAL_FINDING, llm_fn=_NO_LLM) == 1


def test_warn_ui_finding_does_not_block_green():
    with tempfile.TemporaryDirectory() as tmp:
        assert run(_cfg(tmp), runner_fn=_OK_RUNNER, probe_fn=_WARN_FINDING, llm_fn=_NO_LLM) == 0


def test_llm_not_called_on_red():
    with tempfile.TemporaryDirectory() as tmp:
        llm_called = [False]
        def fake_llm(s, c, st, n):
            llm_called[0] = True
            return []
        run(_cfg(tmp, skip_llm=False), runner_fn=_FAIL_PYTEST,
            probe_fn=_NO_FINDINGS, llm_fn=fake_llm)
        assert llm_called[0] is False


def test_llm_called_on_green_when_not_skipped():
    with tempfile.TemporaryDirectory() as tmp:
        llm_called = [False]
        def fake_llm(s, c, st, n):
            llm_called[0] = True
            return []
        run(_cfg(tmp, skip_llm=False), runner_fn=_OK_RUNNER,
            probe_fn=_NO_FINDINGS, llm_fn=fake_llm)
        assert llm_called[0] is True


def test_llm_not_called_when_skip_llm_true():
    with tempfile.TemporaryDirectory() as tmp:
        llm_called = [False]
        def fake_llm(s, c, st, n):
            llm_called[0] = True
            return []
        run(_cfg(tmp, skip_llm=True), runner_fn=_OK_RUNNER,
            probe_fn=_NO_FINDINGS, llm_fn=fake_llm)
        assert llm_called[0] is False


def test_report_written_on_green():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        run(cfg, runner_fn=_OK_RUNNER, probe_fn=_NO_FINDINGS, llm_fn=_NO_LLM)
        assert os.path.exists(cfg.report_path)
        assert "GREEN" in open(cfg.report_path).read()


def test_report_written_on_red():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        run(cfg, runner_fn=_FAIL_PYTEST, probe_fn=_NO_FINDINGS, llm_fn=_NO_LLM)
        assert os.path.exists(cfg.report_path)
        assert "RED" in open(cfg.report_path).read()


def test_crash_in_probe_returns_2():
    with tempfile.TemporaryDirectory() as tmp:
        def boom(url, d):
            raise RuntimeError("playwright exploded")
        exit_code = run(_cfg(tmp), runner_fn=_OK_RUNNER, probe_fn=boom, llm_fn=_NO_LLM)
        assert exit_code == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/redji/crypto-swing-bot && .venv/bin/python -m pytest tests/test_selftest_runner.py -v
```
Expected: `ModuleNotFoundError: No module named 'swingbot.selftest.runner'`

- [ ] **Step 3: Create `src/swingbot/selftest/runner.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/redji/crypto-swing-bot && .venv/bin/python -m pytest tests/test_selftest_runner.py -v
```
Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/selftest/runner.py tests/test_selftest_runner.py
git commit -m "feat(selftest): runner.py — gate orchestrator with injectable check/probe/llm fns"
```

---

## Task 7: __main__.py + playwright install + integration test stub

**Files:**
- Create: `src/swingbot/selftest/__main__.py`
- Create: `tests/test_selftest_integration.py`
- Install: `playwright` package + Chromium browser binary

- [ ] **Step 1: Install playwright dev deps**

```bash
cd /home/redji/crypto-swing-bot && .venv/bin/pip install playwright pytest-playwright
.venv/bin/playwright install chromium
```
Expected: `Chromium ... downloaded` (may take a minute)

- [ ] **Step 2: Create `src/swingbot/selftest/__main__.py`**

```python
from __future__ import annotations

import argparse
import os
import sys

from swingbot.profiles import ProfileStore
from swingbot.selftest.runner import SelfTestConfig, run

DATA_DIR = os.environ.get("SWINGBOT_DATA_DIR", os.path.expanduser("~/.swingbot"))
# Walk up 4 dirs from src/swingbot/selftest/__main__.py to reach project root
_HERE = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))


def main() -> None:
    parser = argparse.ArgumentParser(description="swingbot self-test gate + LLM proposals")
    parser.add_argument("--base-url",       default="http://localhost:8000")
    parser.add_argument("--no-llm",         action="store_true")
    parser.add_argument("--ollama-url",     default="http://172.17.0.1:11434")
    parser.add_argument("--ollama-model",   default="qwen3.5:9b")
    parser.add_argument("--ollama-timeout", type=float, default=120.0)
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
        proposal_store_path=os.path.join(DATA_DIR, "proposals.json"),
        discord_webhook_getter=profiles.get_discord_webhook,
        skip_llm=args.no_llm,
    )
    sys.exit(run(config))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify the CLI entry point is importable**

```bash
cd /home/redji/crypto-swing-bot && .venv/bin/python -c "import swingbot.selftest.__main__; print('ok')"
```
Expected: `ok`

- [ ] **Step 4: Create opt-in integration test stub**

`tests/test_selftest_integration.py`:
```python
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
```

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/selftest/__main__.py tests/test_selftest_integration.py
git commit -m "feat(selftest): __main__.py CLI entry + playwright install + integration test stub"
```

---

## Task 8: Final validation

**Files:** none — validation only

- [ ] **Step 1: Run full test suite**

```bash
cd /home/redji/crypto-swing-bot && .venv/bin/python -m pytest -q
```
Expected: at least `288 passed, 5 skipped` (original baseline) plus the ~35 new selftest tests. All must pass; no regressions.

- [ ] **Step 2: Verify selftest package is fully importable**

```bash
.venv/bin/python -c "
from swingbot.selftest import CheckResult, UIFinding, HealthSummary
from swingbot.selftest.checks import run_checks
from swingbot.selftest.uiprobe import UIProbe, ROUTES
from swingbot.selftest.report import write_report
from swingbot.selftest.llm import propose_from_health
from swingbot.selftest.runner import SelfTestConfig, run
print('all imports ok')
"
```
Expected: `all imports ok`

- [ ] **Step 3: Verify CLI help works**

```bash
.venv/bin/python -m swingbot.selftest --help
```
Expected: usage line showing `--base-url`, `--no-llm`, `--ollama-url`, `--ollama-model`, `--ollama-timeout`

- [ ] **Step 4: Update ROADMAP_STATUS.md**

Set Sub-project D status to `✅ DONE` in the status board. Update NEXT ACTION to reflect D is complete. Update "Last updated" date to today (2026-06-04).

- [ ] **Step 5: Final commit**

```bash
git add docs/ROADMAP_STATUS.md
git commit -m "docs: Sub-project D complete — selftest gate, Playwright probe, LLM proposals"
```

- [ ] **Step 6: Push to origin**

```bash
git push origin master
```
Expected: pushes cleanly (or fast-forwards).
