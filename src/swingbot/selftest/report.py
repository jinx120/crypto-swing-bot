from __future__ import annotations

import datetime

from swingbot.decision.proposals import Proposal
from swingbot.selftest import HealthSummary

_CHECK_ICON = {True: "✅", False: "❌"}
_SEV_ICON = {"fatal": "🔴", "warn": "⚠️", "info": "ℹ️"}


_DEVLOG_HEADER_MARKER = "Newest first.\n"


def _insert_devlog_line(devlog_path: str, line: str) -> None:
    """Insert directly under the header so the log stays newest-first."""
    try:
        with open(devlog_path) as fh:
            content = fh.read()
    except OSError:
        content = "# Devlog\n\nRunning log of platform improvements. Newest first.\n"
    i = content.find(_DEVLOG_HEADER_MARKER)
    if i == -1:
        content = line + "\n" + content
    else:
        j = i + len(_DEVLOG_HEADER_MARKER)
        content = content[:j] + "\n" + line + "\n" + content[j:]
    with open(devlog_path, "w") as fh:
        fh.write(content)


_ROADMAP_POINTER_PREFIX = "**Usage Agent:"


def update_roadmap_next_action(roadmap_path: str, drift_count: int) -> None:
    """Prepend a pointer line inside the NEXT ACTION block (idempotent: any
    previous usage-agent pointer line is replaced, the rest is untouched)."""
    try:
        with open(roadmap_path) as fh:
            lines = fh.read().splitlines(keepends=True)
    except OSError:
        return
    lines = [ln for ln in lines if not ln.startswith(_ROADMAP_POINTER_PREFIX)]
    pointer = (f"{_ROADMAP_POINTER_PREFIX} {drift_count} drift finding(s) pending — "
               f"see docs/SELFTEST_REPORT.md §Drift Findings and the Health tab.**\n")
    out, inserted = [], False
    for ln in lines:
        out.append(ln)
        if not inserted and ln.startswith("## ▶ NEXT ACTION"):
            out += ["\n", pointer]
            inserted = True
    if not inserted:
        out = [pointer, "\n"] + out
    with open(roadmap_path, "w") as fh:
        fh.write("".join(out))


def write_report(summary: HealthSummary, proposals: list[Proposal],
                 report_path: str, devlog_path: str,
                 traces=None, drift=None) -> None:
    traces = traces or []
    drift = drift or []
    status = "GREEN" if summary.green else "RED"
    status_emoji = "🟢" if summary.green else "🔴"
    dt_str = datetime.datetime.fromtimestamp(
        summary.started_at, tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

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

    lines += ["", "## Usage Sessions", ""]
    if traces:
        lines += ["| Session | Status | Steps | Duration |",
                  "|---------|--------|-------|----------|"]
        for t in traces:
            passed = sum(1 for s in t.steps if s.ok)
            lines.append(f"| {t.session} | {'✅' if t.ok else '❌'} "
                         f"| {passed}/{len(t.steps)} | {t.duration_s}s |")
        failed = [(t.session, s) for t in traces for s in t.steps if not s.ok]
        if failed:
            lines += ["", "**Failed steps:**", ""]
            for session, s in failed:
                lines.append(f"- `{session}` — {s.desc}: {s.detail[:160]}")
    else:
        lines.append("_Sessions skipped._")

    lines += ["", "## Drift Findings", ""]
    if drift:
        lines += ["| Session | Kind | Expected | Observed | Doc ref |",
                  "|---------|------|----------|----------|---------|"]
        for d in drift:
            lines.append(f"| {d.session} | {d.kind} | {d.expected[:60]} "
                         f"| {d.observed[:60]} | {d.doc_ref[:60]} |")
    else:
        lines.append("_No drift — observed behavior matches the docs._")

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
    passed_sessions = sum(1 for t in traces if t.ok)
    devlog_line = (
        f"{dt_str}  {status}  {summary.duration_s}s  "
        f"{check_icons}  ui:{fatal_count}fatal  "
        f"sessions:{passed_sessions}/{len(traces)}  drift:{len(drift)}  "
        f"proposals:{len(proposals)}"
    )
    _insert_devlog_line(devlog_path, devlog_line)
