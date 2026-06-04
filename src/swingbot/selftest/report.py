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
