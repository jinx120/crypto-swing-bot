from __future__ import annotations

import datetime

from swingbot.decision.guardrails import NON_EXECUTABLE_ACTIONS
from swingbot.decision.ollama import OllamaClient
from swingbot.decision.proposals import Proposal, ProposalStore, make_proposal
from swingbot.notify import DiscordNotifier
from swingbot.selftest import HealthSummary

_ALLOWED_ACTIONS = {"tune", "ui_fix", "doc_fix", "portfolio_settings"}

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
    dt = datetime.datetime.fromtimestamp(
        summary.started_at, tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
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
        if action in NON_EXECUTABLE_ACTIONS:
            p.guardrail_status, p.guardrail_reason = "approved", ""
        else:
            # No live portfolio/backtest context here — an "approved" stamp
            # would be a lie (audit finding #4). The live brain re-evaluates.
            p.guardrail_status = "pending"
            p.guardrail_reason = ("deferred: needs live portfolio context — "
                                  "run Recommend on the Brain page to evaluate")
        proposals.append(p)

    if proposals:
        store.add_many(proposals)
        notifier.send("selftest_proposals", {"count": len(proposals)})

    return proposals
