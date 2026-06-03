from swingbot.decision.proposals import IssueLog, ProposalStore, make_proposal


def test_make_proposal_stable_id():
    a = make_proposal("arm", {"symbol": "BTC/USD", "archetype": "balanced"}, "r", 0.9, now=100)
    b = make_proposal("arm", {"archetype": "balanced", "symbol": "BTC/USD"}, "r2", 0.1, now=200)
    assert a.id == b.id                              # id ignores rationale/confidence/key order


def test_store_roundtrip_and_supersede(tmp_path):
    path = str(tmp_path / "proposals.json")
    s = ProposalStore(path)
    p = make_proposal("arm", {"symbol": "ETH/USD", "archetype": "momo"}, "r", 0.8, now=1)
    s.add_many([p])
    assert ProposalStore(path).get(p.id).status == "pending"
    s.supersede_pending()
    assert s.get(p.id).status == "superseded"


def test_mark_applied(tmp_path):
    s = ProposalStore(str(tmp_path / "p.json"))
    p = make_proposal("disarm", {"name": "x"}, "r", 0.5, now=1)
    s.add_many([p])
    s.mark(p.id, "applied", applied_at=42)
    got = s.get(p.id)
    assert got.status == "applied" and got.applied_at == 42


def test_issue_log_caps_and_persists(tmp_path):
    log = IssueLog(str(tmp_path / "issues.json"), cap=2)
    log.add("ollama_error", "a"); log.add("parse_dropped", "b"); log.add("blocked", "c")
    items = IssueLog(str(tmp_path / "issues.json")).all()
    assert len(items) == 2 and items[-1]["detail"] == "c"   # oldest dropped
