# Ollama Decision Brain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local-LLM decision brain that turns B2 discovery output + live portfolio context into guardrailed, persistent proposals (arm/disarm/tune/portfolio_settings), recommend-only by default with an opt-in full-autonomous mode, plus Discord notifications and a runtime issues feed.

**Architecture:** A small `decision/` package of independently testable units (`ollama` HTTP client, `prompt` builder/parser, `guardrails`, `proposals` store, `brain` orchestrator) plus a `notify.py` Discord sender. Every brain run executes on a background thread and never raises into trading; the Ollama client is mocked in all tests so the suite stays offline/deterministic. Configuration (model, URL, thresholds, toggles) rides on existing portfolio settings; the Discord webhook URL is a write-only secret.

**Tech Stack:** Python 3.11, stdlib `urllib` (no new deps), FastAPI, pytest, SQLite (`ProfileStore`), Ollama (`qwen2.5`), React/Vite frontend.

---

## Reference: existing interfaces this plan reuses

- `profiles` is a `ProfileStore` (`src/swingbot/profiles.py`): `save(name, dict)`, `get(name)`, `arm(name)`, `disarm(name)`, `set_live_eligible(name, bool)`, `list_armed()`, `get_portfolio_settings()`, `set_portfolio_settings(patch)` (**rejects unknown keys** — must extend `_PORTFOLIO_DEFAULTS`).
- `controller` is the `PortfolioSupervisor`: `status()` → `{"portfolio": {equity, deployed, deployed_frac, open_positions, day_pnl, mode, ...}, "strategies": [{name, symbol, ...}]}`; `reload()`; `flatten(name)`.
- `discovery` rows (`src/swingbot/discovery.py`): each row `{symbol, archetype, label, profile, metrics, eligible_now, fires_now, regime, error}`. Helpers: `good_history(metrics_dict)`, `load_cache(path)`, `save_cache(path, data)`. `app.state.discovery` holds `{status, rows, ...}`.
- `presets` (`src/swingbot/presets.py`): `ARCHETYPES` (each `.key`, `.name`, `.needs_ai`), `archetype_profile(arch, symbol, style)` → profile dict.
- `backtest.run_backtest(df, StrategyProfile, benchmark_df, starting_equity)` → `(trades, Metrics)`; `strategy_search._df_from_market(market, symbol, timeframe, lookback)`, `strategy_search.metrics_dict(m)`.
- `StrategyProfile` tunable numeric fields: `entry_threshold`, `stop_atr_mult`, `take_profit_atr_mult`, `risk_per_trade`, `max_position_frac`.
- Test patterns live in `tests/test_web_discovery.py` (`FakeMarket`, `FakeStore`, `_Ctl`, `create_app` + `TestClient`).

## File structure (created / modified)

| File | Responsibility |
|------|----------------|
| `src/swingbot/decision/__init__.py` | package marker |
| `src/swingbot/decision/ollama.py` | Ollama HTTP client; schema-constrained JSON; never raises |
| `src/swingbot/decision/prompt.py` | prompt builder + JSON→`Proposal` parser/validator; `PROPOSAL_SCHEMA` |
| `src/swingbot/decision/guardrails.py` | pure per-action validation (`evaluate`) |
| `src/swingbot/decision/proposals.py` | `Proposal` dataclass + `ProposalStore` (JSON inbox) + `IssueLog` |
| `src/swingbot/decision/brain.py` | `DecisionBrain` orchestrator (gather→ollama→parse→guardrail→store→notify→autonomous), apply path |
| `src/swingbot/notify.py` | `DiscordNotifier` webhook sender (failure-tolerant) |
| `src/swingbot/profiles.py` | extend `_PORTFOLIO_DEFAULTS`; add `get/set_discord_webhook` |
| `src/swingbot/web.py` | brain endpoints + `auto_recommend` hook in discovery refresh |
| `src/swingbot/webmain.py` | construct + wire `DecisionBrain` |
| `frontend/src/api.js` | brain API client methods |
| `frontend/src/pages/Brain.jsx` | Brain page UI |
| `frontend/src/App.jsx` (+ nav) | route + nav entry |
| `tests/test_decision_*.py`, `tests/test_web_brain.py` | tests |

---

## Task 1: Ollama client (`decision/ollama.py`)

**Files:**
- Create: `src/swingbot/decision/__init__.py`
- Create: `src/swingbot/decision/ollama.py`
- Test: `tests/test_decision_ollama.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_decision_ollama.py
from swingbot.decision.ollama import OllamaClient


def test_generate_json_ok_parses_response():
    def fake_transport(url, payload, timeout):
        assert payload["model"] == "qwen2.5"
        assert payload["format"] == {"type": "object"}
        return {"response": '{"proposals": []}'}
    c = OllamaClient("http://x:11434", "qwen2.5", 5.0, transport=fake_transport)
    res = c.generate_json("hi", {"type": "object"})
    assert res.ok and res.data == {"proposals": []} and res.error is None


def test_generate_json_transport_error_is_caught():
    def boom(url, payload, timeout):
        raise OSError("connection refused")
    c = OllamaClient("http://x:11434", "qwen2.5", 5.0, transport=boom)
    res = c.generate_json("hi", {"type": "object"})
    assert res.ok is False and res.data is None and "connection refused" in res.error


def test_generate_json_bad_json_is_caught():
    c = OllamaClient("http://x", "qwen2.5", 5.0,
                     transport=lambda u, p, t: {"response": "not json{"})
    res = c.generate_json("hi", {"type": "object"})
    assert res.ok is False and "json" in res.error.lower()
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_decision_ollama.py -v`
Expected: FAIL with `ModuleNotFoundError: swingbot.decision.ollama`

