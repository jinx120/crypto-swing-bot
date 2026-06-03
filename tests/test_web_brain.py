from fastapi.testclient import TestClient

from swingbot.web import create_app


class _Ctl:
    def status(self): return {"portfolio": {}, "strategies": []}
    def reload(self): pass
    def flatten(self, name): pass


class FakeBrain:
    def __init__(self):
        from swingbot.decision.proposals import IssueLog, ProposalStore, make_proposal
        import tempfile, os
        d = tempfile.mkdtemp()
        self.proposals = ProposalStore(os.path.join(d, "p.json"))
        self.issues = IssueLog(os.path.join(d, "i.json"))
        self.proposals.add_many([make_proposal("arm",
            {"symbol": "BTC/USD", "archetype": "balanced"}, "r", 0.9, now=1)])
        self.recommended = 0; self.applied = []; self.dismissed = []
    def recommend(self, source="manual"): self.recommended += 1; return {"proposals": 1}
    def apply(self, pid, source="manual"): self.applied.append(pid); return {"ok": True}
    def daily_summary(self): return {"pending": 1, "applied": 0, "blocked": 0, "issues": 0}


def _client():
    brain = FakeBrain()
    app = create_app(_Ctl(), profiles=None, creds=None, token="t", brain=brain)
    return TestClient(app), brain


def test_recommend_requires_token():
    client, _ = _client()
    assert client.post("/api/brain/recommend").status_code == 401


def test_recommend_and_list_proposals():
    client, brain = _client()
    assert client.post("/api/brain/recommend", headers={"x-token": "t"}).status_code == 200
    rows = client.get("/api/brain/proposals").json()
    assert rows and rows[0]["action"] == "arm"


def test_apply_and_dismiss():
    client, brain = _client()
    pid = brain.proposals.all()[0].id
    assert client.post(f"/api/brain/proposals/{pid}/apply",
                       headers={"x-token": "t"}).status_code == 200
    assert brain.applied == [pid]
    assert client.post(f"/api/brain/proposals/{pid}/dismiss",
                       headers={"x-token": "t"}).status_code == 200


def test_issues_endpoint():
    client, brain = _client()
    brain.issues.add("blocked", "demo")
    assert client.get("/api/brain/issues").json()[-1]["detail"] == "demo"


def test_summary_endpoint():
    client, _ = _client()
    r = client.post("/api/brain/summary", headers={"x-token": "t"})
    assert r.status_code == 200 and r.json()["pending"] == 1


def test_brain_endpoints_503_without_brain():
    app = create_app(_Ctl(), profiles=None, creds=None, token="t")   # brain=None
    c = TestClient(app)
    assert c.post("/api/brain/recommend", headers={"x-token": "t"}).status_code == 503
