# Sub-project E — Usage Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scripted usage sessions (S1–S6) that drive the app like a user, reconcile observed behavior against documented intent, and emit drift findings as `doc_fix`/`ui_fix` proposals into the existing brain inbox — plus a Health tab, hash routing, and the 7 targeted audit fixes.

**Architecture:** Extends the existing `selftest/` package (one gate, one CLI). Read-only sessions hit the live `:8000` container; mutating sessions hit an ephemeral `uvicorn` on `:8001` with a throwaway `SWINGBOT_DATA_DIR`. Drift findings → `ProposalStore` (`source="usage-agent"`, recommend-only). Artifacts under `DATA_DIR/agent/` so the container can serve them.

**Tech Stack:** Python 3.12 + FastAPI + Playwright (sync), React/Vite frontend, pytest with injectable fakes (no network/browser in unit tests).

**Spec:** `docs/superpowers/specs/2026-06-12-subproject-e-usage-agent-design.md` — treat as final.

**Environment ground rules (from ROADMAP_STATUS.md):**
- Python is `.venv/bin/python` (run pytest as `.venv/bin/python -m pytest`).
- Working tree carries unrelated uncommitted changes (FVG/presets/etc.) — **scope every `git add` to the files named in the task.**
- Any code change requires `docker compose build swingbot && docker compose up -d swingbot` (standing rule; done in Task 10 once, after all code lands — intermediate tasks only need the test suite).
- Suite baseline: `328 passed, 6 skipped`.

---

## File structure

| File | Responsibility |
|---|---|
| `frontend/src/App.jsx` (modify) | hash routing (`#/dashboard` … `#/health`), Health tab |
| `src/swingbot/selftest/__init__.py` (modify) | new dataclasses: `SessionStep`, `SessionTrace`, `DriftFinding` |
| `src/swingbot/selftest/agentstore.py` (create) | `AgentRunStore` — `runs.json` ring under `DATA_DIR/agent/` |
| `src/swingbot/selftest/expectations.py` (create) | expectation catalog + Guide affordance list, all with doc refs |
| `src/swingbot/selftest/ephemeral.py` (create) | `EphemeralApp` — launch/seed/teardown uvicorn on :8001 |
| `src/swingbot/selftest/sessions.py` (create) | `SessionContext`/`SessionRecorder` + sessions S1–S6 |
| `src/swingbot/selftest/drift.py` (create) | trace×expectation → `DriftFinding` → `Proposal` |
| `src/swingbot/selftest/uiprobe.py` (modify) | `ROUTES` → hash routes |
| `src/swingbot/selftest/llm.py` (modify) | `doc_fix` allowed; honest guardrail stamping |
| `src/swingbot/selftest/runner.py` (modify) | sessions stage + drift reconciliation in pipeline |
| `src/swingbot/selftest/report.py` (modify) | sessions/drift report sections; DEVLOG insert-at-top; ROADMAP NEXT-ACTION writer |
| `src/swingbot/selftest/__main__.py` (modify) | `--no-sessions`, `--ephemeral-port`; agent dir; store path fix |
| `src/swingbot/webmain.py` (modify) | `SWINGBOT_PORT` env; pass `agent_dir` to `create_app` |
| `src/swingbot/web.py` (modify) | `/api/agent/runs`, `/runs/latest`, `/artifacts/{name}` |
| `src/swingbot/decision/guardrails.py` (modify) | `NON_EXECUTABLE_ACTIONS = {ui_fix, doc_fix}` |
| `src/swingbot/decision/proposals.py` (modify) | `supersede_pending` carve-out so brain runs don't clear findings |
| `src/swingbot/decision/brain.py` (modify) | supersede carve-out call + clear `_dispatch` rejection for non-executable |
| `frontend/src/pages/Brain.jsx` (modify) | hide Apply for non-executable actions |
| `frontend/src/pages/Health.jsx` (create) | Health tab UI |
| `frontend/src/pages/Discover.jsx` (modify) | `alert()` → inline toast |
| `frontend/src/api.js` (modify) | `agentRuns`, `agentLatest` |
| `frontend/src/guide.md` (modify) | rewrite stale sections; add Discover/Brain/Health |
| Tests | `tests/test_selftest_agentstore.py`, `test_selftest_expectations.py`, `test_selftest_ephemeral.py`, `test_selftest_sessions.py`, `test_selftest_drift.py`, `test_web_agent.py` (create); `test_selftest_uiprobe.py`, `test_selftest_llm.py`, `test_selftest_runner.py`, `test_selftest_report.py`, `test_decision_guardrails.py`, `test_decision_brain.py` (modify) |

---

### Task 1: Hash routing + probe routes (unblocks everything)

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `src/swingbot/selftest/uiprobe.py:7`
- Test: `tests/test_selftest_uiprobe.py`

- [ ] **Step 1: Update the ROUTES test to expect hash routes (failing test)**

In `tests/test_selftest_uiprobe.py`, replace `test_routes_are_dashboard_discover_brain`:

```python
def test_routes_cover_all_tabs_via_hash():
    assert ROUTES == ["/#/dashboard", "/#/strategy", "/#/discover",
                      "/#/brain", "/#/settings", "/#/guide"]


def test_screenshot_name_strips_hash():
    probe = _make_probe()
    page = FakePage()
    _fire_during_goto(page, "pageerror", Exception("oops"))
    result = probe.probe_route("/#/discover", page)
    assert all("discover.png" in f.screenshot_path for f in result)
```

- [ ] **Step 2: Run to verify both fail**

Run: `.venv/bin/python -m pytest tests/test_selftest_uiprobe.py -q`
Expected: 2 FAIL (`ROUTES == ["/", "/discover", "/brain"]`; screenshot name contains `#`).

- [ ] **Step 3: Update uiprobe**

In `src/swingbot/selftest/uiprobe.py` replace the `ROUTES` line and the `shot_name` line:

```python
ROUTES = ["/#/dashboard", "/#/strategy", "/#/discover",
          "/#/brain", "/#/settings", "/#/guide"]
```

```python
        shot_name = route.replace("#", "").strip("/").replace("/", "-") or "index"
```

- [ ] **Step 4: Run uiprobe tests**

Run: `.venv/bin/python -m pytest tests/test_selftest_uiprobe.py -q`
Expected: all PASS.

- [ ] **Step 5: Add hash routing to App.jsx**

In `frontend/src/App.jsx`, replace the `const [tab, setTab] = useState('dashboard')` line with:

```jsx
const TABS = ['dashboard', 'strategy', 'discover', 'brain', 'settings', 'guide']
const tabFromHash = () => {
  const h = window.location.hash.replace(/^#\/?/, '')
  return TABS.includes(h) ? h : 'dashboard'
}
```

(put `TABS`/`tabFromHash` at module level, above `export default function App()`), and inside `App()`:

```jsx
  const [tab, setTabState] = useState(tabFromHash)
  const setTab = (t) => { window.location.hash = `#/${t}` }
  useEffect(() => {
    const onHash = () => setTabState(tabFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
```

The existing nav buttons already call `setTab('…')` — unchanged. Initial load of `/` (no hash) renders dashboard as before.

- [ ] **Step 6: Build frontend**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.jsx src/swingbot/selftest/uiprobe.py tests/test_selftest_uiprobe.py
git commit -m "feat(e): hash routing for all tabs; selftest probe now renders every page"
```

---

### Task 2: Agent data types + runs.json ring store

**Files:**
- Modify: `src/swingbot/selftest/__init__.py`
- Create: `src/swingbot/selftest/agentstore.py`
- Test: `tests/test_selftest_agentstore.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_selftest_agentstore.py`:

```python
import json
import os

from swingbot.selftest import DriftFinding, SessionStep, SessionTrace
from swingbot.selftest.agentstore import AgentRunStore


def _run(ts=1.0, green=True):
    return {"ts": ts, "green": green, "checks": [], "route_findings": [],
            "traces": [], "drift": [], "proposal_ids": []}


def test_types_have_expected_fields():
    s = SessionStep(desc="open dashboard", action="goto", ok=True)
    t = SessionTrace(session="s1-tabs", ok=True, steps=[s])
    d = DriftFinding(session="s1-tabs", step="open dashboard", expected="renders",
                     observed="404", doc_ref="frontend/src/guide.md §x", kind="drift")
    assert s.expectation_key == "" and t.duration_s == 0.0 and d.suggestion == ""


def test_round_trip_and_latest(tmp_path):
    store = AgentRunStore(str(tmp_path / "agent"))
    assert store.all() == [] and store.latest() is None
    store.add(_run(ts=1.0))
    store.add(_run(ts=2.0, green=False))
    assert [r["ts"] for r in store.all()] == [1.0, 2.0]
    assert store.latest()["green"] is False


def test_ring_caps_at_20(tmp_path):
    store = AgentRunStore(str(tmp_path / "agent"), cap=20)
    for i in range(25):
        store.add(_run(ts=float(i)))
    runs = store.all()
    assert len(runs) == 20 and runs[0]["ts"] == 5.0 and runs[-1]["ts"] == 24.0


def test_corrupt_file_tolerated(tmp_path):
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "runs.json").write_text("{not json")
    store = AgentRunStore(str(agent_dir))
    assert store.all() == []
    store.add(_run())
    assert len(store.all()) == 1


def test_creates_dirs_and_screenshot_dir(tmp_path):
    store = AgentRunStore(str(tmp_path / "deep" / "agent"))
    store.add(_run())
    assert os.path.isfile(store.path)
    assert store.screenshot_dir.endswith(os.path.join("agent", "screenshots"))
    assert json.load(open(store.path))[0]["green"] is True
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_selftest_agentstore.py -q`
Expected: FAIL — `ImportError` (no `agentstore`, no new dataclasses).

- [ ] **Step 3: Add dataclasses to `src/swingbot/selftest/__init__.py`**

Append (note `field` import — change line 3 to `from dataclasses import dataclass, field`):

```python
@dataclass
class SessionStep:
    desc: str
    action: str                    # goto | click | fill | assert | api
    ok: bool
    detail: str = ""
    screenshot_path: str = ""
    expectation_key: str = ""      # links a failed step to the expectations catalog


@dataclass
class SessionTrace:
    session: str
    ok: bool
    steps: list[SessionStep] = field(default_factory=list)
    console_events: list[str] = field(default_factory=list)
    network_events: list[str] = field(default_factory=list)
    started_at: float = 0.0
    duration_s: float = 0.0


@dataclass
class DriftFinding:
    session: str
    step: str
    expected: str
    observed: str
    doc_ref: str                   # "path/to/doc §Section" — empty for plain bugs
    kind: str                      # "drift" (doc vs behavior) | "bug" (no doc claim)
    suggestion: str = ""
    screenshot_path: str = ""
```

- [ ] **Step 4: Create `src/swingbot/selftest/agentstore.py`**

```python
from __future__ import annotations

import json
import os


class AgentRunStore:
    """Ring of recent usage-agent runs, JSON-backed under DATA_DIR/agent/.

    Runs are plain dicts (dataclasses serialized with asdict upstream) so the
    file stays readable by the web endpoints without import coupling.
    """

    def __init__(self, agent_dir: str, cap: int = 20):
        self.agent_dir = agent_dir
        self.path = os.path.join(agent_dir, "runs.json")
        self.cap = cap

    @property
    def screenshot_dir(self) -> str:
        return os.path.join(self.agent_dir, "screenshots")

    def all(self) -> list[dict]:
        try:
            with open(self.path) as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def latest(self) -> dict | None:
        runs = self.all()
        return runs[-1] if runs else None

    def add(self, run: dict) -> None:
        os.makedirs(self.agent_dir, exist_ok=True)
        runs = (self.all() + [run])[-self.cap:]
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(runs, f)
        os.replace(tmp, self.path)
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/test_selftest_agentstore.py -q`
Expected: 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/swingbot/selftest/__init__.py src/swingbot/selftest/agentstore.py tests/test_selftest_agentstore.py
git commit -m "feat(e): session/drift dataclasses + AgentRunStore runs.json ring"
```

---

### Task 3: Expectations catalog

**Files:**
- Create: `src/swingbot/selftest/expectations.py`
- Test: `tests/test_selftest_expectations.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_selftest_expectations.py`:

```python
import os

from swingbot.selftest.expectations import EXPECTATIONS, GUIDE_AFFORDANCES, Expectation

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_catalog_is_keyed_consistently():
    for key, exp in EXPECTATIONS.items():
        assert isinstance(exp, Expectation)
        assert exp.key == key
        assert exp.session and exp.expected and exp.doc and exp.section
        assert exp.fix_bias in ("doc", "ui")


def test_every_doc_ref_points_at_existing_file():
    docs = {e.doc for e in EXPECTATIONS.values()}
    docs |= {"frontend/src/guide.md"}
    for doc in docs:
        assert os.path.isfile(os.path.join(_ROOT, doc)), f"missing doc: {doc}"


def test_guide_affordances_shape():
    assert len(GUIDE_AFFORDANCES) >= 5
    for text, route, section in GUIDE_AFFORDANCES:
        assert text and route.startswith("/#/") and section.startswith("§")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_selftest_expectations.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Create `src/swingbot/selftest/expectations.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

_ROADMAP_SPEC = "docs/superpowers/specs/2026-06-02-platform-improvement-roadmap-design.md"
_C_SPEC = "docs/superpowers/specs/2026-06-04-subproject-c-decision-brain-design.md"
_D_SPEC = "docs/superpowers/specs/2026-06-03-subproject-d-self-test-gate-design.md"
_GUIDE = "frontend/src/guide.md"


@dataclass(frozen=True)
class Expectation:
    key: str
    session: str
    expected: str        # the documented claim, human-readable
    doc: str             # repo-relative path of the source document
    section: str         # '§"Section name"'
    fix_bias: str = "ui"  # when violated: "doc" -> doc_fix proposal, "ui" -> ui_fix


def _e(key, session, expected, doc, section, fix_bias="ui"):
    return Expectation(key, session, expected, doc, section, fix_bias)


EXPECTATIONS: dict[str, Expectation] = {e.key: e for e in [
    # S1 — tab navigation
    _e("s1.tab-renders", "s1-tabs",
       "every nav tab renders its key element with no console errors",
       _ROADMAP_SPEC, '§"Sub-project A"'),
    # S2 — guided strategy flow
    _e("s2.backtest-needs-creds", "s2-strategy-flow",
       "backtest without Alpaca credentials returns the documented "
       "'set Alpaca credentials in Settings first' error",
       _GUIDE, '§"Step 2 — Connect your Alpaca account (paper)"', "doc"),
    _e("s2.save-profile", "s2-strategy-flow",
       "a valid preset-based profile saves via POST /api/profiles",
       _GUIDE, '§"Step 3 — Build a strategy profile"'),
    _e("s2.arm-strategy", "s2-strategy-flow",
       "arming a saved profile succeeds and it lists as armed",
       _GUIDE, '§"The 5 steps to start trading"', "doc"),
    _e("s2.dashboard-shows-armed", "s2-strategy-flow",
       "an armed strategy appears on the Dashboard grid (no 'No strategies "
       "armed' empty state)",
       _ROADMAP_SPEC, '§"Sub-project A"'),
    # S3 — watchlist round-trip
    _e("s3.watchlist-roundtrip", "s3-watchlist",
       "a symbol added to the watchlist appears in the Dashboard watchlist "
       "row and removal restores the original list",
       _ROADMAP_SPEC, '§"Sub-project A"'),
    # S4 — settings persistence
    _e("s4.settings-persist", "s4-settings",
       "PUT /api/portfolio/settings persists max_concurrent and serves it back",
       _C_SPEC, '§"Configuration"'),
    # S5 — brain inbox
    _e("s5.apply-approved-arm", "s5-brain-inbox",
       "applying an approved arm proposal arms the strategy",
       _C_SPEC, '§"Frontend"'),
    _e("s5.dismiss-leaves-others", "s5-brain-inbox",
       "dismissing a proposal marks it dismissed and leaves others pending",
       _C_SPEC, '§"Frontend"'),
    _e("s5.blocked-shows-reason", "s5-brain-inbox",
       "a blocked proposal card shows its guardrail reason",
       _C_SPEC, '§"Frontend"'),
    _e("s5.ui-fix-no-apply", "s5-brain-inbox",
       "non-executable proposals (ui_fix/doc_fix) show no Apply button",
       _D_SPEC, '§"New action type"'),
    # S6 — guide reconciliation (one key; per-affordance detail in the step)
    _e("s6.affordance-exists", "s6-guide",
       "every UI control the Guide names exists in the rendered DOM",
       _GUIDE, '§"The 5 steps to start trading"', "doc"),
]}


# (visible text, hash route, guide section) — S6 checks each renders in the DOM.
# Task 10 rewrites the Guide; keep this list in sync with it (that task updates
# the entries marked stale below).
GUIDE_AFFORDANCES: list[tuple[str, str, str]] = [
    ("Save profile",     "/#/strategy",  '§"Step 3 — Build a strategy profile"'),
    ("Set active",       "/#/strategy",  '§"Step 4 — Set the profile active"'),  # stale: removed in A — S6 must flag this until Task 10
    ("Save credentials", "/#/settings",  '§"Step 2 — Connect your Alpaca account (paper)"'),
    ("Start bot",        "/#/dashboard", '§"Step 5 — Start the bot"'),
    ("HALT",             "/#/dashboard", '§"Controls reference"'),
    ("Flatten",          "/#/dashboard", '§"Controls reference"'),
]
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_selftest_expectations.py -q`
Expected: 3 PASS. (If a spec filename assert fails, fix the path constant to the actual file under `docs/superpowers/specs/` — verify with `ls docs/superpowers/specs/`.)

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/selftest/expectations.py tests/test_selftest_expectations.py
git commit -m "feat(e): expectations catalog with doc refs + guide affordance list"
```

---

### Task 4: Ephemeral app harness

**Files:**
- Modify: `src/swingbot/webmain.py` (port from env)
- Create: `src/swingbot/selftest/ephemeral.py`
- Test: `tests/test_selftest_ephemeral.py`

- [ ] **Step 1: Make webmain's port configurable**

In `src/swingbot/webmain.py`, under the `DATA_DIR` line add:

```python
PORT = int(os.environ.get("SWINGBOT_PORT", "8000"))
```

and change the last two lines of `main()`:

```python
    print(f"[swingbot-web] http://{HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_selftest_ephemeral.py`:

```python
import json
import os

import pytest

from swingbot.selftest.ephemeral import EphemeralApp


class FakeProc:
    def __init__(self, pid=4242, alive=True):
        self.pid = pid
        self._alive = alive
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if self._alive else 1

    def terminate(self):
        self.terminated = True
        self._alive = False

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True
        self._alive = False


def _app(tmp_path, http_results, proc=None, **kw):
    """http_results: list of bools consumed per readiness poll."""
    calls = {"popen": [], "env": []}

    def popen_fn(cmd, env=None, **kwargs):
        calls["popen"].append(cmd)
        calls["env"].append(env)
        return proc or FakeProc()

    it = iter(http_results)

    def http_get(url, timeout=2.0):
        return next(it, False)

    app = EphemeralApp(port=8001, agent_dir=str(tmp_path / "agent"),
                       popen_fn=popen_fn, http_get=http_get,
                       startup_timeout_s=0.2, poll_interval_s=0.01, **kw)
    return app, calls


def test_start_sets_env_writes_token_and_pidfile(tmp_path):
    app, calls = _app(tmp_path, [False, True])
    app.start()
    try:
        env = calls["env"][0]
        assert env["SWINGBOT_PORT"] == "8001"
        assert env["SWINGBOT_HOST"] == "127.0.0.1"
        data_dir = env["SWINGBOT_DATA_DIR"]
        assert open(os.path.join(data_dir, "token")).read() == app.token
        pid_meta = json.load(open(os.path.join(str(tmp_path / "agent"), "ephemeral.pid")))
        assert pid_meta["pid"] == 4242 and pid_meta["port"] == 8001
        assert app.base_url == "http://127.0.0.1:8001"
    finally:
        app.stop()


def test_stop_terminates_removes_pidfile_and_data_dir(tmp_path):
    app, _ = _app(tmp_path, [True])
    app.start()
    data_dir = app.data_dir
    app.stop()
    assert not os.path.exists(os.path.join(str(tmp_path / "agent"), "ephemeral.pid"))
    assert not os.path.exists(data_dir)


def test_startup_timeout_raises_and_tears_down(tmp_path):
    proc = FakeProc()
    app, _ = _app(tmp_path, [False] * 100, proc=proc)
    with pytest.raises(RuntimeError):
        app.start()
    assert proc.terminated or proc.killed
    assert app.data_dir is None or not os.path.exists(app.data_dir)


def test_early_process_death_raises(tmp_path):
    proc = FakeProc(alive=False)
    app, _ = _app(tmp_path, [False] * 100, proc=proc)
    with pytest.raises(RuntimeError, match="exited"):
        app.start()


def test_stale_pidfile_is_killed_on_start(tmp_path):
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "ephemeral.pid").write_text(json.dumps({"pid": 99999, "port": 8001}))
    killed = []
    app, _ = _app(tmp_path, [True])
    app.kill_fn = lambda pid: killed.append(pid)
    app.start()
    try:
        assert killed == [99999]
    finally:
        app.stop()


def test_seed_proposals_writes_store_file(tmp_path):
    app, _ = _app(tmp_path, [True])
    app.start()
    try:
        app.seed_proposals([{"id": "x1", "action": "arm"}])
        rows = json.load(open(os.path.join(app.data_dir, "brain_proposals.json")))
        assert rows[0]["id"] == "x1"
    finally:
        app.stop()


def test_context_manager(tmp_path):
    app, _ = _app(tmp_path, [True])
    with app as a:
        assert a.base_url.endswith(":8001")
    assert not os.path.exists(os.path.join(str(tmp_path / "agent"), "ephemeral.pid"))
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_selftest_ephemeral.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 4: Create `src/swingbot/selftest/ephemeral.py`**

```python
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request


def _default_popen(cmd: list[str], env: dict, **kwargs):
    return subprocess.Popen(cmd, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _default_http_get(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 500
    except Exception:
        return False


def _default_kill(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


class EphemeralApp:
    """Throwaway swingbot web instance: own port, own SWINGBOT_DATA_DIR,
    torn down after use. The live container's state is never touched.

    A pidfile under agent_dir lets the next run kill a leaked instance.
    """

    def __init__(self, port: int = 8001, agent_dir: str = "",
                 python: str = sys.executable, popen_fn=None, http_get=None,
                 kill_fn=None, startup_timeout_s: float = 30.0,
                 poll_interval_s: float = 0.5):
        self.port = port
        self.agent_dir = agent_dir
        self.python = python
        self.popen_fn = popen_fn or _default_popen
        self.http_get = http_get or _default_http_get
        self.kill_fn = kill_fn or _default_kill
        self.startup_timeout_s = startup_timeout_s
        self.poll_interval_s = poll_interval_s
        self.token = "agent-ephemeral-token"
        self.data_dir: str | None = None
        self.proc = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def _pidfile(self) -> str:
        return os.path.join(self.agent_dir, "ephemeral.pid")

    def _kill_stale(self) -> None:
        if not self.agent_dir:
            return
        try:
            with open(self._pidfile) as f:
                meta = json.load(f)
            self.kill_fn(int(meta["pid"]))
            os.remove(self._pidfile)
        except (OSError, ValueError, KeyError):
            pass

    def start(self) -> None:
        self._kill_stale()
        self.data_dir = tempfile.mkdtemp(prefix="swingbot-agent-")
        # Pre-write the token so it is known (webmain reuses an existing file).
        with open(os.path.join(self.data_dir, "token"), "w") as f:
            f.write(self.token)
        env = {**os.environ,
               "SWINGBOT_DATA_DIR": self.data_dir,
               "SWINGBOT_HOST": "127.0.0.1",
               "SWINGBOT_PORT": str(self.port)}
        self.proc = self.popen_fn([self.python, "-m", "swingbot.webmain"], env=env)
        if self.agent_dir:
            os.makedirs(self.agent_dir, exist_ok=True)
            with open(self._pidfile, "w") as f:
                json.dump({"pid": self.proc.pid, "port": self.port}, f)
        deadline = time.monotonic() + self.startup_timeout_s
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                self.stop()
                raise RuntimeError(f"ephemeral app exited rc={self.proc.poll()}")
            if self.http_get(f"{self.base_url}/api/state"):
                return
            time.sleep(self.poll_interval_s)
        self.stop()
        raise RuntimeError(f"ephemeral app on :{self.port} not ready "
                           f"after {self.startup_timeout_s}s (port busy?)")

    def seed_proposals(self, proposals: list[dict]) -> None:
        """Write proposal dicts straight into the ephemeral brain inbox.
        ProposalStore re-reads the file per request, so no restart is needed."""
        assert self.data_dir, "seed_proposals before start()"
        with open(os.path.join(self.data_dir, "brain_proposals.json"), "w") as f:
            json.dump(proposals, f)

    def stop(self) -> None:
        if self.proc is not None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=10)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None
        if self.agent_dir:
            try:
                os.remove(self._pidfile)
            except OSError:
                pass
        if self.data_dir:
            shutil.rmtree(self.data_dir, ignore_errors=True)
            self.data_dir = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
        return False
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/test_selftest_ephemeral.py -q`
Expected: 7 PASS.

- [ ] **Step 6: Sanity-run the full suite (webmain change)**

Run: `.venv/bin/python -m pytest -q`
Expected: green (baseline + new tests, no regressions).

- [ ] **Step 7: Commit**

```bash
git add src/swingbot/webmain.py src/swingbot/selftest/ephemeral.py tests/test_selftest_ephemeral.py
git commit -m "feat(e): EphemeralApp harness on :8001 with throwaway DATA_DIR + stale-pid cleanup"
```

---

### Task 5: Sessions framework + S1 (tab navigation) + S6 (guide reconciliation)

**Files:**
- Create: `src/swingbot/selftest/sessions.py`
- Test: `tests/test_selftest_sessions.py`

Sessions follow the uiprobe injectable-page pattern: real runs pass Playwright
pages; unit tests pass fakes. The page surface used is only:
`page.on(event, fn)`, `page.goto(url, wait_until=...)`,
`page.wait_for_selector(sel, timeout=...)` (raises when absent),
`page.locator(sel).count()`, `page.screenshot(path=...)`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_selftest_sessions.py`:

```python
from swingbot.selftest.sessions import (
    EPHEMERAL_SESSIONS, LIVE_SESSIONS, GuideReconciliationSession,
    SessionContext, TabNavigationSession,
)


class FakeLocator:
    def __init__(self, n):
        self._n = n

    def count(self):
        return self._n


class FakePage:
    """present_selectors: selectors that exist; everything else is missing."""

    def __init__(self, present_selectors=None, fail_goto=False):
        self.present = set(present_selectors or [])
        self.fail_goto = fail_goto
        self.gotos = []

    def on(self, event, handler):
        pass

    def goto(self, url, **kw):
        self.gotos.append(url)
        if self.fail_goto:
            raise ConnectionRefusedError("refused")

    def wait_for_selector(self, sel, timeout=0):
        if sel not in self.present:
            raise TimeoutError(f"no {sel}")

    def locator(self, sel):
        return FakeLocator(1 if sel in self.present else 0)

    def screenshot(self, **kw):
        pass


_ALL_S1 = ["text=Watchlist", "text=Save profile", ".discover-controls",
           ".brain-title", "text=Alpaca credentials", ".guide"]


def _ctx():
    return SessionContext(base_url="http://x:8000", screenshot_dir="/tmp/shots")


def test_s1_all_tabs_render_ok():
    trace = TabNavigationSession().run(FakePage(_ALL_S1), _ctx())
    assert trace.session == "s1-tabs" and trace.ok
    assert len(trace.steps) == 6
    assert all(s.ok for s in trace.steps)


def test_s1_missing_element_fails_step_with_expectation_key():
    present = [s for s in _ALL_S1 if s != ".brain-title"]
    trace = TabNavigationSession().run(FakePage(present), _ctx())
    assert not trace.ok
    bad = [s for s in trace.steps if not s.ok]
    assert len(bad) == 1
    assert bad[0].expectation_key == "s1.tab-renders"
    assert "/#/brain" in bad[0].detail


def test_s1_goto_failure_is_failed_step_not_crash():
    trace = TabNavigationSession().run(FakePage(fail_goto=True), _ctx())
    assert not trace.ok and len(trace.steps) == 6


def test_s6_flags_missing_affordance():
    # Everything present except the stale "Set active" button.
    present = ["text=Save profile", "text=Save credentials", "text=Start bot",
               "text=HALT", "text=Flatten"]
    trace = GuideReconciliationSession().run(FakePage(present), _ctx())
    assert trace.session == "s6-guide" and not trace.ok
    bad = [s for s in trace.steps if not s.ok]
    assert len(bad) == 1
    assert "Set active" in bad[0].detail
    assert bad[0].expectation_key == "s6.affordance-exists"


def test_registries_partition_by_tier():
    assert [s.name for s in LIVE_SESSIONS] == ["s1-tabs", "s6-guide"]
    assert all(s.tier == "live" for s in LIVE_SESSIONS)
    assert all(s.tier == "ephemeral" for s in EPHEMERAL_SESSIONS)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_selftest_sessions.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Create `src/swingbot/selftest/sessions.py` (framework + S1 + S6)**

```python
from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass, field

from swingbot.selftest import SessionStep, SessionTrace
from swingbot.selftest.expectations import GUIDE_AFFORDANCES

_WAIT_MS = 8000


def _default_api(base_url: str, token: str, method: str, path: str,
                 body: dict | None = None) -> tuple[int, dict]:
    """Tiny JSON client for session API steps. Returns (status, payload)."""
    req = urllib.request.Request(
        base_url.rstrip("/") + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "X-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


@dataclass
class SessionContext:
    base_url: str
    token: str = ""
    screenshot_dir: str = ""
    api_fn: object = None          # (base_url, token, method, path, body) -> (status, json)
    seed_proposals: object = None  # callable(list[dict]) — wired to EphemeralApp

    def api(self, method: str, path: str, body: dict | None = None):
        fn = self.api_fn or _default_api
        return fn(self.base_url, self.token, method, path, body)


class SessionRecorder:
    def __init__(self, name: str):
        self.trace = SessionTrace(session=name, ok=True, started_at=time.time())

    def step(self, desc: str, action: str, ok: bool, detail: str = "",
             expectation_key: str = "", screenshot_path: str = "") -> bool:
        self.trace.steps.append(SessionStep(
            desc=desc, action=action, ok=ok, detail=detail,
            screenshot_path=screenshot_path, expectation_key=expectation_key))
        if not ok:
            self.trace.ok = False
        return ok

    def finish(self) -> SessionTrace:
        self.trace.duration_s = round(time.time() - self.trace.started_at, 2)
        return self.trace


def _goto(page, rec: SessionRecorder, ctx: SessionContext, route: str,
          expectation_key: str = "") -> bool:
    try:
        page.goto(f"{ctx.base_url.rstrip('/')}{route}", wait_until="networkidle")
        return rec.step(f"open {route}", "goto", True)
    except Exception as e:
        return rec.step(f"open {route}", "goto", False,
                        detail=f"{route}: navigation failed: {e}",
                        expectation_key=expectation_key)


def _shoot(page, ctx: SessionContext, name: str) -> str:
    if not ctx.screenshot_dir:
        return ""
    path = os.path.join(ctx.screenshot_dir, f"{name}.png")
    try:
        os.makedirs(ctx.screenshot_dir, exist_ok=True)
        page.screenshot(path=path, full_page=True)
        return path
    except Exception:
        return ""


def _wait(page, rec: SessionRecorder, ctx: SessionContext, route: str,
          selector: str, expectation_key: str, shot_name: str) -> bool:
    try:
        page.wait_for_selector(selector, timeout=_WAIT_MS)
        return rec.step(f"{route} shows {selector}", "assert", True)
    except Exception:
        return rec.step(f"{route} shows {selector}", "assert", False,
                        detail=f"{route}: expected element {selector!r} not found",
                        expectation_key=expectation_key,
                        screenshot_path=_shoot(page, ctx, shot_name))


# ---- S1: every tab renders its key element ----

_TAB_CHECKS = [
    ("/#/dashboard", "text=Watchlist"),          # PositionGrid header
    ("/#/strategy",  "text=Save profile"),
    ("/#/discover",  ".discover-controls"),
    ("/#/brain",     ".brain-title"),
    ("/#/settings",  "text=Alpaca credentials"),
    ("/#/guide",     ".guide"),
]


class TabNavigationSession:
    name = "s1-tabs"
    tier = "live"

    def run(self, page, ctx: SessionContext) -> SessionTrace:
        rec = SessionRecorder(self.name)
        for route, selector in _TAB_CHECKS:
            try:
                page.goto(f"{ctx.base_url.rstrip('/')}{route}",
                          wait_until="networkidle")
                page.wait_for_selector(selector, timeout=_WAIT_MS)
                rec.step(f"{route} renders {selector}", "goto", True)
            except Exception as e:
                rec.step(f"{route} renders {selector}", "goto", False,
                         detail=f"{route}: {selector!r} not rendered ({e})",
                         expectation_key="s1.tab-renders",
                         screenshot_path=_shoot(page, ctx, f"s1-{route.split('/')[-1]}"))
        return rec.finish()


# ---- S6: every affordance the Guide names exists in the DOM ----

class GuideReconciliationSession:
    name = "s6-guide"
    tier = "live"

    def run(self, page, ctx: SessionContext) -> SessionTrace:
        rec = SessionRecorder(self.name)
        for text, route, section in GUIDE_AFFORDANCES:
            try:
                page.goto(f"{ctx.base_url.rstrip('/')}{route}",
                          wait_until="networkidle")
                found = page.locator(f"text={text}").count() > 0
            except Exception:
                found = False
            rec.step(f"Guide names {text!r} on {route}", "assert", found,
                     detail=("" if found else
                             f"Guide {section} names {text!r} but {route} has no "
                             f"such element"),
                     expectation_key="" if found else "s6.affordance-exists",
                     screenshot_path="" if found else _shoot(page, ctx, "s6-" + text.lower().replace(" ", "-")))
        return rec.finish()


LIVE_SESSIONS = [TabNavigationSession(), GuideReconciliationSession()]
EPHEMERAL_SESSIONS: list = []   # filled in Task 6
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_selftest_sessions.py -q`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/selftest/sessions.py tests/test_selftest_sessions.py
git commit -m "feat(e): session framework + S1 tab navigation + S6 guide reconciliation"
```

---

### Task 6: Mutating sessions S2–S5 (ephemeral tier)

**Files:**
- Modify: `src/swingbot/selftest/sessions.py`
- Test: `tests/test_selftest_sessions.py` (extend)

- [ ] **Step 1: Write failing tests (fake API + fake page)**

Append to `tests/test_selftest_sessions.py`:

```python
from swingbot.selftest.sessions import (
    BrainInboxSession, GuidedStrategyFlowSession, SettingsPersistenceSession,
    WatchlistRoundTripSession,
)


class FakeApi:
    """Routes (method, path) -> (status, payload); records every call."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, base_url, token, method, path, body=None):
        self.calls.append((method, path, body))
        for (m, prefix), resp in self.routes.items():
            if m == method and path.startswith(prefix):
                return resp(path, body) if callable(resp) else resp
        return 404, {}


_PRESETS = [{"key": "dip", "name": "Dip buyer", "profile": {
    "symbol": "BTC/USD", "timeframe": "15m",
    "signals": {"oversold": {"weight": 1.0}}}}]


def _s2_routes(backtest=(400, {"detail": "set Alpaca credentials in Settings first"}),
               armed=True):
    return {
        ("GET", "/api/presets"): (200, _PRESETS),
        ("POST", "/api/strategy/backtest"): backtest,
        ("POST", "/api/profiles"): (200, {"ok": True}),
        ("POST", "/api/strategies/arm"): (200, {"ok": True}),
        ("GET", "/api/strategies"): (200, [{"name": "agent-s2-btc", "armed": armed}]),
    }


def test_s2_happy_path():
    api = FakeApi(_s2_routes())
    page = FakePage(["text=BTC/USD"])
    ctx = SessionContext(base_url="http://x:8001", token="t", api_fn=api)
    trace = GuidedStrategyFlowSession().run(page, ctx)
    assert trace.session == "s2-strategy-flow" and trace.ok
    assert ("POST", "/api/strategies/arm", {"name": "agent-s2-btc"}) in api.calls


def test_s2_undocumented_backtest_error_fails_expectation():
    api = FakeApi(_s2_routes(backtest=(500, {"detail": "boom"})))
    page = FakePage(["text=BTC/USD"])
    trace = GuidedStrategyFlowSession().run(
        page, SessionContext(base_url="http://x:8001", token="t", api_fn=api))
    bad = [s for s in trace.steps if not s.ok]
    assert any(s.expectation_key == "s2.backtest-needs-creds" for s in bad)


def test_s2_dashboard_missing_strategy_fails_expectation():
    api = FakeApi(_s2_routes())
    page = FakePage([])      # dashboard never shows the armed symbol
    trace = GuidedStrategyFlowSession().run(
        page, SessionContext(base_url="http://x:8001", token="t", api_fn=api))
    bad = [s for s in trace.steps if not s.ok]
    assert any(s.expectation_key == "s2.dashboard-shows-armed" for s in bad)


def test_s3_watchlist_roundtrip():
    lists = {"symbols": ["BTC/USD"]}

    def put(path, body):
        lists["symbols"] = body["symbols"]
        return 200, dict(lists)

    api = FakeApi({("GET", "/api/watchlist"): lambda p, b: (200, dict(lists)),
                   ("PUT", "/api/watchlist"): put})
    page = FakePage(["text=ETH/USD"])
    trace = WatchlistRoundTripSession().run(
        page, SessionContext(base_url="http://x:8001", token="t", api_fn=api))
    assert trace.ok
    assert lists["symbols"] == ["BTC/USD"]          # restored


def test_s4_settings_persist_and_restore():
    settings = {"max_concurrent": 5}

    def put(path, body):
        settings.update(body)
        return 200, dict(settings)

    api = FakeApi({("GET", "/api/portfolio/settings"): lambda p, b: (200, dict(settings)),
                   ("PUT", "/api/portfolio/settings"): put})
    trace = SettingsPersistenceSession().run(
        FakePage(), SessionContext(base_url="http://x:8001", token="t", api_fn=api))
    assert trace.ok and settings["max_concurrent"] == 5   # restored


def test_s5_brain_inbox_flow():
    seeded = []
    proposals = []

    def seed(rows):
        seeded.extend(rows)
        proposals.clear()
        proposals.extend(rows)

    def apply_(path, body):
        pid = path.split("/")[-2]
        for p in proposals:
            if p["id"] == pid:
                p["status"] = "applied"
        return 200, {"ok": True}

    def dismiss(path, body):
        pid = path.split("/")[-2]
        for p in proposals:
            if p["id"] == pid:
                p["status"] = "dismissed"
        return 200, {"ok": True}

    api = FakeApi({
        ("GET", "/api/presets"): (200, _PRESETS),
        ("GET", "/api/brain/proposals"): lambda p, b: (200, [dict(x) for x in proposals]),
        ("POST", "/api/brain/proposals/agent-s5-arm/apply"): apply_,
        ("POST", "/api/brain/proposals/agent-s5-tune/dismiss"): dismiss,
        ("GET", "/api/strategies"): (200, [{"name": "disc-btcusd-dip", "armed": True}]),
    })
    # Brain page shows the blocked reason and zero Apply buttons.
    page = FakePage(["text=guardrail-test-reason"])
    ctx = SessionContext(base_url="http://x:8001", token="t", api_fn=api,
                         seed_proposals=seed)
    trace = BrainInboxSession().run(page, ctx)
    assert trace.ok, [s.detail for s in trace.steps if not s.ok]
    assert {p["id"] for p in seeded} == {"agent-s5-arm", "agent-s5-tune",
                                         "agent-s5-uifix"}
    assert [s for s in trace.steps if s.expectation_key] == []


def test_s5_apply_button_present_for_ui_fix_is_drift():
    api = FakeApi({
        ("GET", "/api/presets"): (200, _PRESETS),
        ("GET", "/api/brain/proposals"): (200, []),
        ("POST", "/api/brain/proposals/agent-s5-arm/apply"): (200, {"ok": True}),
        ("POST", "/api/brain/proposals/agent-s5-tune/dismiss"): (200, {"ok": True}),
        ("GET", "/api/strategies"): (200, [{"name": "disc-btcusd-dip", "armed": True}]),
    })
    page = FakePage(["text=guardrail-test-reason", "button:has-text(\"Apply\")"])
    ctx = SessionContext(base_url="http://x:8001", token="t", api_fn=api,
                         seed_proposals=lambda rows: None)
    trace = BrainInboxSession().run(page, ctx)
    bad = [s for s in trace.steps if not s.ok]
    assert any(s.expectation_key == "s5.ui-fix-no-apply" for s in bad)


def test_ephemeral_registry_complete():
    assert [s.name for s in EPHEMERAL_SESSIONS] == [
        "s2-strategy-flow", "s3-watchlist", "s4-settings", "s5-brain-inbox"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_selftest_sessions.py -q`
Expected: new tests FAIL with `ImportError` (S2–S5 classes missing); Task 5 tests still PASS.

- [ ] **Step 3: Implement S2–S5 in `src/swingbot/selftest/sessions.py`**

Add above the `LIVE_SESSIONS` line; then change `EPHEMERAL_SESSIONS`:

```python
def _api_step(rec: SessionRecorder, ctx: SessionContext, desc: str, method: str,
              path: str, body=None, ok_when=lambda st, js: st == 200,
              expectation_key: str = "") -> tuple[bool, dict]:
    try:
        st, js = ctx.api(method, path, body)
    except Exception as e:
        return rec.step(desc, "api", False, detail=f"{method} {path}: {e}",
                        expectation_key=expectation_key), {}
    ok = bool(ok_when(st, js))
    return rec.step(desc, "api", ok,
                    detail="" if ok else f"{method} {path} -> {st} {str(js)[:200]}",
                    expectation_key="" if ok else expectation_key), js


# ---- S2: Guide's "5 steps" — build, (gated) backtest, arm, see it trading ----

class GuidedStrategyFlowSession:
    name = "s2-strategy-flow"
    tier = "ephemeral"
    PROFILE_NAME = "agent-s2-btc"

    def run(self, page, ctx: SessionContext) -> SessionTrace:
        rec = SessionRecorder(self.name)
        ok, presets = _api_step(rec, ctx, "list presets", "GET", "/api/presets")
        if not ok or not presets:
            return rec.finish()
        profile = dict(presets[0]["profile"])
        profile["symbol"] = "BTC/USD"

        # Ephemeral app has no Alpaca creds: the Guide documents the exact
        # error this must produce (Guide §Step 2).
        _api_step(rec, ctx, "backtest without creds gives documented error",
                  "POST", "/api/strategy/backtest", {"profile": profile},
                  ok_when=lambda st, js: st == 400 and
                  "credentials" in str(js.get("detail", "")).lower(),
                  expectation_key="s2.backtest-needs-creds")

        _api_step(rec, ctx, "save preset-based profile", "POST", "/api/profiles",
                  {"name": self.PROFILE_NAME, "profile": profile},
                  expectation_key="s2.save-profile")
        _api_step(rec, ctx, "arm the profile", "POST", "/api/strategies/arm",
                  {"name": self.PROFILE_NAME},
                  expectation_key="s2.arm-strategy")
        _api_step(rec, ctx, "strategy lists as armed", "GET", "/api/strategies",
                  ok_when=lambda st, js: st == 200 and any(
                      r.get("name") == self.PROFILE_NAME and r.get("armed")
                      for r in js),
                  expectation_key="s2.arm-strategy")

        if _goto(page, rec, ctx, "/#/dashboard", "s2.dashboard-shows-armed"):
            _wait(page, rec, ctx, "/#/dashboard", "text=BTC/USD",
                  "s2.dashboard-shows-armed", "s2-dashboard")
        return rec.finish()


# ---- S3: watchlist round-trip ----

class WatchlistRoundTripSession:
    name = "s3-watchlist"
    tier = "ephemeral"

    def run(self, page, ctx: SessionContext) -> SessionTrace:
        rec = SessionRecorder(self.name)
        ok, before = _api_step(rec, ctx, "read watchlist", "GET", "/api/watchlist",
                               expectation_key="s3.watchlist-roundtrip")
        if not ok:
            return rec.finish()
        base = list(before.get("symbols") or [])
        _api_step(rec, ctx, "add ETH/USD", "PUT", "/api/watchlist",
                  {"symbols": base + ["ETH/USD"]},
                  ok_when=lambda st, js: st == 200 and "ETH/USD" in js.get("symbols", []),
                  expectation_key="s3.watchlist-roundtrip")
        if _goto(page, rec, ctx, "/#/dashboard", "s3.watchlist-roundtrip"):
            _wait(page, rec, ctx, "/#/dashboard", "text=ETH/USD",
                  "s3.watchlist-roundtrip", "s3-watchlist")
        _api_step(rec, ctx, "restore watchlist", "PUT", "/api/watchlist",
                  {"symbols": base},
                  ok_when=lambda st, js: st == 200 and js.get("symbols") == base,
                  expectation_key="s3.watchlist-roundtrip")
        return rec.finish()


# ---- S4: portfolio settings persistence ----

class SettingsPersistenceSession:
    name = "s4-settings"
    tier = "ephemeral"

    def run(self, page, ctx: SessionContext) -> SessionTrace:
        rec = SessionRecorder(self.name)
        ok, before = _api_step(rec, ctx, "read settings", "GET",
                               "/api/portfolio/settings",
                               expectation_key="s4.settings-persist")
        if not ok:
            return rec.finish()
        old = before.get("max_concurrent", 5)
        new = old + 2
        _api_step(rec, ctx, f"set max_concurrent={new}", "PUT",
                  "/api/portfolio/settings", {"max_concurrent": new},
                  ok_when=lambda st, js: st == 200 and js.get("max_concurrent") == new,
                  expectation_key="s4.settings-persist")
        _api_step(rec, ctx, "re-read shows persisted value", "GET",
                  "/api/portfolio/settings",
                  ok_when=lambda st, js: st == 200 and js.get("max_concurrent") == new,
                  expectation_key="s4.settings-persist")
        _api_step(rec, ctx, "restore", "PUT", "/api/portfolio/settings",
                  {"max_concurrent": old},
                  ok_when=lambda st, js: st == 200 and js.get("max_concurrent") == old,
                  expectation_key="s4.settings-persist")
        return rec.finish()


# ---- S5: brain inbox flow ----

def _seed_rows(archetype_key: str) -> list[dict]:
    base = {"created_at": 1, "rationale": "agent seed", "confidence": 0.9,
            "status": "pending", "applied_at": None, "source": "usage-agent"}
    return [
        {**base, "id": "agent-s5-arm", "action": "arm",
         "target": {"symbol": "BTC/USD", "archetype": archetype_key},
         "guardrail_status": "approved", "guardrail_reason": ""},
        {**base, "id": "agent-s5-tune", "action": "tune",
         "target": {"symbol": "BTC/USD", "archetype": archetype_key,
                    "params": {"entry_threshold": 0.5}},
         "guardrail_status": "blocked",
         "guardrail_reason": "guardrail-test-reason"},
        {**base, "id": "agent-s5-uifix", "action": "ui_fix",
         "target": {"route": "/#/dashboard", "issue": "agent seed"},
         "guardrail_status": "approved", "guardrail_reason": ""},
    ]


class BrainInboxSession:
    name = "s5-brain-inbox"
    tier = "ephemeral"

    def run(self, page, ctx: SessionContext) -> SessionTrace:
        rec = SessionRecorder(self.name)
        ok, presets = _api_step(rec, ctx, "list presets", "GET", "/api/presets")
        if not ok or not presets:
            return rec.finish()
        arch = presets[0]["key"]

        if ctx.seed_proposals is None:
            rec.step("seed proposals", "api", False,
                     detail="no seed_proposals hook on context")
            return rec.finish()
        ctx.seed_proposals(_seed_rows(arch))
        rec.step("seed 3 proposals into inbox", "api", True)

        _api_step(rec, ctx, "inbox shows seeded proposals", "GET",
                  "/api/brain/proposals",
                  ok_when=lambda st, js: st == 200 and
                  {"agent-s5-arm", "agent-s5-tune", "agent-s5-uifix"} <=
                  {p.get("id") for p in js},
                  expectation_key="s5.apply-approved-arm")
        _api_step(rec, ctx, "apply approved arm", "POST",
                  "/api/brain/proposals/agent-s5-arm/apply",
                  ok_when=lambda st, js: st == 200 and js.get("ok"),
                  expectation_key="s5.apply-approved-arm")
        _api_step(rec, ctx, "applied arm armed the strategy", "GET",
                  "/api/strategies",
                  ok_when=lambda st, js: st == 200 and any(
                      r.get("name", "").startswith("disc-btcusd") and r.get("armed")
                      for r in js),
                  expectation_key="s5.apply-approved-arm")
        _api_step(rec, ctx, "dismiss blocked tune", "POST",
                  "/api/brain/proposals/agent-s5-tune/dismiss",
                  ok_when=lambda st, js: st == 200 and js.get("ok"),
                  expectation_key="s5.dismiss-leaves-others")
        _api_step(rec, ctx, "ui_fix still pending after dismiss", "GET",
                  "/api/brain/proposals",
                  ok_when=lambda st, js: st == 200 and any(
                      p.get("id") == "agent-s5-uifix" and p.get("status") == "pending"
                      for p in js),
                  expectation_key="s5.dismiss-leaves-others")

        if _goto(page, rec, ctx, "/#/brain", "s5.blocked-shows-reason"):
            _wait(page, rec, ctx, "/#/brain", "text=guardrail-test-reason",
                  "s5.blocked-shows-reason", "s5-brain")
            apply_buttons = 0
            try:
                apply_buttons = page.locator('button:has-text("Apply")').count()
            except Exception:
                pass
            rec.step("no Apply button for non-executable proposals", "assert",
                     apply_buttons == 0,
                     detail="" if apply_buttons == 0 else
                     f"{apply_buttons} Apply button(s) rendered for "
                     f"ui_fix/blocked proposals",
                     expectation_key="" if apply_buttons == 0 else "s5.ui-fix-no-apply",
                     screenshot_path="" if apply_buttons == 0 else _shoot(page, ctx, "s5-apply-dead-end"))
        return rec.finish()
```

and replace the registry line:

```python
EPHEMERAL_SESSIONS = [GuidedStrategyFlowSession(), WatchlistRoundTripSession(),
                      SettingsPersistenceSession(), BrainInboxSession()]
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_selftest_sessions.py -q`
Expected: all PASS (14 tests).

- [ ] **Step 5: Ruff + commit**

Run: `.venv/bin/python -m ruff check src/swingbot/selftest/sessions.py tests/test_selftest_sessions.py` — fix anything it flags.

```bash
git add src/swingbot/selftest/sessions.py tests/test_selftest_sessions.py
git commit -m "feat(e): mutating sessions S2-S5 against the ephemeral instance"
```

---

### Task 7: `doc_fix` action, drift reconciliation, Apply dead-end + guardrail honesty fixes

**Files:**
- Modify: `src/swingbot/decision/guardrails.py:69-72`
- Modify: `src/swingbot/decision/proposals.py` (`supersede_pending` carve-out)
- Modify: `src/swingbot/decision/brain.py` (supersede call + `_dispatch` rejection)
- Modify: `src/swingbot/selftest/llm.py`
- Create: `src/swingbot/selftest/drift.py`
- Modify: `frontend/src/pages/Brain.jsx:136-143`
- Test: `tests/test_decision_guardrails.py`, `tests/test_decision_brain.py`, `tests/test_selftest_llm.py` (extend), `tests/test_selftest_drift.py` (create)

- [ ] **Step 1: Failing tests — guardrails + brain**

Append to `tests/test_decision_guardrails.py`:

```python
from swingbot.decision.guardrails import NON_EXECUTABLE_ACTIONS


def test_doc_fix_and_ui_fix_are_non_executable_and_approved():
    assert NON_EXECUTABLE_ACTIONS == {"ui_fix", "doc_fix"}
    for action in NON_EXECUTABLE_ACTIONS:
        p = make_proposal(action, {"doc": "x"}, "r", 0.9)
        assert evaluate(p, {}, [], backtest_ok=lambda *a: True) == ("approved", "")
```

(reuse the file's existing imports of `evaluate`/`make_proposal`; add them if its
helpers differ — match local conventions.)

Append to `tests/test_decision_brain.py` — it already has `_brain(tmp_path,
ollama, profiles=…)`, `FakeOllama`, `FakeProfiles`, and imports `OllamaResult`;
add `from swingbot.decision.proposals import make_proposal` to its imports:

```python
def test_apply_non_executable_action_returns_clear_error(tmp_path):
    brain = _brain(tmp_path, FakeOllama(OllamaResult(ok=True, data={})))
    p = make_proposal("ui_fix", {"route": "/#/x", "issue": "y"}, "r", 0.9)
    p.guardrail_status = "approved"
    brain.proposals.add_many([p])
    res = brain.apply(p.id)
    assert res["ok"] is False
    assert "recommend-only" in res["error"]
    assert brain.proposals.get(p.id).status == "pending"   # not marked applied


def test_recommend_supersede_keeps_usage_agent_findings_pending(tmp_path):
    data = {"proposals": [{"action": "arm",
            "target": {"symbol": "BTC/USD", "archetype": "balanced"},
            "rationale": "good", "confidence": 0.9}]}
    brain = _brain(tmp_path, FakeOllama(OllamaResult(ok=True, data=data)))
    finding = make_proposal("ui_fix", {"route": "/#/x", "issue": "y"}, "drift", 0.9)
    finding.source = "usage-agent"
    finding.guardrail_status = "approved"
    brain.proposals.add_many([finding])
    brain.recommend()
    by_action = {p.action: p for p in brain.proposals.all()}
    assert by_action["ui_fix"].status == "pending"   # finding survives recommend
    assert by_action["arm"].status == "pending"      # fresh batch stored
```

Why: `recommend()` supersedes all pending proposals before storing the fresh
batch (`brain.py:66`) — without a carve-out, every brain run would silently
clear pending usage-agent drift findings off the Health tab. Note the live
brain can never *produce* `ui_fix`/`doc_fix` itself (`prompt.py` `VALID_ACTIONS`
drops them at parse), so autonomous mode cannot auto-apply findings — the
`_dispatch` rejection below is defense-in-depth for manual/API apply calls.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_decision_guardrails.py tests/test_decision_brain.py -q`
Expected: new tests FAIL (`ImportError: NON_EXECUTABLE_ACTIONS`; `_dispatch` raises generic `unknown action 'ui_fix'`).

- [ ] **Step 3: Implement guardrails + brain changes**

`src/swingbot/decision/guardrails.py` — add near the top (after `SETTINGS_BOUNDS`):

```python
# Findings-style proposals: always recommend-only, never auto-applied.
NON_EXECUTABLE_ACTIONS = {"ui_fix", "doc_fix"}
```

and replace the `ui_fix` branch at the bottom of `evaluate`:

```python
    if p.action in NON_EXECUTABLE_ACTIONS:
        return _OPEN   # recommend-only; apply is rejected at dispatch
```

`src/swingbot/decision/proposals.py` — give `supersede_pending` a carve-out:

```python
    def supersede_pending(self, keep_actions: frozenset[str] = frozenset()) -> None:
        rows = self.all()
        for p in rows:
            if p.status == "pending" and p.action not in keep_actions:
                p.status = "superseded"
        _atomic_write(self.path, [asdict(p) for p in rows])
```

`src/swingbot/decision/brain.py` — in `recommend()`, change the supersede call:

```python
        self.proposals.supersede_pending(keep_actions=frozenset(gr.NON_EXECUTABLE_ACTIONS))
```

and in `_dispatch`, before the final `else`:

```python
        elif p.action in gr.NON_EXECUTABLE_ACTIONS:
            raise ValueError(
                f"{p.action} proposals are recommend-only: make the change "
                f"manually, then dismiss the proposal")
```

- [ ] **Step 4: Run brain/guardrail tests**

Run: `.venv/bin/python -m pytest tests/test_decision_guardrails.py tests/test_decision_brain.py -q`
Expected: PASS.

- [ ] **Step 5: Failing tests — drift reconciliation**

Create `tests/test_selftest_drift.py`:

```python
from swingbot.selftest import SessionStep, SessionTrace
from swingbot.selftest.drift import findings_to_proposals, reconcile


def _trace(steps):
    return SessionTrace(session="s6-guide", ok=all(s.ok for s in steps),
                        steps=steps)


def _fail(key, detail="observed mismatch", desc="check"):
    return SessionStep(desc=desc, action="assert", ok=False, detail=detail,
                       expectation_key=key, screenshot_path="/shots/x.png")


def test_passing_traces_produce_no_findings():
    t = _trace([SessionStep(desc="ok", action="assert", ok=True)])
    assert reconcile([t]) == []


def test_failed_step_with_doc_biased_expectation_is_drift():
    f = reconcile([_trace([_fail("s6.affordance-exists",
                                 'Guide §"x" names \'Set active\' but missing')])])
    assert len(f) == 1
    d = f[0]
    assert d.kind == "drift" and d.session == "s6-guide"
    assert d.doc_ref.startswith("frontend/src/guide.md")
    assert d.observed.startswith("Guide")
    assert d.screenshot_path == "/shots/x.png"


def test_failed_step_with_ui_biased_expectation_is_drift_too():
    f = reconcile([_trace([_fail("s1.tab-renders")])])
    assert f[0].kind == "drift"


def test_failed_step_without_expectation_key_is_bug():
    f = reconcile([_trace([_fail("", detail="browser crashed")])])
    assert f[0].kind == "bug" and f[0].doc_ref == ""


def test_findings_to_proposals_maps_bias_and_stamps():
    findings = reconcile([_trace([
        _fail("s6.affordance-exists", "guide says X"),     # doc bias
        _fail("s1.tab-renders", "brain tab blank"),        # ui bias
        _fail("", "crash"),                                # bug -> ui_fix
    ])])
    props = findings_to_proposals(findings)
    assert [p.action for p in props] == ["doc_fix", "ui_fix", "ui_fix"]
    for p in props:
        assert p.source == "usage-agent"
        assert p.guardrail_status == "approved"
        assert {"expected", "observed", "doc", "section", "suggestion"} <= set(p.target)


def test_same_finding_twice_dedupes_by_id():
    f = reconcile([_trace([_fail("s6.affordance-exists", "guide says X")])])
    a = findings_to_proposals(f)[0]
    b = findings_to_proposals(f)[0]
    assert a.id == b.id
```

Run: `.venv/bin/python -m pytest tests/test_selftest_drift.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 6: Create `src/swingbot/selftest/drift.py`**

```python
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
```

Run: `.venv/bin/python -m pytest tests/test_selftest_drift.py -q` → PASS.

- [ ] **Step 7: Honest guardrail stamping in `selftest/llm.py` (+ tests)**

In `tests/test_selftest_llm.py`, if any existing test asserts `tune` or
`portfolio_settings` proposals get `guardrail_status == "approved"`, change
that expectation to `"pending"`; then append (the file already has `_summary`,
`_client`, `_store`, `_notifier` helpers):

```python
def test_doc_fix_allowed_and_executable_actions_deferred():
    data = {"proposals": [
        {"action": "doc_fix",
         "target": {"doc": "frontend/src/guide.md", "section": "§x",
                    "expected": "e", "observed": "o", "suggestion": "s"},
         "rationale": "stale doc", "confidence": 0.8},
        {"action": "tune",
         "target": {"symbol": "BTC/USD", "archetype": "balanced",
                    "params": {"entry_threshold": 0.5}},
         "rationale": "tighten", "confidence": 0.7},
    ]}
    proposals = propose_from_health(_summary(), _client(data), _store(), _notifier())
    by_action = {p.action: p for p in proposals}
    assert by_action["doc_fix"].guardrail_status == "approved"
    assert by_action["tune"].guardrail_status == "pending"
    assert "deferred" in by_action["tune"].guardrail_reason
```

Then in `src/swingbot/selftest/llm.py`:

```python
from swingbot.decision.guardrails import NON_EXECUTABLE_ACTIONS

_ALLOWED_ACTIONS = {"tune", "ui_fix", "doc_fix", "portfolio_settings"}
```

(drop the now-unused `evaluate` import) and replace the stamping block:

```python
        if action in NON_EXECUTABLE_ACTIONS:
            p.guardrail_status, p.guardrail_reason = "approved", ""
        else:
            # No live portfolio/backtest context here — an "approved" stamp
            # would be a lie (audit finding #4). The live brain re-evaluates.
            p.guardrail_status = "pending"
            p.guardrail_reason = ("deferred: needs live portfolio context — "
                                  "run Recommend on the Brain page to evaluate")
```

Run: `.venv/bin/python -m pytest tests/test_selftest_llm.py -q` → PASS.

- [ ] **Step 8: Hide Apply for non-executable actions in Brain.jsx**

In `frontend/src/pages/Brain.jsx`, add at module level (under `STATUS_COLOR`):

```jsx
const NON_EXECUTABLE = ['ui_fix', 'doc_fix']
```

and change the Apply-button condition inside the proposal card:

```jsx
                {p.guardrail_status === 'approved' && !NON_EXECUTABLE.includes(p.action) && (
                  <button className="act" onClick={async () => { await api.brainApply(p.id); refresh() }}>Apply</button>
                )}
```

Run: `cd frontend && npm run build` → succeeds.

- [ ] **Step 9: Full suite + commit**

Run: `.venv/bin/python -m pytest -q` and `.venv/bin/python -m ruff check .`
Expected: green.

```bash
git add src/swingbot/decision/guardrails.py src/swingbot/decision/proposals.py \
        src/swingbot/decision/brain.py \
        src/swingbot/selftest/llm.py src/swingbot/selftest/drift.py \
        frontend/src/pages/Brain.jsx \
        tests/test_decision_guardrails.py tests/test_decision_brain.py \
        tests/test_selftest_llm.py tests/test_selftest_drift.py
git commit -m "feat(e): doc_fix action + drift reconciliation; fix ui_fix Apply dead-end and misleading selftest guardrail stamps"
```

---

### Task 8: Agent endpoints + Health tab

**Files:**
- Modify: `src/swingbot/web.py` (new `agent_dir` param + 3 endpoints)
- Modify: `src/swingbot/webmain.py` (pass `agent_dir`)
- Modify: `frontend/src/api.js`, `frontend/src/App.jsx`
- Create: `frontend/src/pages/Health.jsx`
- Modify: `src/swingbot/selftest/uiprobe.py` (`/#/health` route)
- Test: `tests/test_web_agent.py` (create), `tests/test_selftest_uiprobe.py` (route list)

- [ ] **Step 1: Write failing endpoint tests**

Create `tests/test_web_agent.py` (FakeController copied from `tests/test_web_read.py`):

```python
import os

from fastapi.testclient import TestClient

from swingbot.selftest.agentstore import AgentRunStore
from swingbot.web import create_app


class FakeController:
    def status(self): return {"portfolio": {"mode": "paper"}, "strategies": []}
    def journal(self, strategy=None): return []
    def metrics(self, strategy=None): return {}


def _client(tmp_path, seed_runs=True):
    agent_dir = str(tmp_path / "agent")
    store = AgentRunStore(agent_dir)
    if seed_runs:
        store.add({"ts": 1.0, "green": True, "checks": [], "route_findings": [],
                   "traces": [{"session": "s1-tabs", "ok": True, "steps": []}],
                   "drift": [], "proposal_ids": []})
        store.add({"ts": 2.0, "green": True, "checks": [], "route_findings": [],
                   "traces": [{"session": "s1-tabs", "ok": False, "steps": []}],
                   "drift": [{"session": "s1-tabs", "kind": "drift"}],
                   "proposal_ids": ["abc"]})
        os.makedirs(store.screenshot_dir, exist_ok=True)
        with open(os.path.join(store.screenshot_dir, "s1.png"), "wb") as f:
            f.write(b"\x89PNG fake")
    app = create_app(controller=FakeController(), profiles=None, creds=None,
                     token="tok", agent_dir=agent_dir)
    return TestClient(app)


def test_runs_returns_summaries_newest_last(tmp_path):
    r = _client(tmp_path).get("/api/agent/runs")
    assert r.status_code == 200
    runs = r.json()
    assert len(runs) == 2
    assert runs[-1]["drift_count"] == 1
    assert runs[-1]["sessions"] == [{"session": "s1-tabs", "ok": False}]
    assert "traces" not in runs[-1]


def test_latest_returns_full_run(tmp_path):
    r = _client(tmp_path).get("/api/agent/runs/latest")
    assert r.status_code == 200
    assert r.json()["proposal_ids"] == ["abc"]


def test_latest_empty_when_no_runs(tmp_path):
    r = _client(tmp_path, seed_runs=False).get("/api/agent/runs/latest")
    assert r.status_code == 200 and r.json() == {}


def test_artifact_served(tmp_path):
    r = _client(tmp_path).get("/api/agent/artifacts/s1.png")
    assert r.status_code == 200
    assert r.content.startswith(b"\x89PNG")


def test_artifact_traversal_rejected(tmp_path):
    c = _client(tmp_path)
    assert c.get("/api/agent/artifacts/..%2Fruns.json").status_code == 404
    assert c.get("/api/agent/artifacts/nope.png").status_code == 404


def test_endpoints_404_or_empty_without_agent_dir(tmp_path):
    app = create_app(controller=FakeController(), profiles=None, creds=None,
                     token="tok")
    c = TestClient(app)
    assert c.get("/api/agent/runs").json() == []
    assert c.get("/api/agent/runs/latest").json() == {}
    assert c.get("/api/agent/artifacts/x.png").status_code == 404
```

Run: `.venv/bin/python -m pytest tests/test_web_agent.py -q`
Expected: FAIL — `create_app() got an unexpected keyword argument 'agent_dir'`.

- [ ] **Step 2: Implement the endpoints**

In `src/swingbot/web.py`:
- change the signature: `def create_app(controller, profiles, creds, token: str, store=None, market=None, backfiller=None, discovery=None, discovery_cache_path=None, brain=None, agent_dir=None) -> FastAPI:`
- add `from fastapi.responses import FileResponse` to the imports
- add before the `# ---- archive` section:

```python
    # ---- usage agent (read-only) ----
    def _agent_store():
        from swingbot.selftest.agentstore import AgentRunStore
        return AgentRunStore(agent_dir) if agent_dir else None

    @app.get("/api/agent/runs")
    def agent_runs():
        s = _agent_store()
        if s is None:
            return []
        return [{"ts": r.get("ts"), "green": r.get("green"),
                 "duration_s": r.get("duration_s"),
                 "sessions": [{"session": t.get("session"), "ok": t.get("ok")}
                              for t in r.get("traces", [])],
                 "drift_count": len(r.get("drift", []))}
                for r in s.all()]

    @app.get("/api/agent/runs/latest")
    def agent_latest():
        s = _agent_store()
        return (s.latest() if s else None) or {}

    @app.get("/api/agent/artifacts/{name}")
    def agent_artifact(name: str):
        s = _agent_store()
        if s is None:
            raise HTTPException(status_code=404, detail="agent not configured")
        shots = os.path.realpath(s.screenshot_dir)
        path = os.path.realpath(os.path.join(shots, name))
        if not path.startswith(shots + os.sep) or not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="no such artifact")
        return FileResponse(path)
```

In `src/swingbot/webmain.py`, add `agent_dir=os.path.join(DATA_DIR, "agent")` to
the `create_app(...)` call.

Run: `.venv/bin/python -m pytest tests/test_web_agent.py -q` → 6 PASS.

- [ ] **Step 3: Frontend — api client + Health page + tab + probe route**

`frontend/src/api.js` — append inside `api`:

```js
  // --- usage agent ---
  agentRuns: () => req('GET', '/api/agent/runs'),
  agentLatest: () => req('GET', '/api/agent/runs/latest'),
```

Create `frontend/src/pages/Health.jsx`:

```jsx
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'

const fmtTs = (ts) => ts ? new Date(ts * 1000).toLocaleString() : '—'

function StepRow({ s }) {
  return (
    <li style={{ fontSize: 12, margin: '2px 0' }}>
      <span style={{ color: s.ok ? 'var(--green)' : 'var(--red)' }}>{s.ok ? '✓' : '✗'}</span>{' '}
      {s.desc}{s.detail && <span style={{ color: 'var(--muted)' }}> — {s.detail}</span>}
      {s.screenshot_path && (
        <a style={{ marginLeft: 6 }} target="_blank" rel="noreferrer"
          href={`/api/agent/artifacts/${encodeURIComponent(s.screenshot_path.split('/').pop())}`}>screenshot</a>
      )}
    </li>
  )
}

export default function Health() {
  const [latest, setLatest] = useState(null)
  const [runs, setRuns] = useState([])
  const [drift, setDrift] = useState([])
  const [err, setErr] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [l, r, props] = await Promise.all([
        api.agentLatest(), api.agentRuns(), api.brainProposals()])
      setLatest(l && l.ts ? l : null)
      setRuns(r)
      setDrift(props.filter(p => p.source === 'usage-agent' && p.status === 'pending'))
    } catch (e) { setErr(e.message) }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  return (
    <div className="wrap">
      {err && <div className="err">{err}</div>}

      <div className="panel full">
        <h3>Last usage-agent run</h3>
        {!latest && <p className="muted">No runs yet — run <code>python -m swingbot.selftest</code>.</p>}
        {latest && (
          <p>
            <b style={{ color: latest.green ? 'var(--green)' : 'var(--red)' }}>
              {latest.green ? 'GREEN' : 'RED'}</b>
            {' '}· {fmtTs(latest.ts)} · {latest.duration_s ?? '—'}s
            {' '}· sessions {latest.traces?.filter(t => t.ok).length ?? 0}/{latest.traces?.length ?? 0} ok
            {' '}· checks: {(latest.checks || []).map(c => `${c.name}${c.ok ? '✓' : '✗'}`).join(' ')}
          </p>
        )}
        {latest?.traces?.map(t => (
          <details key={t.session}>
            <summary style={{ cursor: 'pointer' }}>
              <span style={{ color: t.ok ? 'var(--green)' : 'var(--red)' }}>{t.ok ? '✓' : '✗'}</span>{' '}
              {t.session} ({t.steps?.filter(s => s.ok).length}/{t.steps?.length} steps, {t.duration_s}s)
            </summary>
            <ul style={{ listStyle: 'none', paddingLeft: 16 }}>
              {t.steps?.map((s, i) => <StepRow key={i} s={s} />)}
            </ul>
          </details>
        ))}
      </div>

      <div className="panel full">
        <h3>Drift findings ({drift.length})</h3>
        {drift.length === 0 && <p className="muted">No pending drift — docs and behavior agree.</p>}
        {drift.map(p => (
          <div key={p.id} className="panel" style={{ margin: '8px 0' }}>
            <b>{p.action}</b> · {p.target.doc} {p.target.section}
            <div style={{ fontSize: 12 }}><b>Expected:</b> {p.target.expected}</div>
            <div style={{ fontSize: 12 }}><b>Observed:</b> {p.target.observed}</div>
            <div style={{ fontSize: 12, color: 'var(--muted)' }}>{p.target.suggestion}</div>
            <button className="act danger" style={{ marginTop: 6 }}
              onClick={async () => { await api.brainDismiss(p.id); refresh() }}>Dismiss</button>
          </div>
        ))}
      </div>

      <div className="panel full">
        <h3>Run history</h3>
        <ul style={{ listStyle: 'none', padding: 0, fontSize: 12 }}>
          {runs.slice().reverse().map((r, i) => (
            <li key={i}>
              <span style={{ color: r.green ? 'var(--green)' : 'var(--red)' }}>●</span>{' '}
              {fmtTs(r.ts)} — {r.sessions.filter(s => s.ok).length}/{r.sessions.length} sessions ok,
              {' '}{r.drift_count} drift
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
```

`frontend/src/App.jsx`:
- `import Health from './pages/Health.jsx'`
- add `'health'` to `TABS` (before `'guide'`)
- add a nav button after Settings: `<button className={tab==='health'?'active':''} onClick={()=>setTab('health')}>Health</button>`
- add render: `{tab==='health' && <Health />}`

`src/swingbot/selftest/uiprobe.py` — add `"/#/health"` to `ROUTES` (before
`"/#/guide"`), and update `test_routes_cover_all_tabs_via_hash` in
`tests/test_selftest_uiprobe.py` to the 7-route list. Also update the S1 tab
check in `src/swingbot/selftest/sessions.py` `_TAB_CHECKS`: add
`("/#/health", "text=Last usage-agent run")` (and adjust the
`len(trace.steps) == 6` asserts in `tests/test_selftest_sessions.py` to 7,
adding `"text=Last usage-agent run"` to `_ALL_S1`).

- [ ] **Step 4: Verify**

Run: `.venv/bin/python -m pytest tests/test_web_agent.py tests/test_selftest_uiprobe.py tests/test_selftest_sessions.py -q` → PASS
Run: `cd frontend && npm run build` → succeeds.

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/web.py src/swingbot/webmain.py frontend/src/api.js \
        frontend/src/pages/Health.jsx frontend/src/App.jsx \
        src/swingbot/selftest/uiprobe.py src/swingbot/selftest/sessions.py \
        tests/test_web_agent.py tests/test_selftest_uiprobe.py tests/test_selftest_sessions.py
git commit -m "feat(e): /api/agent endpoints + Health tab"
```

---

### Task 9: Pipeline integration — runner, report, DEVLOG-at-top, ROADMAP writer, CLI

**Files:**
- Modify: `src/swingbot/selftest/runner.py`
- Modify: `src/swingbot/selftest/report.py`
- Modify: `src/swingbot/selftest/__main__.py`
- Test: `tests/test_selftest_runner.py`, `tests/test_selftest_report.py` (extend)

- [ ] **Step 1: Failing runner tests (gate table extension)**

Append to `tests/test_selftest_runner.py` (reuse that file's existing fakes for
`runner_fn`/`probe_fn`/config; the pattern below shows the new injectables —
adapt the config construction to the file's existing helper):

```python
from swingbot.selftest import SessionStep, SessionTrace


def _ok_trace(name="s1-tabs"):
    return SessionTrace(session=name, ok=True,
                        steps=[SessionStep(desc="x", action="goto", ok=True)])


def _drift_trace():
    return SessionTrace(session="s6-guide", ok=False, steps=[SessionStep(
        desc="check", action="assert", ok=False,
        detail="missing", expectation_key="s6.affordance-exists")])


def test_session_infra_failure_is_red(tmp_path, green_config):
    cfg = green_config(tmp_path)            # checks pass, probe clean
    rc = run(cfg, runner_fn=ok_runner, probe_fn=lambda *a: [],
             sessions_fn=lambda config: ([], False), llm_fn=no_llm)
    assert rc == 1


def test_drift_only_stays_green_and_stores_proposals(tmp_path, green_config):
    cfg = green_config(tmp_path)
    rc = run(cfg, runner_fn=ok_runner, probe_fn=lambda *a: [],
             sessions_fn=lambda config: ([_drift_trace()], True), llm_fn=no_llm)
    assert rc == 0
    from swingbot.decision.proposals import ProposalStore
    rows = ProposalStore(cfg.proposal_store_path).all()
    assert any(p.source == "usage-agent" and p.action == "doc_fix" for p in rows)


def test_agent_run_persisted(tmp_path, green_config):
    cfg = green_config(tmp_path)
    run(cfg, runner_fn=ok_runner, probe_fn=lambda *a: [],
        sessions_fn=lambda config: ([_ok_trace()], True), llm_fn=no_llm)
    from swingbot.selftest.agentstore import AgentRunStore
    latest = AgentRunStore(cfg.agent_dir).latest()
    assert latest["green"] is True
    assert latest["traces"][0]["session"] == "s1-tabs"


def test_no_sessions_flag_skips_stage(tmp_path, green_config):
    cfg = green_config(tmp_path)
    cfg.run_sessions = False
    called = []
    rc = run(cfg, runner_fn=ok_runner, probe_fn=lambda *a: [],
             sessions_fn=lambda config: called.append(1) or ([], True),
             llm_fn=no_llm)
    assert rc == 0 and called == []
```

`green_config` must set the new `SelfTestConfig` fields:
`agent_dir=str(tmp_path / "agent")`, `run_sessions=True`, `ephemeral_port=8001`,
and point `report_path`/`devlog_path`/`roadmap_path`/`proposal_store_path` at
tmp files. If the file has no such fixture, create one from its existing config
construction.

Run: `.venv/bin/python -m pytest tests/test_selftest_runner.py -q`
Expected: new tests FAIL (`SelfTestConfig` has no `agent_dir`; `run()` has no `sessions_fn`).

- [ ] **Step 2: Extend `SelfTestConfig` and `run()` in `runner.py`**

Add fields to `SelfTestConfig`:

```python
    agent_dir: str = ""
    roadmap_path: str = ""
    run_sessions: bool = True
    ephemeral_port: int = 8001
```

Add the real-sessions driver next to `_real_probe`:

```python
def _real_sessions(config: "SelfTestConfig") -> tuple[list, bool]:
    """Returns (traces, infra_ok). Assertion failures live inside the traces;
    infra_ok=False means browser/ephemeral-app failure -> RED."""
    from playwright.sync_api import sync_playwright  # lazy
    from swingbot.selftest.agentstore import AgentRunStore
    from swingbot.selftest.ephemeral import EphemeralApp
    from swingbot.selftest.sessions import (EPHEMERAL_SESSIONS, LIVE_SESSIONS,
                                            SessionContext)
    shots = AgentRunStore(config.agent_dir).screenshot_dir if config.agent_dir else ""
    traces, infra_ok = [], True
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            bctx = browser.new_context()
            live = SessionContext(base_url=config.base_url, screenshot_dir=shots)
            for s in LIVE_SESSIONS:
                traces.append(s.run(bctx.new_page(), live))
            try:
                with EphemeralApp(port=config.ephemeral_port,
                                  agent_dir=config.agent_dir) as app:
                    ectx = SessionContext(base_url=app.base_url, token=app.token,
                                          screenshot_dir=shots,
                                          seed_proposals=app.seed_proposals)
                    for s in EPHEMERAL_SESSIONS:
                        traces.append(s.run(bctx.new_page(), ectx))
            except Exception:
                infra_ok = False
            browser.close()
    except Exception:
        infra_ok = False
    return traces, infra_ok
```

In `run()`:
- signature gains `sessions_fn=None`; default `sessions_fn = sessions_fn or _real_sessions`.
- after the `ui_findings` line:

```python
        traces, session_infra_ok = ([], True)
        if config.run_sessions:
            traces, session_infra_ok = sessions_fn(config)

        green = (
            all(c.ok for c in checks)
            and not any(f.severity == "fatal" for f in ui_findings)
            and session_infra_ok
        )
```

- after computing `summary`, reconcile drift and store proposals (drift is the
  product — stored even with `--no-llm`; LLM analysis remains green-gated):

```python
        from dataclasses import asdict

        from swingbot.selftest.drift import findings_to_proposals, reconcile

        drift = reconcile(traces)
        drift_proposals = findings_to_proposals(drift)
        store = ProposalStore(config.proposal_store_path)
        if green and drift_proposals:
            known = {p.id for p in store.all()}
            new = [p for p in drift_proposals if p.id not in known]
            store.add_many(drift_proposals)
            if new:
                notifier.send("usage_drift", {"count": len(new),
                                              "sessions": sorted({f.session for f in drift})})

        proposals: list[Proposal] = []
        if green and not config.skip_llm:
            client = OllamaClient(config.ollama_url, config.ollama_model,
                                  config.ollama_timeout_s)
            proposals = llm_fn(summary, client, store, notifier)
        elif not green:
            notifier.send("selftest_red", {
                "failed_checks": [c.name for c in checks if not c.ok],
                "fatal_ui": sum(1 for f in ui_findings if f.severity == "fatal"),
                "session_infra_ok": session_infra_ok,
            })
```

(the old `store = ProposalStore(...)` line inside the LLM branch moves up as shown)

- persist the run + write reports:

```python
        if config.agent_dir:
            from swingbot.selftest.agentstore import AgentRunStore
            AgentRunStore(config.agent_dir).add({
                "ts": started_at, "green": green,
                "duration_s": summary.duration_s,
                "checks": [asdict(c) for c in checks],
                "route_findings": [asdict(f) for f in ui_findings],
                "traces": [asdict(t) for t in traces],
                "drift": [asdict(d) for d in drift],
                "proposal_ids": [p.id for p in drift_proposals],
            })

        write_report(summary, proposals, config.report_path, config.devlog_path,
                     traces=traces, drift=drift)
        if config.roadmap_path and green and drift:
            from swingbot.selftest.report import update_roadmap_next_action
            update_roadmap_next_action(config.roadmap_path, len(drift))
        return 0 if green else 1
```

Run: `.venv/bin/python -m pytest tests/test_selftest_runner.py -q` → PASS
(existing tests keep passing because `sessions_fn` defaults are bypassed by
`run_sessions=False` or an injected stub — update any existing test configs to
set `run_sessions=False` if they don't inject `sessions_fn`).

- [ ] **Step 3: Failing report tests**

Append to `tests/test_selftest_report.py`:

```python
from swingbot.selftest import DriftFinding, SessionStep, SessionTrace
from swingbot.selftest.report import update_roadmap_next_action


def test_report_includes_sessions_and_drift_sections(tmp_path, summary_factory):
    t = SessionTrace(session="s1-tabs", ok=False, duration_s=1.2,
                     steps=[SessionStep(desc="x", action="goto", ok=False,
                                        detail="boom")])
    d = DriftFinding(session="s1-tabs", step="x", expected="renders",
                     observed="boom", doc_ref="frontend/src/guide.md §y",
                     kind="drift")
    rp, dl = str(tmp_path / "r.md"), str(tmp_path / "d.md")
    write_report(summary_factory(), [], rp, dl, traces=[t], drift=[d])
    body = open(rp).read()
    assert "## Usage Sessions" in body and "s1-tabs" in body
    assert "## Drift Findings" in body and "frontend/src/guide.md" in body
    assert "drift:1" in open(dl).read()


def test_devlog_inserts_at_top_not_bottom(tmp_path, summary_factory):
    dl = tmp_path / "DEVLOG.md"
    dl.write_text("# Devlog\n\nRunning log of platform improvements. "
                  "Newest first.\n\n## Old entry\nold\n")
    write_report(summary_factory(), [], str(tmp_path / "r.md"), str(dl))
    content = dl.read_text()
    assert content.index("GREEN") < content.index("## Old entry")
    assert content.startswith("# Devlog")


def test_roadmap_writer_inserts_and_replaces_pointer(tmp_path):
    rm = tmp_path / "ROADMAP_STATUS.md"
    rm.write_text("# Roadmap\n\n## ▶ NEXT ACTION\n\nDo the thing.\n\n---\n\nrest\n")
    update_roadmap_next_action(str(rm), 3)
    one = rm.read_text()
    assert "3 drift finding(s)" in one and "Do the thing." in one
    update_roadmap_next_action(str(rm), 5)
    two = rm.read_text()
    assert "5 drift finding(s)" in two and "3 drift finding(s)" not in two
```

(`summary_factory` = however the existing tests in this file build a green
`HealthSummary`; reuse it, or add a small helper matching their pattern.)

Run: `.venv/bin/python -m pytest tests/test_selftest_report.py -q` → new tests FAIL.

- [ ] **Step 4: Implement report changes**

In `src/swingbot/selftest/report.py`:

Change the signature: `def write_report(summary, proposals, report_path, devlog_path, traces=None, drift=None) -> None:` with `traces = traces or []` / `drift = drift or []` at the top.

After the UI-findings section, add:

```python
    lines += ["", "## Usage Sessions", ""]
    if traces:
        lines += ["| Session | Status | Steps | Duration |",
                  "|---------|--------|-------|----------|"]
        for t in traces:
            passed = sum(1 for s in t.steps if s.ok)
            lines.append(f"| {t.session} | {'✅' if t.ok else '❌'} "
                         f"| {passed}/{len(t.steps)} | {t.duration_s}s |")
        failed = [(t.session, s) for t in traces for s in t.steps if not s.ok]
        if failed:
            lines += ["", "**Failed steps:**", ""]
            for session, s in failed:
                lines.append(f"- `{session}` — {s.desc}: {s.detail[:160]}")
    else:
        lines.append("_Sessions skipped._")

    lines += ["", "## Drift Findings", ""]
    if drift:
        lines += ["| Session | Kind | Expected | Observed | Doc ref |",
                  "|---------|------|----------|----------|---------|"]
        for d in drift:
            lines.append(f"| {d.session} | {d.kind} | {d.expected[:60]} "
                         f"| {d.observed[:60]} | {d.doc_ref[:60]} |")
    else:
        lines.append("_No drift — observed behavior matches the docs._")
```

Replace the trailing DEVLOG append block with insert-at-top (audit fix #6/#4 of
the spec's fold-in list):

```python
    passed_sessions = sum(1 for t in traces if t.ok)
    devlog_line = (
        f"{dt_str}  {status}  {summary.duration_s}s  "
        f"{check_icons}  ui:{fatal_count}fatal  "
        f"sessions:{passed_sessions}/{len(traces)}  drift:{len(drift)}  "
        f"proposals:{len(proposals)}"
    )
    _insert_devlog_line(devlog_path, devlog_line)
```

and add the two new helpers at module level:

```python
_DEVLOG_HEADER_MARKER = "Newest first.\n"


def _insert_devlog_line(devlog_path: str, line: str) -> None:
    """Insert directly under the header so the log stays newest-first."""
    try:
        with open(devlog_path) as fh:
            content = fh.read()
    except OSError:
        content = "# Devlog\n\nRunning log of platform improvements. Newest first.\n"
    i = content.find(_DEVLOG_HEADER_MARKER)
    if i == -1:
        content = line + "\n" + content
    else:
        j = i + len(_DEVLOG_HEADER_MARKER)
        content = content[:j] + "\n" + line + "\n" + content[j:]
    with open(devlog_path, "w") as fh:
        fh.write(content)


_ROADMAP_POINTER_PREFIX = "**Usage Agent:"


def update_roadmap_next_action(roadmap_path: str, drift_count: int) -> None:
    """Prepend a pointer line inside the NEXT ACTION block (idempotent: any
    previous usage-agent pointer line is replaced, the rest is untouched)."""
    try:
        with open(roadmap_path) as fh:
            lines = fh.read().splitlines(keepends=True)
    except OSError:
        return
    lines = [ln for ln in lines if not ln.startswith(_ROADMAP_POINTER_PREFIX)]
    pointer = (f"{_ROADMAP_POINTER_PREFIX} {drift_count} drift finding(s) pending — "
               f"see docs/SELFTEST_REPORT.md §Drift Findings and the Health tab.**\n")
    out, inserted = [], False
    for ln in lines:
        out.append(ln)
        if not inserted and ln.startswith("## ▶ NEXT ACTION"):
            out += ["\n", pointer]
            inserted = True
    if not inserted:
        out = [pointer, "\n"] + out
    with open(roadmap_path, "w") as fh:
        fh.write("".join(out))
```

Run: `.venv/bin/python -m pytest tests/test_selftest_report.py -q` → PASS.

- [ ] **Step 5: CLI flags + store-path fix in `__main__.py`**

In `src/swingbot/selftest/__main__.py`:
- add args:

```python
    parser.add_argument("--no-sessions",    action="store_true")
    parser.add_argument("--ephemeral-port", type=int, default=8001)
```

- extend the config:

```python
        proposal_store_path=os.path.join(DATA_DIR, "brain_proposals.json"),
        agent_dir=os.path.join(DATA_DIR, "agent"),
        roadmap_path=os.path.join(PROJECT_ROOT, "docs", "ROADMAP_STATUS.md"),
        run_sessions=not args.no_sessions,
        ephemeral_port=args.ephemeral_port,
```

Note the `proposal_store_path` change from `proposals.json` to
`brain_proposals.json`: the web app's brain inbox (see `webmain.py:83`) reads
`brain_proposals.json` — D was silently writing proposals to a file the UI
never reads. This makes selftest/usage-agent proposals actually appear on the
Brain/Health pages.

- [ ] **Step 6: Full suite + commit**

Run: `.venv/bin/python -m pytest -q` and `.venv/bin/python -m ruff check .` → green.

```bash
git add src/swingbot/selftest/runner.py src/swingbot/selftest/report.py \
        src/swingbot/selftest/__main__.py \
        tests/test_selftest_runner.py tests/test_selftest_report.py
git commit -m "feat(e): wire sessions+drift into the selftest pipeline; DEVLOG newest-first; ROADMAP pointer; unify proposal store"
```

---

### Task 10: Guide rewrite, toast, live full-loop verification, docs

**Files:**
- Modify: `frontend/src/guide.md`
- Modify: `src/swingbot/selftest/expectations.py` (affordance list sync)
- Modify: `frontend/src/pages/Discover.jsx` (alert → toast)
- Modify: `docs/ROADMAP_STATUS.md`, `docs/DEVLOG.md`

- [ ] **Step 1: Rewrite the stale Guide sections**

All edits to `frontend/src/guide.md`:

**(a)** In "The 5 steps" table, replace row 4
`| 4 | Strategy | **Set active** on that profile |` with:

```markdown
| 4 | Strategy | **Arm** the profile (Strategies panel). Arm several to trade them concurrently. |
```

**(b)** Find the real no-strategies error string first:
`grep -rn "armed" src/swingbot/supervisor.py | grep -i "no \|error\|raise"` —
then update the line *"If you skip step 3 or 4, **Start bot** returns 'no
active strategy profile set.'"* to quote that actual message.

**(c)** Replace the whole "### Step 4 — Set the profile active" section with:

```markdown
### Step 4 — Arm the profile

Saving a profile does **not** start it trading. On the Strategy page, find your
profile in the **Strategies** panel and click **Arm**. The bot runs **all armed
profiles concurrently** (one per symbol); **Disarm** stops one (its open
position is flattened first). The per-profile **live-eligible** flag decides
whether that strategy may open trades once the portfolio is switched to LIVE.
```

**(d)** Fix the FVG signal row (it is implemented now — `e852ea7`). Replace the
FVG row in the signals table with:

```markdown
| **FVG** | `weight` | Price trades back into an unfilled bullish fair-value gap (ICT-style 3-candle imbalance). |
```

(then sanity-check the param list against `src/swingbot/signals/` — e.g.
`grep -n "def \|param\|weight" src/swingbot/signals/fvg.py` — and include any
extra tunables that file actually reads.)

**(e)** Add a new section before "## Going live":

```markdown
## Discover, Brain & Health

Three pages automate the manual loop above:

- **Discover** sweeps the archived history of the whole universe (or your
  watchlist) against the built-in strategy archetypes, ranks the results by
  expectancy, and flags combos that are *eligible now* (good history + regime
  OK). One click on **Arm** saves and arms that combo as a `disc-…` profile.
- **Brain** is the local-LLM decision console. **Recommend now** asks the
  model (configurable, e.g. `qwen3.5:9b` via Ollama) for proposals — arm /
  disarm / tune / settings — each pre-screened by hard guardrails. Everything
  is **recommend-only** unless you enable Autonomous mode; `ui_fix`/`doc_fix`
  findings can never be auto-applied — review them, fix manually, dismiss.
- **Health** shows what the usage agent (`python -m swingbot.selftest`) found
  on its last run: per-session step traces, screenshots, and **drift
  findings** — places where this Guide or the specs disagree with what the app
  actually does.
```

- [ ] **Step 2: Sync the affordance list to the rewritten Guide**

In `src/swingbot/selftest/expectations.py`, replace the stale entry:

```python
    ("Arm",              "/#/strategy",  '§"Step 4 — Arm the profile"'),
```

(drop the `("Set active", …)` line and its stale-marker comment). Confirm the
Strategy page actually renders an "Arm" button when a profile exists —
`grep -n '>Arm<' frontend/src/components/StrategyManager.jsx` (it does, line 39;
StrategyManager is rendered by the Strategy page).

Run: `.venv/bin/python -m pytest tests/test_selftest_expectations.py tests/test_selftest_sessions.py -q`
Expected: PASS — but `test_s6_flags_missing_affordance` references "Set active";
update that test so the missing affordance is `"Arm"` (present list omits
`"text=Arm"` instead).

- [ ] **Step 3: Replace Discover's blocking `alert()` with a toast**

In `frontend/src/pages/Discover.jsx`:

```jsx
  const [toast, setToast] = useState('')

  const arm = async (row) => {
    await api.armDiscovery(row.symbol, row.archetype, window)
    setToast(`Armed ${row.symbol} · ${row.label}`)
    setTimeout(() => setToast(''), 4000)
  }
```

and render it just under the controls div:

```jsx
      {toast && <p className="pos" role="status">{toast}</p>}
```

Run: `cd frontend && npm run build` → succeeds.

- [ ] **Step 4: Commit the code**

```bash
git add frontend/src/guide.md frontend/src/pages/Discover.jsx \
        src/swingbot/selftest/expectations.py tests/test_selftest_sessions.py
git commit -m "docs(e): rewrite stale Guide (arm model, real FVG, Discover/Brain/Health); toast instead of alert"
```

- [ ] **Step 5: Housekeeping check — D plan tracked**

Run: `git ls-files docs/superpowers/plans/2026-06-03-subproject-d-self-test-gate.md`
If empty, `git add` + commit that file (audit fix #7). (It was committed with
the E spec on 2026-06-12 — this is just verification.)

- [ ] **Step 6: Rebuild + restart the container (standing rule)**

```bash
docker compose build swingbot && docker compose up -d swingbot
```

Wait for healthy: `curl -s http://localhost:8000/api/state | head -c 200`.

- [ ] **Step 7: Full-loop live verification**

```bash
.venv/bin/python -m pytest -q                       # green (baseline + ~40 new)
cd frontend && npm run build && cd ..
.venv/bin/python -m swingbot.selftest --no-llm      # full gate + sessions
echo "exit=$?"
```

Expected: exit 0. Then verify each loop output:
- `docs/SELFTEST_REPORT.md` has **Usage Sessions** (6 sessions listed, all
  routes now rendering — no more 404 route warns) and **Drift Findings**.
- `~/.swingbot/agent/runs.json` exists; `curl -s http://localhost:8000/api/agent/runs/latest | head -c 400` returns the run (host agent dir = container `/data/agent`).
- `docs/DEVLOG.md` — the new one-liner is at the **top**, under the header.
- Health tab renders: use Playwright MCP to open `http://localhost:8000/#/health`,
  confirm last-run banner + session traces + drift cards, screenshot it.
- Brain page: any `doc_fix`/`ui_fix` cards show **Dismiss only** (no Apply).
- If drift findings exist (expected zero after the Guide rewrite; if S6 still
  flags something, that's the loop working — file it, don't fight it), confirm
  the ROADMAP pointer line appears in `docs/ROADMAP_STATUS.md` §NEXT ACTION.

- [ ] **Step 8: Update the knowledge graph**

Run: `python3 -m graphify update .`

- [ ] **Step 9: Close out docs + final commit**

- `docs/DEVLOG.md`: add a dated **Sub-project E** entry at the top (sessions
  S1–S6, two-tier safety, doc_fix, Health tab, audit fixes folded in).
- `docs/ROADMAP_STATUS.md`: set **Last updated** to today; status-board row E →
  ✅ **DONE** with plan path `plans/2026-06-12-subproject-e-usage-agent.md`;
  rewrite **NEXT ACTION** (suggest: schedule the nightly selftest run via
  `/schedule`, and triage any drift findings on the Health tab).
- Tick all checkboxes in this plan file.

```bash
git add docs/DEVLOG.md docs/ROADMAP_STATUS.md docs/SELFTEST_REPORT.md \
        docs/superpowers/plans/2026-06-12-subproject-e-usage-agent.md
git commit -m "docs(e): Sub-project E complete — usage agent live-verified"
```

Pushing to `origin/master` is a user decision (D's commits are also unpushed) —
ask once at the end, don't push unprompted.

---

## Self-review notes (spec coverage)

- Spec §Decisions → Tasks 1 (hash routing), 5–6 (deterministic sessions, two
  tiers), 3 (expectations + doc refs), 7 (`doc_fix`, Apply dead-end,
  guardrails), 2+9 (`DATA_DIR/agent` artifacts), 9 (DEVLOG top-insert, ROADMAP
  writer). Task 7 also adds a `supersede_pending` carve-out discovered during
  planning: without it every brain recommend run would mark pending
  usage-agent findings superseded, emptying the Health tab. (`autonomous_mode`
  needs no extra guard — `prompt.py` `VALID_ACTIONS` already drops
  `ui_fix`/`doc_fix` at parse, so they can never enter the autonomous loop;
  the `_dispatch` rejection covers manual/API apply.)
- Spec §Pipeline 1–6 → Task 9 (infra failure RED / drift stays GREEN; `usage_drift`
  Discord event; report sections; `--no-sessions`/`--ephemeral-port`; exit codes
  unchanged).
- Spec §Endpoints + §Health tab → Task 8.
- Spec §Targeted fixes 1–7 → Tasks 1, 7, 9, 10 (routing; Apply dead-end; llm
  guardrail ctx; DEVLOG order; alert→toast; Guide rewrite; D plan commit check).
- Spec §Error handling → ephemeral `finally`-equivalent teardown +
  pidfile stale-kill (Task 4); `_real_sessions` wraps everything (Task 9).
- Spec §Testing list → one test file per module, gate table extended, artifact
  path-traversal test, `npm run build` in Tasks 1/7/8/10.
- Known deliberate scope choices: S2/S5 drive mutations via the API with UI
  asserts on top (sessions stay deterministic; full form-filling via Playwright
  is YAGNI for v1); S4 is API-only persistence (no page shows
  `max_concurrent` today); `GUIDE_AFFORDANCES` is a static catalog synced in
  Task 10 (parsing guide.md is the v2 extension point).