- [x] **Step 3: Write minimal implementation**

```python
# src/swingbot/decision/__init__.py
```

```python
# src/swingbot/decision/ollama.py
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass


@dataclass
class OllamaResult:
    ok: bool
    data: dict | None = None
    error: str | None = None


def _urllib_transport(url: str, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


class OllamaClient:
    """Calls Ollama /api/generate with a JSON schema. Never raises: all failures
    (connection, timeout, non-JSON) return OllamaResult(ok=False)."""

    def __init__(self, url: str, model: str, timeout_s: float, transport=None):
        self.url = url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self._transport = transport or _urllib_transport

    def generate_json(self, prompt: str, schema: dict) -> OllamaResult:
        payload = {"model": self.model, "prompt": prompt, "stream": False,
                   "format": schema, "options": {"temperature": 0}}
        try:
            raw = self._transport(f"{self.url}/api/generate", payload, self.timeout_s)
        except Exception as e:                       # network / timeout / HTTP error
            return OllamaResult(ok=False, error=f"ollama transport: {e}")
        try:
            data = json.loads(raw["response"])
        except Exception as e:                       # missing key / invalid JSON body
            return OllamaResult(ok=False, error=f"ollama json: {e}")
        if not isinstance(data, dict):
            return OllamaResult(ok=False, error="ollama json: top-level not an object")
        return OllamaResult(ok=True, data=data)
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_decision_ollama.py -v`
Expected: PASS (3 tests)

- [x] **Step 5: Commit**

```bash
git add src/swingbot/decision/__init__.py src/swingbot/decision/ollama.py tests/test_decision_ollama.py
git commit -m "feat(brain): Ollama JSON client that never raises"
```

---

## Task 2: Discord notifier (`notify.py`)

**Files:**
- Create: `src/swingbot/notify.py`
- Test: `tests/test_notify.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_notify.py
from swingbot.notify import DiscordNotifier


def test_sends_when_webhook_configured():
    sent = []
    n = DiscordNotifier(lambda: "http://hook", transport=lambda u, p, t: sent.append((u, p)))
    assert n.send("proposals_ready", {"count": 3}) is True
    assert sent and sent[0][0] == "http://hook" and "proposals_ready" in sent[0][1]["content"]


def test_noop_when_no_webhook():
    sent = []
    n = DiscordNotifier(lambda: None, transport=lambda u, p, t: sent.append(1))
    assert n.send("proposals_ready", {"count": 3}) is False
    assert sent == []


def test_transport_failure_is_swallowed():
    def boom(u, p, t):
        raise OSError("discord down")
    n = DiscordNotifier(lambda: "http://hook", transport=boom)
    assert n.send("blocked_or_error", {"error": "x"}) is False   # never raises
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_notify.py -v`
Expected: FAIL with `ModuleNotFoundError: swingbot.notify`

- [x] **Step 3: Write minimal implementation**

```python
# src/swingbot/notify.py
from __future__ import annotations

import json
import urllib.request


def _urllib_post(url: str, payload: dict, timeout: float) -> None:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=timeout).close()


class DiscordNotifier:
    """Posts compact messages to a Discord webhook. Failure-tolerant: a missing
    webhook or a transport error never raises (returns False)."""

    def __init__(self, webhook_getter, transport=None, timeout_s: float = 5.0):
        self._webhook_getter = webhook_getter
        self._transport = transport or _urllib_post
        self.timeout_s = timeout_s

    def send(self, event_type: str, payload: dict) -> bool:
        url = self._webhook_getter()
        if not url:
            return False
        content = f"**[swingbot:{event_type}]** " + json.dumps(payload, default=str)[:1800]
        try:
            self._transport(url, {"content": content}, self.timeout_s)
            return True
        except Exception:                            # webhook must never touch trading
            return False
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_notify.py -v`
Expected: PASS (3 tests)

- [x] **Step 5: Commit**

```bash
git add src/swingbot/notify.py tests/test_notify.py
git commit -m "feat(brain): failure-tolerant Discord notifier"
```

---

## Task 3: Proposal model + stores (`decision/proposals.py`)

**Files:**
- Create: `src/swingbot/decision/proposals.py`
- Test: `tests/test_decision_proposals.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_decision_proposals.py
from swingbot.decision.proposals import IssueLog, Proposal, ProposalStore, make_proposal


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
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_decision_proposals.py -v`
Expected: FAIL with `ModuleNotFoundError: swingbot.decision.proposals`

- [x] **Step 3: Write minimal implementation**

```python
# src/swingbot/decision/proposals.py
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field


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
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_decision_proposals.py -v`
Expected: PASS (4 tests)

