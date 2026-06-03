from __future__ import annotations

import time

from swingbot import presets as presets_mod
from swingbot.decision import guardrails as gr
from swingbot.decision.prompt import PROPOSAL_SCHEMA, build_prompt, parse_proposals


class DecisionBrain:
    """Orchestrates a recommend run and applies proposals. All public methods are
    safe to call from a background thread and never raise into the caller."""

    def __init__(self, *, profiles, controller, ollama_factory, proposals, issues,
                 notifier, get_discovery, backtest_ok):
        self.profiles = profiles
        self.controller = controller
        self.ollama_factory = ollama_factory          # settings -> OllamaClient
        self.proposals = proposals
        self.issues = issues
        self.notifier = notifier
        self.get_discovery = get_discovery
        self.backtest_ok = backtest_ok

    # ---- context ----
    def _context(self) -> dict:
        st = self.controller.status() or {}
        pf = st.get("portfolio") or {}
        s = self.profiles.get_portfolio_settings()
        strat_kill = any((x.get("risk") or {}).get("kill_switch", {}).get("active")
                         for x in (st.get("strategies") or []))
        return {
            "equity": pf.get("equity", 0.0),
            "open_position_count": pf.get("open_positions", 0),
            "deployed_frac": pf.get("deployed_frac", 0.0),
            "max_concurrent": s.get("max_concurrent", 5),
            "max_total_deployed_frac": s.get("max_total_deployed_frac", 0.80),
            "kill_switch": bool(pf.get("kill_switch")) or strat_kill,
            "armed": self.profiles.list_armed(),
        }

    # ---- recommend ----
    def recommend(self, source: str = "manual") -> dict:
        settings = self.profiles.get_portfolio_settings()
        disc = self.get_discovery() or {}
        eligible = [r for r in (disc.get("rows") or []) if r.get("eligible_now")]
        ctx = self._context()
        res = self.ollama_factory(settings).generate_json(build_prompt(eligible, ctx),
                                                           PROPOSAL_SCHEMA)
        if not res.ok:
            self.issues.add("ollama_error", res.error)
            self.notifier.send("blocked_or_error", {"error": res.error})
            return {"error": res.error, "proposals": 0}

        now = int(time.time())
        parsed, dropped = parse_proposals(res.data, now=now)
        for d in dropped:
            self.issues.add("parse_dropped", d)
        for p in parsed:
            status, reason = gr.evaluate(p, ctx, eligible, self.backtest_ok)
            p.guardrail_status, p.guardrail_reason = status, reason
            p.source = source
            if status == "blocked":
                self.issues.add("blocked", f"{p.action} {p.target}: {reason}")

        self.proposals.supersede_pending()
        self.proposals.add_many(parsed)
        if parsed:
            self.notifier.send("proposals_ready", {"count": len(parsed), "source": source})

        if settings.get("brain_autonomous_mode"):
            thr = settings.get("brain_confidence_threshold", 0.7)
            for p in parsed:
                if p.guardrail_status == "approved" and p.confidence >= thr:
                    self.apply(p.id, source="autonomous")
        return {"error": None, "proposals": len(parsed), "dropped": len(dropped)}

    # ---- apply ----
    def apply(self, proposal_id: str, source: str = "manual") -> dict:
        p = self.proposals.get(proposal_id)
        if p is None:
            return {"ok": False, "error": "unknown proposal"}
        if p.status == "applied":
            return {"ok": True, "already": True}
        try:
            self._dispatch(p)
        except Exception as e:                         # apply failure -> issue, never raises out
            self.issues.add("apply_error", f"{p.action} {p.target}: {e}")
            self.notifier.send("blocked_or_error", {"apply_error": str(e)})
            return {"ok": False, "error": str(e)}
        self.proposals.mark(p.id, "applied", applied_at=int(time.time()), source=source)
        self.notifier.send("autonomous_apply" if source == "autonomous" else "applied",
                           {"action": p.action, "target": p.target})
        return {"ok": True}

    # ---- periodic digest (scheduled externally via /loop or /schedule) ----
    def daily_summary(self) -> dict:
        rows = self.proposals.all()
        summary = {
            "pending": sum(1 for p in rows if p.status == "pending"),
            "applied": sum(1 for p in rows if p.status == "applied"),
            "blocked": sum(1 for p in rows if p.guardrail_status == "blocked"),
            "issues": len(self.issues.all()),
        }
        self.notifier.send("daily_summary", summary)
        return summary

    def _dispatch(self, p) -> None:
        if p.action == "arm":
            arch = next(a for a in presets_mod.ARCHETYPES if a.key == p.target["archetype"])
            profile = presets_mod.archetype_profile(arch, p.target["symbol"], "swing")
            name = f"disc-{p.target['symbol'].replace('/', '').lower()}-{p.target['archetype']}"
            self.profiles.save(name, profile)
            self.profiles.arm(name)
            self.profiles.set_live_eligible(name, True)
            self.controller.reload()
        elif p.action == "disarm":
            self.controller.flatten(p.target["name"])
            self.profiles.disarm(p.target["name"])
            self.controller.reload()
        elif p.action == "tune":
            arch = next(a for a in presets_mod.ARCHETYPES if a.key == p.target["archetype"])
            profile = presets_mod.archetype_profile(arch, p.target["symbol"], "swing")
            profile.update(p.target.get("params") or {})
            name = f"disc-{p.target['symbol'].replace('/', '').lower()}-{p.target['archetype']}"
            self.profiles.save(name, profile)
            self.controller.reload()
        elif p.action == "portfolio_settings":
            self.profiles.set_portfolio_settings(dict(p.target))
            self.controller.reload()
        else:
            raise ValueError(f"unknown action {p.action!r}")
