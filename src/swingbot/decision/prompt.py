from __future__ import annotations

import json

from swingbot.decision.proposals import Proposal, make_proposal

VALID_ACTIONS = {"arm", "disarm", "tune", "portfolio_settings"}

PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "target": {"type": "object"},
                    "rationale": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["action", "target", "rationale", "confidence"],
            },
        }
    },
    "required": ["proposals"],
}

_SYSTEM = """You are a trading-strategy advisor for a long-only crypto swing bot.
Given backtested, currently-eligible strategy candidates and the live portfolio,
propose actions. Allowed actions and their target shapes:
- arm: {"symbol": "<PAIR>", "archetype": "<key>"}  (must be one of the eligible candidates)
- disarm: {"name": "<armed strategy name>"}
- tune: {"symbol": "<PAIR>", "archetype": "<key>", "params": {<field>: <number>}}
- portfolio_settings: {"max_concurrent": <int>?, "max_total_deployed_frac": <0..0.9>?,
                       "portfolio_daily_loss_limit_pct": <0..0.2>?}
Return JSON: {"proposals": [{"action","target","rationale","confidence"}]}.
confidence is 0..1. Only propose what the data supports. Prefer diversification across symbols."""


def build_prompt(eligible_rows: list[dict], ctx: dict) -> str:
    cands = [{"symbol": r.get("symbol"), "archetype": r.get("archetype"),
              "regime": r.get("regime"), "metrics": r.get("metrics")}
             for r in eligible_rows]
    portfolio = {
        "equity": ctx.get("equity"),
        "open_position_count": ctx.get("open_position_count"),
        "max_concurrent": ctx.get("max_concurrent"),
        "deployed_frac": ctx.get("deployed_frac"),
        "armed_strategies": ctx.get("armed"),
    }
    return (f"{_SYSTEM}\n\nELIGIBLE CANDIDATES:\n{json.dumps(cands, default=str)}"
            f"\n\nPORTFOLIO:\n{json.dumps(portfolio, default=str)}\n\nRespond with JSON only.")


def parse_proposals(data: dict, now: int | None = None) -> tuple[list[Proposal], list[str]]:
    items = data.get("proposals") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return [], ["missing 'proposals' list"]
    good: list[Proposal] = []
    dropped: list[str] = []
    for raw in items:
        if not isinstance(raw, dict):
            dropped.append("proposal not an object"); continue
        action = raw.get("action")
        target = raw.get("target")
        if action not in VALID_ACTIONS:
            dropped.append(f"bad action: {action!r}"); continue
        if not isinstance(target, dict) or not target:
            dropped.append(f"missing/empty target for {action}"); continue
        try:
            conf = float(raw.get("confidence", 0.0))
        except (TypeError, ValueError):
            dropped.append(f"bad confidence for {action}"); continue
        good.append(make_proposal(action, target, str(raw.get("rationale", "")), conf, now))
    return good, dropped