- [x] **Step 5: Commit**

```bash
git add src/swingbot/decision/proposals.py tests/test_decision_proposals.py
git commit -m "feat(brain): Proposal model + JSON inbox + issue log"
```

---

## Task 4: Prompt builder + parser (`decision/prompt.py`)

**Files:**
- Create: `src/swingbot/decision/prompt.py`
- Test: `tests/test_decision_prompt.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_decision_prompt.py
from swingbot.decision.prompt import PROPOSAL_SCHEMA, build_prompt, parse_proposals


def test_build_prompt_includes_context():
    rows = [{"symbol": "BTC/USD", "archetype": "balanced",
             "metrics": {"expectancy": 0.5}, "regime": "uptrend"}]
    ctx = {"equity": 1000, "open_position_count": 1, "max_concurrent": 5,
           "deployed_frac": 0.2, "armed": ["disc-ethusd-momo"]}
    p = build_prompt(rows, ctx)
    assert "BTC/USD" in p and "balanced" in p and "disc-ethusd-momo" in p
    assert "arm" in p and "disarm" in p and "tune" in p and "portfolio_settings" in p


def test_parse_proposals_keeps_valid_drops_invalid():
    data = {"proposals": [
        {"action": "arm", "target": {"symbol": "BTC/USD", "archetype": "balanced"},
         "rationale": "ok", "confidence": 0.9},
        {"action": "fly", "target": {}, "rationale": "bad action", "confidence": 0.5},
        {"action": "disarm", "rationale": "missing target", "confidence": 0.5},
    ]}
    good, dropped = parse_proposals(data, now=1)
    assert len(good) == 1 and good[0].action == "arm"
    assert len(dropped) == 2


def test_parse_proposals_handles_garbage():
    good, dropped = parse_proposals({"nope": 1}, now=1)
    assert good == [] and dropped == ["missing 'proposals' list"]


def test_schema_is_object():
    assert PROPOSAL_SCHEMA["type"] == "object"
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_decision_prompt.py -v`
Expected: FAIL with `ModuleNotFoundError: swingbot.decision.prompt`

- [x] **Step 3: Write minimal implementation**

```python
# src/swingbot/decision/prompt.py
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
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_decision_prompt.py -v`
Expected: PASS (4 tests)

- [x] **Step 5: Commit**

```bash
git add src/swingbot/decision/prompt.py tests/test_decision_prompt.py
git commit -m "feat(brain): prompt builder + strict proposal parser"
```

---

## Task 5: Guardrails (`decision/guardrails.py`)

**Files:**
- Create: `src/swingbot/decision/guardrails.py`
- Test: `tests/test_decision_guardrails.py`

Note: `evaluate` is pure. For `tune` it receives a `backtest_ok(symbol, archetype, params) -> bool`
callback so tests stay offline; the real callback (wired in Task 6) re-backtests and checks
`good_history`.

- [x] **Step 1: Write the failing test**

```python
# tests/test_decision_guardrails.py
from swingbot.decision.guardrails import evaluate
from swingbot.decision.proposals import make_proposal

ELIGIBLE = [{"symbol": "BTC/USD", "archetype": "balanced"}]
CTX = {"open_position_count": 1, "max_concurrent": 5, "deployed_frac": 0.2,
       "max_total_deployed_frac": 0.80, "armed": ["disc-ethusd-momo"], "kill_switch": False}


def _ev(p, **over):
    ctx = {**CTX, **over.pop("ctx", {})}
    return evaluate(p, ctx, ELIGIBLE, backtest_ok=over.get("backtest_ok", lambda *a: True))


def test_arm_approved_for_eligible_candidate():
    p = make_proposal("arm", {"symbol": "BTC/USD", "archetype": "balanced"}, "r", 0.9, now=1)
    assert _ev(p) == ("approved", "")


def test_arm_blocked_when_not_eligible():
    p = make_proposal("arm", {"symbol": "DOGE/USD", "archetype": "balanced"}, "r", 0.9, now=1)
    assert _ev(p)[0] == "blocked"


def test_arm_blocked_at_max_concurrent():
    p = make_proposal("arm", {"symbol": "BTC/USD", "archetype": "balanced"}, "r", 0.9, now=1)
    assert _ev(p, ctx={"open_position_count": 5})[0] == "blocked"


def test_arm_blocked_when_kill_switch():
    p = make_proposal("arm", {"symbol": "BTC/USD", "archetype": "balanced"}, "r", 0.9, now=1)
    assert _ev(p, ctx={"kill_switch": True})[0] == "blocked"


def test_disarm_requires_armed():
    ok = make_proposal("disarm", {"name": "disc-ethusd-momo"}, "r", 0.5, now=1)
    bad = make_proposal("disarm", {"name": "ghost"}, "r", 0.5, now=1)
    assert _ev(ok)[0] == "approved" and _ev(bad)[0] == "blocked"


def test_tune_param_bounds_and_backtest():
    inb = make_proposal("tune", {"symbol": "BTC/USD", "archetype": "balanced",
                                  "params": {"entry_threshold": 0.7}}, "r", 0.8, now=1)
    oob = make_proposal("tune", {"symbol": "BTC/USD", "archetype": "balanced",
                                 "params": {"entry_threshold": 5.0}}, "r", 0.8, now=1)
    fails = make_proposal("tune", {"symbol": "BTC/USD", "archetype": "balanced",
                                   "params": {"entry_threshold": 0.7}}, "r", 0.8, now=1)
    assert _ev(inb)[0] == "approved"
    assert _ev(oob)[0] == "blocked"
    assert _ev(fails, backtest_ok=lambda *a: False)[0] == "blocked"


def test_portfolio_settings_clamp():
    ok = make_proposal("portfolio_settings", {"max_concurrent": 4}, "r", 0.5, now=1)
    bad = make_proposal("portfolio_settings", {"max_total_deployed_frac": 0.99}, "r", 0.5, now=1)
    assert _ev(ok)[0] == "approved" and _ev(bad)[0] == "blocked"
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_decision_guardrails.py -v`
Expected: FAIL with `ModuleNotFoundError: swingbot.decision.guardrails`

