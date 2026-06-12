from __future__ import annotations

from dataclasses import dataclass, field


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


@dataclass
class SessionStep:
    desc: str
    action: str                    # goto | click | fill | assert | api
    ok: bool
    detail: str = ""
    screenshot_path: str = ""
    expectation_key: str = ""      # links a failed step to the expectations catalog


@dataclass
class SessionTrace:
    session: str
    ok: bool
    steps: list[SessionStep] = field(default_factory=list)
    console_events: list[str] = field(default_factory=list)
    network_events: list[str] = field(default_factory=list)
    started_at: float = 0.0
    duration_s: float = 0.0


@dataclass
class DriftFinding:
    session: str
    step: str
    expected: str
    observed: str
    doc_ref: str                   # "path/to/doc §Section" — empty for plain bugs
    kind: str                      # "drift" (doc vs behavior) | "bug" (no doc claim)
    suggestion: str = ""
    screenshot_path: str = ""
