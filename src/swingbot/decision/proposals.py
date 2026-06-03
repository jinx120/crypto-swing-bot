from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass


@dataclass
class Proposal:
    id: str
    created_at: int
    action: str                 # arm | disarm | tune | portfolio_settings
    target: dict
    rationale: str
    confidence: float
    guardrail_status: str = "pending"     # pending | approved | blocked
    guardrail_reason: str = ""
    status: str = "pending"               # pending | applied | dismissed | superseded
    applied_at: int | None = None
    source: str = "manual"


def make_proposal(action: str, target: dict, rationale: str, confidence: float,
                  now: int | None = None) -> Proposal:
    now = int(time.time()) if now is None else now
    key = json.dumps({"action": action, "target": target}, sort_keys=True)
    pid = hashlib.sha1(key.encode()).hexdigest()[:12]
    return Proposal(id=pid, created_at=now, action=action, target=target,
                    rationale=rationale, confidence=max(0.0, min(1.0, float(confidence))))


def _atomic_write(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


class ProposalStore:
    """Persistent proposal inbox backed by a JSON file."""

    def __init__(self, path: str):
        self.path = path

    def _load(self) -> list[dict]:
        try:
            with open(self.path) as f:
                return json.load(f)
        except (OSError, ValueError):
            return []

    def all(self) -> list[Proposal]:
        return [Proposal(**d) for d in self._load()]

    def get(self, pid: str) -> Proposal | None:
        return next((p for p in self.all() if p.id == pid), None)

    def add_many(self, proposals: list[Proposal]) -> None:
        existing = {p.id: p for p in self.all()}
        for p in proposals:
            existing[p.id] = p                       # newest wins on id collision
        _atomic_write(self.path, [asdict(p) for p in existing.values()])

    def supersede_pending(self) -> None:
        rows = self.all()
        for p in rows:
            if p.status == "pending":
                p.status = "superseded"
        _atomic_write(self.path, [asdict(p) for p in rows])

    def mark(self, pid: str, status: str, applied_at: int | None = None) -> None:
        rows = self.all()
        for p in rows:
            if p.id == pid:
                p.status = status
                if applied_at is not None:
                    p.applied_at = applied_at
        _atomic_write(self.path, [asdict(p) for p in rows])


class IssueLog:
    """Append-only ring of brain limitations/errors, JSON-backed."""

    def __init__(self, path: str, cap: int = 200):
        self.path = path
        self.cap = cap

    def all(self) -> list[dict]:
        try:
            with open(self.path) as f:
                return json.load(f)
        except (OSError, ValueError):
            return []

    def add(self, kind: str, detail: str) -> None:
        rows = self.all()
        rows.append({"ts": int(time.time()), "kind": kind, "detail": str(detail)})
        _atomic_write(self.path, rows[-self.cap:])