- [x] **Step 3: Write minimal implementation**

```python
# src/swingbot/decision/guardrails.py
from __future__ import annotations

from swingbot.decision.proposals import Proposal

TUNE_BOUNDS = {
    "entry_threshold": (0.3, 0.95),
    "stop_atr_mult": (0.5, 4.0),
    "take_profit_atr_mult": (1.0, 6.0),
    "risk_per_trade": (0.0025, 0.03),
    "max_position_frac": (0.05, 0.5),
}
SETTINGS_BOUNDS = {
    "max_concurrent": (1, 20),
    "max_total_deployed_frac": (0.0, 0.90),
    "portfolio_daily_loss_limit_pct": (0.0, 0.20),
}
_OPEN = "approved", ""


def _block(reason: str):
    return "blocked", reason


def evaluate(p: Proposal, ctx: dict, eligible_rows: list[dict], backtest_ok) -> tuple[str, str]:
    """Pure pre-apply gate. Returns (status, reason). backtest_ok(symbol, archetype, params)
    -> bool is only consulted for `tune`."""
    if p.action == "arm":
        sym, arch = p.target.get("symbol"), p.target.get("archetype")
        if not any(r.get("symbol") == sym and r.get("archetype") == arch for r in eligible_rows):
            return _block(f"{sym}/{arch} is not a currently-eligible candidate")
        if ctx.get("kill_switch"):
            return _block("portfolio kill switch active")
        if ctx.get("open_position_count", 0) >= ctx.get("max_concurrent", 5):
            return _block("max concurrent positions reached")
        if ctx.get("deployed_frac", 0.0) >= ctx.get("max_total_deployed_frac", 0.80):
            return _block("deployed-capital cap reached")
        return _OPEN

    if p.action == "disarm":
        if p.target.get("name") not in (ctx.get("armed") or []):
            return _block(f"{p.target.get('name')!r} is not armed")
        return _OPEN

    if p.action == "tune":
        params = p.target.get("params") or {}
        if not params:
            return _block("tune has no params")
        for field, val in params.items():
            if field not in TUNE_BOUNDS:
                return _block(f"non-tunable field {field!r}")
            lo, hi = TUNE_BOUNDS[field]
            if not isinstance(val, (int, float)) or not (lo <= val <= hi):
                return _block(f"{field}={val} out of bounds [{lo}, {hi}]")
        if not backtest_ok(p.target.get("symbol"), p.target.get("archetype"), params):
            return _block("tuned profile fails good_history backtest")
        return _OPEN

    if p.action == "portfolio_settings":
        if not p.target:
            return _block("no settings to change")
        for field, val in p.target.items():
            if field not in SETTINGS_BOUNDS:
                return _block(f"unknown setting {field!r}")
            lo, hi = SETTINGS_BOUNDS[field]
            if not isinstance(val, (int, float)) or not (lo <= val <= hi):
                return _block(f"{field}={val} out of bounds [{lo}, {hi}]")
        return _OPEN

    return _block(f"unknown action {p.action!r}")
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_decision_guardrails.py -v`
Expected: PASS (7 tests)

- [x] **Step 5: Commit**

```bash
git add src/swingbot/decision/guardrails.py tests/test_decision_guardrails.py
git commit -m "feat(brain): pure per-action guardrails"
```

---

## Task 6: Brain orchestrator (`decision/brain.py`)

**Files:**
- Create: `src/swingbot/decision/brain.py`
- Test: `tests/test_decision_brain.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_decision_brain.py
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
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_decision_brain.py -v`
Expected: FAIL with `ModuleNotFoundError: swingbot.decision.brain`

- [x] **Step 3: Write minimal implementation**

```python
# src/swingbot/decision/brain.py
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
        self.proposals.mark(p.id, "applied", applied_at=int(time.time()))
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
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_decision_brain.py -v`
Expected: PASS (6 tests)

- [x] **Step 5: Commit**

```bash
git add src/swingbot/decision/brain.py tests/test_decision_brain.py
git commit -m "feat(brain): DecisionBrain orchestrator + apply paths + autonomy"
```

---

