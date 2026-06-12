from __future__ import annotations

from swingbot.decision.proposals import Proposal, make_proposal
from swingbot.selftest import DriftFinding, SessionTrace
from swingbot.selftest.expectations import EXPECTATIONS


def reconcile(traces: list[SessionTrace]) -> list[DriftFinding]:
    """Failed steps with an expectation become drift findings (doc claim vs
    observed); failed steps without one are plain bugs."""
    findings: list[DriftFinding] = []
    for t in traces:
        for s in t.steps:
            if s.ok:
                continue
            exp = EXPECTATIONS.get(s.expectation_key)
            if exp is not None:
                findings.append(DriftFinding(
                    session=t.session, step=s.desc,
                    expected=exp.expected, observed=s.detail,
                    doc_ref=f"{exp.doc} {exp.section}", kind="drift",
                    suggestion=(f"update {exp.doc} {exp.section}"
                                if exp.fix_bias == "doc"
                                else f"fix the behavior so that: {exp.expected}"),
                    screenshot_path=s.screenshot_path))
            else:
                findings.append(DriftFinding(
                    session=t.session, step=s.desc,
                    expected="step succeeds", observed=s.detail,
                    doc_ref="", kind="bug",
                    suggestion="investigate the failing step",
                    screenshot_path=s.screenshot_path))
    return findings


def _bias(f: DriftFinding) -> str:
    for exp in EXPECTATIONS.values():
        if f.doc_ref.startswith(exp.doc) and exp.section in f.doc_ref:
            return exp.fix_bias
    return "ui"


def findings_to_proposals(findings: list[DriftFinding]) -> list[Proposal]:
    out: list[Proposal] = []
    for f in findings:
        action = "doc_fix" if (f.kind == "drift" and _bias(f) == "doc") else "ui_fix"
        doc, _, section = f.doc_ref.partition(" ")
        p = make_proposal(
            action=action,
            target={"doc": doc, "section": section, "expected": f.expected,
                    "observed": f.observed, "suggestion": f.suggestion,
                    "session": f.session, "step": f.step},
            rationale=f"usage-agent {f.kind}: expected (per {f.doc_ref or 'session script'}) "
                      f"'{f.expected[:120]}' but observed '{f.observed[:120]}'",
            confidence=0.9 if f.kind == "drift" else 0.6)
        p.source = "usage-agent"
        p.guardrail_status, p.guardrail_reason = "approved", ""
        out.append(p)
    return out
