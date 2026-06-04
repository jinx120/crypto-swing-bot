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