## Task 7: Settings + webhook persistence (`profiles.py`)

**Files:**
- Modify: `src/swingbot/profiles.py` (extend `_PORTFOLIO_DEFAULTS`; add webhook getter/setter)
- Test: `tests/test_brain_settings.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_brain_settings.py
from swingbot.profiles import ProfileStore


def test_brain_defaults_present(tmp_path):
    s = ProfileStore(str(tmp_path / "db.sqlite")).get_portfolio_settings()
    assert s["brain_model"] == "qwen2.5"
    assert s["brain_ollama_url"] == "http://localhost:11434"
    assert s["brain_confidence_threshold"] == 0.7
    assert s["brain_timeout_s"] == 30
    assert s["brain_autonomous_mode"] is False
    assert s["brain_auto_recommend"] is False


def test_brain_settings_are_writable(tmp_path):
    p = ProfileStore(str(tmp_path / "db.sqlite"))
    p.set_portfolio_settings({"brain_model": "llama3", "brain_autonomous_mode": True})
    s = p.get_portfolio_settings()
    assert s["brain_model"] == "llama3" and s["brain_autonomous_mode"] is True


def test_discord_webhook_roundtrip_write_only(tmp_path):
    p = ProfileStore(str(tmp_path / "db.sqlite"))
    assert p.get_discord_webhook() is None
    p.set_discord_webhook("http://hook")
    assert p.get_discord_webhook() == "http://hook"
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_brain_settings.py -v`
Expected: FAIL (`brain_model` KeyError)

- [x] **Step 3: Write minimal implementation**

In `src/swingbot/profiles.py`, replace the `_PORTFOLIO_DEFAULTS` dict (currently lines 113-118) with:

```python
    _PORTFOLIO_DEFAULTS = {
        "max_concurrent": 5,
        "max_total_deployed_frac": 0.80,
        "portfolio_daily_loss_limit_pct": 0.08,
        "default_symbol": "",
        # --- decision brain config ---
        "brain_model": "qwen2.5",
        "brain_ollama_url": "http://localhost:11434",
        "brain_confidence_threshold": 0.7,
        "brain_timeout_s": 30,
        "brain_autonomous_mode": False,
        "brain_auto_recommend": False,
    }
```

Then add these methods after `set_watchlist` (end of the class):

```python
    def get_discord_webhook(self) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key='discord_webhook'").fetchone()
        return row[0] if row and row[0] else None

    def set_discord_webhook(self, url: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('discord_webhook', ?)",
            (url or "",))
        self._conn.commit()
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_brain_settings.py -v`
Expected: PASS (3 tests)

- [x] **Step 5: Run the full settings/profiles suite to confirm no regression**

Run: `.venv/bin/python -m pytest tests/test_profiles.py tests/test_profiles_armed.py -q`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add src/swingbot/profiles.py tests/test_brain_settings.py
git commit -m "feat(brain): brain config in portfolio settings + webhook store"
```

---

## Task 8: Web endpoints (`web.py`)

**Files:**
- Modify: `src/swingbot/web.py` (body models near line 74; `create_app` signature line 80; new routes after the discovery routes ~line 373; extend `PortfolioSettingsBody`; webhook in cred routes)
- Test: `tests/test_web_brain.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_web_brain.py
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
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_web_brain.py -v`
Expected: FAIL (`create_app` has no `brain` kwarg / routes missing)

- [x] **Step 3: Write minimal implementation**

In `src/swingbot/web.py`, extend `PortfolioSettingsBody` (after line 50, before its closing) to include the brain fields:

```python
class PortfolioSettingsBody(BaseModel):
    max_concurrent: int | None = None
    max_total_deployed_frac: float | None = None
    portfolio_daily_loss_limit_pct: float | None = None
    default_symbol: str | None = None
    brain_model: str | None = None
    brain_ollama_url: str | None = None
    brain_confidence_threshold: float | None = None
    brain_timeout_s: int | None = None
    brain_autonomous_mode: bool | None = None
    brain_auto_recommend: bool | None = None
```

Add a body model next to the other brain-adjacent models (after `DiscoveryArmBody`, ~line 78):

```python
class WebhookBody(BaseModel):
    url: str
```

Change the `create_app` signature (line 80-81) to accept `brain`:

```python
def create_app(controller, profiles, creds, token: str, store=None, market=None,
               backfiller=None, discovery=None, discovery_cache_path=None,
               brain=None) -> FastAPI:
