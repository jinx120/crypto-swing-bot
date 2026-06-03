from swingbot.decision.brain import DecisionBrain
from swingbot.decision.ollama import OllamaResult
from swingbot.decision.proposals import IssueLog, ProposalStore


class FakeOllama:
    def __init__(self, result): self.result = result
    def generate_json(self, prompt, schema): return self.result


class FakeProfiles:
    def __init__(self): self.armed = []; self.saved = {}; self.eligible = {}; self.settings = {}
    def save(self, name, profile): self.saved[name] = profile
    def arm(self, name): self.armed.append(name)
    def disarm(self, name): self.armed = [n for n in self.armed if n != name]
    def set_live_eligible(self, name, v): self.eligible[name] = v
    def list_armed(self): return list(self.armed)
    def get_portfolio_settings(self):
        return {"max_concurrent": 5, "max_total_deployed_frac": 0.8,
                "brain_autonomous_mode": self.settings.get("auto", False),
                "brain_confidence_threshold": 0.7, **self.settings}
    def set_portfolio_settings(self, patch): self.settings.update(patch)


class FakeController:
    def __init__(self): self.reloaded = 0
    def status(self): return {"portfolio": {"equity": 1000, "open_positions": 0,
                                            "deployed_frac": 0.0}, "strategies": []}
    def reload(self): self.reloaded += 1
    def flatten(self, name): pass


def _brain(tmp_path, ollama, profiles=None, notifier_events=None):
    discovery = {"rows": [{"symbol": "BTC/USD", "archetype": "balanced",
                           "eligible_now": True, "metrics": {"expectancy": 1.0}}]}

    class _Notif:
        def send(self, ev, payload):
            if notifier_events is not None: notifier_events.append(ev)
            return True
    return DecisionBrain(
        profiles=profiles or FakeProfiles(), controller=FakeController(),
        ollama_factory=lambda settings: ollama,
        proposals=ProposalStore(str(tmp_path / "p.json")),
        issues=IssueLog(str(tmp_path / "i.json")),
        notifier=_Notif(),
        get_discovery=lambda: discovery,
        backtest_ok=lambda s, a, p: True)


def test_recommend_stores_and_guardrails(tmp_path):
    data = {"proposals": [{"action": "arm",
            "target": {"symbol": "BTC/USD", "archetype": "balanced"},
            "rationale": "good", "confidence": 0.9}]}
    brain = _brain(tmp_path, FakeOllama(OllamaResult(ok=True, data=data)))
    out = brain.recommend()
    props = brain.proposals.all()
    assert out["proposals"] == 1 and props[0].guardrail_status == "approved"
    assert props[0].status == "pending"             # recommend-only: not applied


def test_recommend_ollama_failure_logs_issue(tmp_path):
    events = []
    brain = _brain(tmp_path, FakeOllama(OllamaResult(ok=False, error="down")),
                   notifier_events=events)
    out = brain.recommend()
    assert out["error"] and brain.issues.all()[0]["kind"] == "ollama_error"
    assert "blocked_or_error" in events


def test_autonomous_applies_approved_above_threshold(tmp_path):
    profiles = FakeProfiles(); profiles.settings["auto"] = True
    data = {"proposals": [{"action": "arm",
            "target": {"symbol": "BTC/USD", "archetype": "balanced"},
            "rationale": "good", "confidence": 0.95}]}
    brain = _brain(tmp_path, FakeOllama(OllamaResult(ok=True, data=data)), profiles=profiles)
    brain.recommend()
    applied = [p for p in brain.proposals.all() if p.status == "applied"]
    assert len(applied) == 1 and applied[0].source == "autonomous"
    assert profiles.armed                            # arm path ran


def test_autonomous_skips_below_threshold(tmp_path):
    profiles = FakeProfiles(); profiles.settings["auto"] = True
    data = {"proposals": [{"action": "arm",
            "target": {"symbol": "BTC/USD", "archetype": "balanced"},
            "rationale": "meh", "confidence": 0.5}]}
    brain = _brain(tmp_path, FakeOllama(OllamaResult(ok=True, data=data)), profiles=profiles)
    brain.recommend()
    assert not [p for p in brain.proposals.all() if p.status == "applied"]


def test_apply_disarm_path(tmp_path):
    profiles = FakeProfiles(); profiles.armed = ["disc-x"]
    data = {"proposals": [{"action": "disarm", "target": {"name": "disc-x"},
                           "rationale": "stale", "confidence": 0.8}]}
    brain = _brain(tmp_path, FakeOllama(OllamaResult(ok=True, data=data)), profiles=profiles)
    brain.recommend()
    pid = brain.proposals.all()[0].id
    brain.apply(pid)
    assert "disc-x" not in profiles.armed and brain.proposals.get(pid).status == "applied"


def test_daily_summary_counts_and_notifies(tmp_path):
    events = []
    data = {"proposals": [{"action": "arm",
            "target": {"symbol": "BTC/USD", "archetype": "balanced"},
            "rationale": "good", "confidence": 0.9}]}
    brain = _brain(tmp_path, FakeOllama(OllamaResult(ok=True, data=data)),
                   notifier_events=events)
    brain.recommend()
    s = brain.daily_summary()
    assert s["pending"] == 1 and "daily_summary" in events
