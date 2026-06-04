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