```

Add the brain routes immediately after the `discovery_arm` route (after current line 373):

```python
    # ---- decision brain ----
    def _require_brain():
        if brain is None:
            raise HTTPException(status_code=503, detail="decision brain is not configured")

    @app.post("/api/brain/recommend")
    def brain_recommend(_=Depends(require_token)):
        _require_brain()
        threading.Thread(target=lambda: brain.recommend(source="manual"),
                         daemon=True).start()
        return {"started": True}

    @app.get("/api/brain/proposals")
    def brain_proposals():
        if brain is None:
            return []
        from dataclasses import asdict
        return [asdict(p) for p in brain.proposals.all()]

    @app.post("/api/brain/proposals/{pid}/apply")
    def brain_apply(pid: str, _=Depends(require_token)):
        _require_brain()
        return brain.apply(pid, source="manual")

    @app.post("/api/brain/proposals/{pid}/dismiss")
    def brain_dismiss(pid: str, _=Depends(require_token)):
        _require_brain()
        brain.proposals.mark(pid, "dismissed")
        return {"ok": True}

    @app.get("/api/brain/issues")
    def brain_issues():
        return brain.issues.all() if brain is not None else []

    @app.post("/api/brain/summary")
    def brain_summary(_=Depends(require_token)):
        _require_brain()
        return brain.daily_summary()

    @app.put("/api/brain/webhook")
    def brain_set_webhook(body: WebhookBody, _=Depends(require_token)):
        if profiles is not None:
            profiles.set_discord_webhook(body.url)
        return {"configured": bool(body.url)}

    @app.get("/api/brain/webhook")
    def brain_get_webhook():
        configured = bool(profiles and profiles.get_discord_webhook())
        return {"configured": configured}            # never returns the URL
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_web_brain.py -v`
Expected: PASS (6 tests)

- [x] **Step 5: Confirm existing web tests still pass**

Run: `.venv/bin/python -m pytest tests/test_web_discovery.py -q`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add src/swingbot/web.py tests/test_web_brain.py
git commit -m "feat(brain): web endpoints (recommend/proposals/apply/dismiss/issues/webhook)"
```

---

## Task 9: Wire brain into server + auto_recommend hook (`webmain.py`, `web.py`)

**Files:**
- Modify: `src/swingbot/webmain.py` (construct `DecisionBrain`, pass to `create_app`)
- Modify: `src/swingbot/web.py` (`auto_recommend` hook at end of the discovery refresh job)
- Test: `tests/test_web_brain_autorecommend.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_web_brain_autorecommend.py
import time
from fastapi.testclient import TestClient

from swingbot.web import create_app


class _Ctl:
    def status(self): return {"portfolio": {}, "strategies": []}
    def reload(self): pass


class FakeProfiles:
    def __init__(self, auto): self._auto = auto
    def get_watchlist(self): return ["BTC/USD"]
    def get_portfolio_settings(self): return {"brain_auto_recommend": self._auto}


class FakeDiscovery:
    def sweep(self, symbols, window_key="full", max_symbols=50): return []


class FakeBrain:
    def __init__(self): self.calls = []
    def recommend(self, source="manual"): self.calls.append(source)


def _client(auto):
    brain = FakeBrain()
    app = create_app(_Ctl(), profiles=FakeProfiles(auto), creds=None, token="t",
                     discovery=FakeDiscovery(), brain=brain)
    return TestClient(app), brain


def _wait(brain):
    for _ in range(50):
        if brain.calls: return
        time.sleep(0.02)


def test_auto_recommend_fires_after_sweep_when_enabled():
    client, brain = _client(auto=True)
    client.post("/api/discovery/refresh", headers={"x-token": "t"},
                json={"scope": "watchlist"})
    _wait(brain)
    assert brain.calls == ["auto-after-discovery"]


def test_auto_recommend_silent_when_disabled():
    client, brain = _client(auto=False)
    client.post("/api/discovery/refresh", headers={"x-token": "t"},
                json={"scope": "watchlist"})
    time.sleep(0.3)
    assert brain.calls == []
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_web_brain_autorecommend.py -v`
Expected: FAIL (no auto-recommend hook; brain never called)

- [x] **Step 3: Write minimal implementation**

In `src/swingbot/web.py`, inside the `discovery_refresh` route's `job()` function, after the
successful-sweep block writes `app.state.discovery = result` and saves the cache (current line
~349), append the auto-recommend hook so the success path ends:

```python
                app.state.discovery = result
                if discovery_cache_path:
                    discovery_mod.save_cache(discovery_cache_path, result)
                if (brain is not None and profiles is not None
                        and profiles.get_portfolio_settings().get("brain_auto_recommend")):
                    brain.recommend(source="auto-after-discovery")
```

In `src/swingbot/webmain.py`, after `discovery = DiscoveryEngine(market)` (line 51) and before
`create_app`, construct the brain:

```python
    from swingbot.decision.brain import DecisionBrain
    from swingbot.decision.ollama import OllamaClient
    from swingbot.decision.proposals import IssueLog, ProposalStore
    from swingbot.notify import DiscordNotifier
    from swingbot.discovery import good_history
    from swingbot.strategy_search import _df_from_market, metrics_dict
    from swingbot.backtest import run_backtest
    from swingbot.presets import STYLE, ARCHETYPES, archetype_profile
    from swingbot.profile import StrategyProfile

    def _ollama_factory(settings):
        return OllamaClient(settings.get("brain_ollama_url", "http://localhost:11434"),
                            settings.get("brain_model", "qwen2.5"),
                            float(settings.get("brain_timeout_s", 30)))

    def _backtest_ok(symbol, archetype_key, params):
        try:
            arch = next(a for a in ARCHETYPES if a.key == archetype_key)
            timeframe = STYLE["swing"]["timeframe"]
            profile_dict = archetype_profile(arch, symbol, "swing")
            profile_dict.update(params or {})
            df = _df_from_market(market, symbol, timeframe, 100_000)
            _trades, m = run_backtest(df, StrategyProfile.from_dict(profile_dict))
            return good_history(metrics_dict(m))
        except Exception:
            return False

    notifier = DiscordNotifier(profiles.get_discord_webhook)
    brain = DecisionBrain(
        profiles=profiles, controller=supervisor, ollama_factory=_ollama_factory,
        proposals=ProposalStore(os.path.join(DATA_DIR, "brain_proposals.json")),
        issues=IssueLog(os.path.join(DATA_DIR, "brain_issues.json")),
        notifier=notifier,
        get_discovery=lambda: getattr(app, "state", None) and app.state.discovery,
        backtest_ok=_backtest_ok)
```

Then pass `brain=brain` to `create_app(...)`. Because `app` is referenced inside
`get_discovery` before assignment, change the discovery `get_discovery` lambda to read it lazily
through a holder; simplest correct form — assign `app` first, then set the attribute:

```python
    app = create_app(controller=supervisor, profiles=profiles, creds=creds,
                     token=token, store=store, market=market, backfiller=backfiller,
                     discovery=discovery,
                     discovery_cache_path=os.path.join(DATA_DIR, "discovery.json"),
                     brain=brain)
    brain.get_discovery = lambda: app.state.discovery
    app.state.archive_config = archive_cfg
```

(Construct `brain` with a temporary `get_discovery=lambda: {}` placeholder, then overwrite it after
`app` exists, as shown.)

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_web_brain_autorecommend.py -v`
Expected: PASS (2 tests)

- [x] **Step 5: Smoke-import webmain to catch wiring errors**

Run: `.venv/bin/python -c "import swingbot.webmain"`
Expected: no output, exit 0

- [x] **Step 6: Commit**

```bash
git add src/swingbot/webmain.py src/swingbot/web.py tests/test_web_brain_autorecommend.py
git commit -m "feat(brain): wire DecisionBrain into server + auto_recommend hook"
```

---

## Task 10: Frontend Brain page (`api.js`, `Brain.jsx`, nav)

**Files:**
- Modify: `frontend/src/api.js` (add brain client methods)
- Create: `frontend/src/pages/Brain.jsx`
- Modify: `frontend/src/App.jsx` (route + nav entry — follow the existing `Discover` wiring)
- Test: `cd frontend && npm run build`

First inspect how `Discover` is registered so this matches exactly:

```bash
grep -n "Discover\|api\." frontend/src/App.jsx | head
grep -n "discovery\|export" frontend/src/api.js | head
```

- [x] **Step 1: Add API client methods**

Append to `frontend/src/api.js` the brain methods, mirroring the existing fetch helper used by
discovery (use the same base/token helper the file already defines — `api.get`/`api.post` or
`request(...)`; match the file's convention):

```javascript
export const brain = {
  proposals: () => api.get("/api/brain/proposals"),
  issues: () => api.get("/api/brain/issues"),
  recommend: () => api.post("/api/brain/recommend", {}),
  apply: (id) => api.post(`/api/brain/proposals/${id}/apply`, {}),
  dismiss: (id) => api.post(`/api/brain/proposals/${id}/dismiss`, {}),
  getWebhook: () => api.get("/api/brain/webhook"),
  setWebhook: (url) => api.put("/api/brain/webhook", { url }),
};
```

(If `api.js` exports a single default object instead of named helpers, add these as keys on that
object instead — match the existing structure rather than introducing a new one.)

- [x] **Step 2: Create the Brain page**

```jsx
// frontend/src/pages/Brain.jsx
import { useEffect, useState } from "react";
import { brain, getPortfolioSettings, setPortfolioSettings } from "../api";

export default function Brain() {
  const [proposals, setProposals] = useState([]);
  const [issues, setIssues] = useState([]);
  const [settings, setSettings] = useState({});
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setProposals(await brain.proposals());
    setIssues(await brain.issues());
    setSettings(await getPortfolioSettings());
  };
  useEffect(() => { refresh(); }, []);

  const runRecommend = async () => {
    setBusy(true);
    await brain.recommend();
    setTimeout(async () => { await refresh(); setBusy(false); }, 1500);
  };
  const toggle = async (key) => {
    const next = { [key]: !settings[key] };
    setSettings(await setPortfolioSettings(next));
  };

  return (
    <div className="brain-page">
      <header>
        <h2>Decision Brain</h2>
        <button onClick={runRecommend} disabled={busy}>
          {busy ? "Thinking…" : "Recommend now"}
        </button>
        <label><input type="checkbox" checked={!!settings.brain_autonomous_mode}
          onChange={() => toggle("brain_autonomous_mode")} /> Autonomous</label>
        <label><input type="checkbox" checked={!!settings.brain_auto_recommend}
          onChange={() => toggle("brain_auto_recommend")} /> Auto after discovery</label>
      </header>

      <section className="proposals">
        {proposals.length === 0 && <p>No proposals yet. Click “Recommend now”.</p>}
        {proposals.map((p) => (
          <div key={p.id} className={`proposal ${p.guardrail_status} ${p.status}`}>
            <div className="title">{p.action} · {JSON.stringify(p.target)}</div>
            <div className="meta">confidence {(p.confidence * 100).toFixed(0)}% ·
              {p.guardrail_status}{p.guardrail_reason ? ` (${p.guardrail_reason})` : ""} ·
              {p.status}</div>
            <div className="rationale">{p.rationale}</div>
            {p.status === "pending" && p.guardrail_status === "approved" && (
              <button onClick={async () => { await brain.apply(p.id); refresh(); }}>Apply</button>
            )}
            {p.status === "pending" && (
              <button onClick={async () => { await brain.dismiss(p.id); refresh(); }}>Dismiss</button>
            )}
          </div>
        ))}
      </section>

      <section className="issues">
        <h3>Issues &amp; shortcomings</h3>
        {issues.length === 0 && <p>No issues logged.</p>}
        <ul>{issues.slice().reverse().map((it, i) => (
          <li key={i}>[{it.kind}] {it.detail}</li>))}</ul>
      </section>
    </div>
  );
}
```

(Adjust the `getPortfolioSettings`/`setPortfolioSettings` import names to whatever `api.js` already
exports for portfolio settings — discover them with the grep in Step 0.)

- [x] **Step 3: Register the route + nav**

Mirror the `Discover` registration found in Step 0. In `frontend/src/App.jsx`, import the page and
add it alongside `Discover` in both the route table and the nav list:

```jsx
import Brain from "./pages/Brain";
// ...in the same place Discover is added to routes/nav:
{ path: "brain", label: "Brain", element: <Brain /> }
```

(Use the exact pattern the file already uses — array entry, `<Route>` element, or nav `<Link>` —
matching `Discover`.)

- [x] **Step 4: Build the frontend**

Run: `cd frontend && npm run build`
Expected: build succeeds with no errors.

- [x] **Step 5: Commit**

```bash
git add frontend/src/api.js frontend/src/pages/Brain.jsx frontend/src/App.jsx
git commit -m "feat(brain): Brain page — proposals inbox, toggles, issues feed"
```

---

## Task 11: Full suite + Playwright verification + docs

**Files:**
- Create: `docs/SUBPROJECT_C_FINDINGS.md`
- Modify: `docs/DEVLOG.md`, `docs/ROADMAP_STATUS.md`
- Modify: `graphify-out/` (regenerated)

- [x] **Step 1: Run the full backend suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all green (prior `250 passed, 5 skipped` plus the new brain tests; record the exact count).

- [x] **Step 2: Build the frontend**

Run: `cd frontend && npm run build`
Expected: success.

- [x] **Step 3: Playwright verification on the live container**

Ask the user for consent to rebuild/restart the container (it interrupts live paper trading):
`docker compose build swingbot && docker compose up -d swingbot`. Then, using the Playwright MCP,
drive the site as the user would and record observations:

  - Open the **Brain** page; click **Recommend now**; confirm proposals render with rationale +
    confidence and no console errors.
  - **Apply** an `arm` proposal; confirm the strategy appears armed on the Strategy/Dashboard view.
  - **Dismiss** a proposal; confirm it leaves the pending set.
  - Toggle **Autonomous** ON, run again; confirm approved + high-confidence proposals auto-apply and
    the issues feed / a test Discord webhook receive the expected events.
  - Confirm blocked proposals appear greyed with a reason; set `brain_model` to a bogus value and
    confirm an issue is logged rather than a crash.

- [x] **Step 4: Write the findings doc**

Create `docs/SUBPROJECT_C_FINDINGS.md` capturing every UX gap, rough edge, and room-for-improvement
observed in Step 3, grouped under: Works as intended / Bugs / UX gaps / Future improvements. This is
the artifact the user reviews manually.

- [x] **Step 5: Update DEVLOG + ROADMAP_STATUS**

Add a Sub-project C entry to `docs/DEVLOG.md`. In `docs/ROADMAP_STATUS.md`: mark row **C** ✅ DONE
with spec/plan paths, set **NEXT ACTION** to "write the Sub-project D spec (self-test gate + LLM
proposals)", and bump the expected pytest count in the "How to resume" section.

- [x] **Step 6: Regenerate the knowledge graph**

Run: `python3 -m graphify update .`
Expected: graph regenerated (node/edge counts increase).

- [x] **Step 7: Commit**

```bash
git add docs/SUBPROJECT_C_FINDINGS.md docs/DEVLOG.md docs/ROADMAP_STATUS.md graphify-out
git commit -m "docs(brain): Sub-project C verification findings + roadmap/devlog update"
```

---

## Done criteria

- `.venv/bin/python -m pytest -q` green (brain units + web endpoints, all offline).
- `cd frontend && npm run build` succeeds.
- Brain page works end-to-end against real Ollama (Playwright-verified); findings doc written.
- Recommend-only is the default; autonomous mode (default OFF) auto-applies only guardrail-approved,
  above-threshold proposals across all action types.
- Discord pings fire for proposals-ready / autonomous-apply / blocks-errors; daily summary available.
- `docs/ROADMAP_STATUS.md` marks C done and points NEXT ACTION at Sub-project D.
```
