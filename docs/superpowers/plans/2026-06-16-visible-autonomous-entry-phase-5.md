# Visible Autonomous Entry — Phase 5: Rebuild the dashboard around truthful state

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the truthful runtime state the Phase 1–4 backend already produces — desired-vs-actual running, startup error, broker-confirmed positions and pending orders, last cycle/bar timestamp and decision code/reason, realized + unrealized P&L with source timestamps, durable entry/exit markers, trading reliability with counts and window, and managed-strategy labels (`kind: strategy|probe`) including probe completion — on the dashboard, keeping the usage-agent health on its own tab.

**Architecture:** Three small, additive backend changes expose data the UI needs but cannot currently read (managed labels, pending orders, probe completion, unrealized P&L). The rest is a frontend rebuild of the Dashboard around `/api/state` (now enriched) plus the existing `/api/health/trading` (lifecycle + last decisions + reliability in one call). No strategy behavior changes; no broker/network calls added.

**Tech Stack:** Python 3.11, FastAPI, pytest, ruff. Frontend: React 18 + Vite (no JS test runner — frontend is verified by `npm run build`, matching the project's regression gate). Charts: `lightweight-charts` (already renders entry/exit markers from `trades`).

---

## Context for a cold code-gen agent

You are implementing Phase 5 of the "visible autonomous entry" roadmap for `crypto-swing-bot`. You may have **zero prior context**. Read this section before touching code.

### House rules (non-negotiable)
- **Python interpreter:** `.venv/bin/python` (plain `python`/`pytest` are NOT on PATH). Run tests with `.venv/bin/python -m pytest -q`.
- **TDD:** for every backend change, write the failing test first, watch it fail, then implement. Commit per task.
- **Lint:** `ruff check src/` must be clean before each commit.
- **Frontend build:** `cd frontend && npm run build` must succeed before committing a frontend task. There is **no** JS unit-test runner; do not add one.
- **Scope discipline:** `git add` only the files this plan names for the current task. The working tree may carry **unrelated uncommitted FVG/presets/graphify work — leave it untouched.** Never `git add -A`.
- **Do NOT** hide or disable strategy creation. Phase 4 formally ruled managed-canvas server-side enforcement **out of scope**, so the spec's conditional ("Hide or disable strategy creation only according to the managed-canvas server contract") does not trigger. Keep all operational controls (`ControlBar`, arm/disarm/flatten) intact — the spec says "Do not remove operational controls needed to recover from failures."

### Current code state (what Phases 1–4 already built — build on this, do not rewrite)
- `src/swingbot/supervisor.py` — `PortfolioSupervisor`. Read methods already exist:
  - `status()` → `{"portfolio": {...}, "strategies": [ {name, symbol, running, live_eligible, snapshot, position, risk}, ... ]}`. Positions are **broker-confirmed** (Phase 3). Has two branches: running (live `_strategies`) and not-running (rebuilt from armed profiles).
  - `lifecycle_state()` → `{mode, running_flag, thread_alive, running_actual, running_desired, running_desired_error, paused, halted, startup_error}`.
  - `trading_health()` → `{status, lifecycle, last_cycle, last_decisions_by_strategy, reliability}`. `status` ∈ `{active, inactive, unhealthy}`. `last_cycle`/decisions use `_cycle_dict` (has `bar_ts`, `decision_code`, `decision_reason`, `completed_at`). `reliability` carries per-stage `ok/failed` counts and window timestamps.
  - `readiness()` → `{ready, checks:{...}}`.
  - `journal(strategy=None)` / `metrics(strategy=None)` — durable trades + computed metrics. `_trade_dict` has `entry_ts, exit_ts, entry_price, exit_price, qty, pnl, exit_reason, score_at_entry, regime_at_entry` (NO `symbol`/`strategy` field — filter by passing `?strategy=` to the endpoint).
  - Supervisor holds `self._store` (state/order/trade store), `self._market` (local market-data store — reads are local SQLite/cached, NOT broker network), `self._probe_marker` (a `ProbeMarkerStore` or `None`), and `self.profiles`.
  - Helpers at module bottom: `_pos_dict(pos)`, `_trade_dict(t)`, `_cycle_dict(record)`.
- `src/swingbot/managed_profiles.py` — `MANAGED_PROFILE_NAMES = {"btc_trend","eth_trend","paper_probe"}` and:
  ```python
  MANAGED_LABELS = {
      "btc_trend": {"kind": "strategy", "label": "BTC Trend (EMA)"},
      "eth_trend": {"kind": "strategy", "label": "ETH Trend (EMA)"},
      "paper_probe": {"kind": "probe", "label": "proof-of-life probe"},
  }
  ```
- `src/swingbot/probe_marker.py` — `ProbeMarkerStore` with `.is_complete(name) -> bool` and `.mark_complete(name)`.
- `src/swingbot/state.py` — `load_all_pending_orders() -> dict[str, PendingOrder]` keyed by strategy. `PendingOrder` fields: `client_order_id, broker_order_id, symbol, side (OrderSide enum), submitted_at (datetime), requested_qty, stop, tp, max_hold_until, score_at_entry, regime_at_entry, exit_reason, observed_exit_price`.
- `src/swingbot/web.py` — `create_app(controller, profiles, creds, token, store=None, market=None, ...)`. `/api/state` returns `controller.status()`. `/api/strategies` builds a list from `profiles.list()` + `profiles.armed_with_flags()`. `/api/health/trading` returns `controller.trading_health()`. `/api/journal`, `/api/metrics`, `/api/candles` exist.
- Frontend (`frontend/src/`): `App.jsx` polls `/api/state` every 3s and journal+metrics every 10s, passing `{state, trades, metrics}` to `pages/Dashboard.jsx`. `Dashboard.jsx` renders `PositionGrid`, per-strategy `StrategyCard`, `MetricsPanel`, `JournalTable`. `Health.jsx` already shows usage-agent runs (keep it there). `api.js` exposes `api.state/journal/metrics/strategies/...` — there is **no** `tradingHealth` yet. `ChartPanel.jsx` already renders entry/exit arrows when passed a `trades` prop (`tradeMarkers()`), and draws entry/stop/tp lines from `position`.

### Spec
Authoritative spec: `docs/superpowers/specs/2026-06-13-visible-autonomous-entry-design-reviewed.md` §"Phase 5: Rebuild the dashboard around truthful state". It says SHOW:
> desired vs actual running state and startup error; broker-confirmed positions and pending orders; last cycle/bar timestamp and last decision code/reason; realized and unrealized P&L with source timestamps; durable entry/exit markers; trading reliability with counts and window; usage-agent health as a separate section.
> Do not remove operational controls needed to recover from failures. Hide or disable strategy creation only according to the managed-canvas server contract.

### Success criteria (Phase 5 is done when)
1. `/api/strategies` and `/api/state` strategies each carry `kind` and `label`.
2. `/api/state` carries `pending_orders` (list) and each strategy carries `probe_complete` (bool for probes, `null` otherwise).
3. Each open position in `/api/state` carries `mark_price`, `mark_ts`, and `unrealized` (or nulls when no local price).
4. The Dashboard shows: a lifecycle banner (desired vs actual + startup error), managed-strategy labels/probe state, pending orders, last decision code/reason + bar timestamp per strategy, realized + unrealized P&L with source timestamps, entry/exit chart markers, and a reliability panel with counts + window.
5. Usage-agent health remains on the Health tab (not merged into the Dashboard).
6. Operational controls (start/stop/pause/resume/halt/flatten/arm/disarm) remain available.
7. Gate green: `.venv/bin/python -m pytest -q`, `ruff check src/`, `cd frontend && npm run build`.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/swingbot/managed_profiles.py` | Modify | Add `managed_meta(name)` lookup helper (DRY label source). |
| `src/swingbot/web.py` | Modify | `/api/strategies` adds `kind`/`label`. |
| `src/swingbot/supervisor.py` | Modify | `status()` adds `pending_orders`, per-strategy `kind`/`label`/`probe_complete`, and `mark_price`/`mark_ts`/`unrealized` on open positions. New `_pending_dict` helper. |
| `tests/test_web_strategy.py` | Modify | Test `/api/strategies` labels. |
| `tests/test_supervisor_managed.py` | Modify | Test status() pending orders, labels, probe_complete, unrealized P&L. |
| `frontend/src/api.js` | Modify | Add `tradingHealth()`. |
| `frontend/src/App.jsx` | Modify | Poll trading health; pass to Dashboard. |
| `frontend/src/pages/Dashboard.jsx` | Modify | Compose new panels. |
| `frontend/src/components/LifecycleBanner.jsx` | Create | Desired vs actual + startup error. |
| `frontend/src/components/StrategyCard.jsx` | Modify | kind/label badge, probe state, last decision, unrealized P&L, per-strategy trade markers. |
| `frontend/src/components/PendingOrders.jsx` | Create | Pending-order table. |
| `frontend/src/components/ReliabilityPanel.jsx` | Create | Reliability counts + window. |
| `frontend/src/components/MetricsPanel.jsx` | Modify | Realized P&L total + source timestamp. |
| `docs/ROADMAP_STATUS.md` | Modify | Phase 5 done; set Phase 6 anchor. |

---

## Task 1: `managed_meta()` helper + `/api/strategies` labels

**Files:**
- Modify: `src/swingbot/managed_profiles.py`
- Modify: `src/swingbot/web.py:166-174` (`/api/strategies`)
- Test: `tests/test_web_strategy.py`

- [x] **Step 1: Write the failing test**

Add to `tests/test_web_strategy.py`:

```python
def test_strategies_carry_kind_and_label():
    class FakeProfiles:
        def list(self): return ["btc_trend", "paper_probe", "my_custom"]
        def get(self, name): return {"symbol": {"btc_trend": "BTC/USD",
                                                 "paper_probe": "BTC/USD",
                                                 "my_custom": "ETH/USD"}[name]}
        def armed_with_flags(self): return [{"name": "btc_trend", "live_eligible": True}]
    app = create_app(_Ctl(), profiles=FakeProfiles(), creds=None, token="t",
                     store=None, market=FakeMarket())
    rows = {r["name"]: r for r in TestClient(app).get("/api/strategies").json()}
    assert rows["btc_trend"]["kind"] == "strategy"
    assert rows["btc_trend"]["label"] == "BTC Trend (EMA)"
    assert rows["paper_probe"]["kind"] == "probe"
    assert rows["paper_probe"]["label"] == "proof-of-life probe"
    # user profiles get a safe default
    assert rows["my_custom"]["kind"] == "user"
    assert rows["my_custom"]["label"] == "my_custom"
    assert rows["btc_trend"]["armed"] is True and rows["my_custom"]["armed"] is False
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_web_strategy.py::test_strategies_carry_kind_and_label -v`
Expected: FAIL with `KeyError: 'kind'`.

- [x] **Step 3: Add the helper to `managed_profiles.py`**

After the `MANAGED_LABELS` dict, add:

```python
def managed_meta(name: str) -> dict:
    """UI metadata for a profile: kind (strategy|probe|user) and a display label.

    Unknown (user-created) profiles default to kind 'user' and their own name.
    """
    return MANAGED_LABELS.get(name, {"kind": "user", "label": name})
```

- [x] **Step 4: Use it in `/api/strategies`**

In `src/swingbot/web.py`, add the import near the other `swingbot` imports at the top of the file:

```python
from swingbot.managed_profiles import managed_meta
```

Replace the `list_strategies` body (currently around lines 166–174):

```python
    @app.get("/api/strategies")
    def list_strategies():
        flags = {f["name"]: f["live_eligible"] for f in profiles.armed_with_flags()}
        out = []
        for name in profiles.list():
            p = profiles.get(name) or {}
            meta = managed_meta(name)
            out.append({"name": name, "symbol": p.get("symbol"),
                        "armed": name in flags, "live_eligible": flags.get(name, False),
                        "kind": meta["kind"], "label": meta["label"]})
        return out
```

- [x] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_web_strategy.py::test_strategies_carry_kind_and_label -v`
Expected: PASS.

- [x] **Step 6: Lint + commit**

```bash
ruff check src/
git add src/swingbot/managed_profiles.py src/swingbot/web.py tests/test_web_strategy.py
git commit -m "feat(api): expose managed kind/label on /api/strategies"
```

---

## Task 2: `status()` — pending orders, per-strategy labels, probe completion

**Files:**
- Modify: `src/swingbot/supervisor.py` (`status()` ~506-536; add `_pending_dict` near `_pos_dict` ~795)
- Test: `tests/test_supervisor_managed.py`

- [x] **Step 1: Write the failing test**

Add to `tests/test_supervisor_managed.py` (it already imports `_probe_supervisor`, `ProbeMarkerStore`, `FakeBroker`, `FakeMarket`, `_bars`):

```python
def test_status_labels_and_probe_complete(tmp_path):
    sup, broker, marker = _probe_supervisor(tmp_path)
    st = sup.status()
    probe = next(s for s in st["strategies"] if s["name"] == "paper_probe")
    assert probe["kind"] == "probe"
    assert probe["label"] == "proof-of-life probe"
    assert probe["probe_complete"] is False
    marker.mark_complete("paper_probe")
    probe2 = next(s for s in sup.status()["strategies"] if s["name"] == "paper_probe")
    assert probe2["probe_complete"] is True


def test_status_includes_pending_orders(tmp_path):
    from datetime import datetime, timezone
    from swingbot.types import PendingOrder, OrderSide
    from swingbot.regime import Regime  # adjust import if Regime lives elsewhere
    sup, broker, marker = _probe_supervisor(tmp_path)
    order = PendingOrder(
        client_order_id="cid-1", broker_order_id=None, symbol="BTC/USD",
        side=OrderSide.BUY, submitted_at=datetime(2026, 6, 16, tzinfo=timezone.utc),
        requested_qty=0.01, stop=None, tp=None,
        max_hold_until=datetime(2026, 6, 17, tzinfo=timezone.utc),
        score_at_entry=0.9, regime_at_entry=Regime.BULL, exit_reason=None,
        observed_exit_price=None)
    sup._store.save_pending_order(order, strategy="paper_probe")
    pend = sup.status()["pending_orders"]
    assert len(pend) == 1
    assert pend[0]["strategy"] == "paper_probe"
    assert pend[0]["symbol"] == "BTC/USD"
    assert pend[0]["side"] == "buy"
    assert pend[0]["client_order_id"] == "cid-1"
```

> Before running, confirm the exact import paths for `PendingOrder`, `OrderSide`, and `Regime` by grepping `src/swingbot/types.py` and the file that defines `Regime` (e.g. `grep -rn "class Regime\|class OrderSide\|class PendingOrder" src/swingbot/`). Use whatever the codebase exports — the enum `.value` for `OrderSide.BUY` must equal `"buy"` (adjust the assertion if the codebase uses uppercase).

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_supervisor_managed.py::test_status_labels_and_probe_complete tests/test_supervisor_managed.py::test_status_includes_pending_orders -v`
Expected: FAIL (`KeyError: 'probe_complete'` / `KeyError: 'pending_orders'`).

- [x] **Step 3: Add the `_pending_dict` helper**

In `src/swingbot/supervisor.py`, just after `_pos_dict` (~line 802), add:

```python
def _pending_dict(strategy, o):
    return {
        "strategy": strategy,
        "symbol": o.symbol,
        "side": o.side.value,
        "requested_qty": o.requested_qty,
        "submitted_at": o.submitted_at.isoformat(),
        "client_order_id": o.client_order_id,
        "broker_order_id": o.broker_order_id,
    }
```

- [x] **Step 4: Enrich `status()`**

Add the import near the top of `supervisor.py` (with the other `swingbot` imports):

```python
from swingbot.managed_profiles import managed_meta
```

Add a small private helper method on `PortfolioSupervisor` (place it right above `def status`):

```python
    def _probe_complete(self, name: str, kind: str):
        if kind != "probe" or self._probe_marker is None:
            return None
        try:
            return bool(self._probe_marker.is_complete(name))
        except Exception:
            return None
```

In `status()`, in **both** branches where a strategy dict is appended, add the label/probe fields. For the running branch:

```python
                meta = managed_meta(name)
                strategies.append({
                    "name": name, "symbol": s["profile"].symbol,
                    "running": self._running,
                    "live_eligible": self.profiles.is_live_eligible(name),
                    "kind": meta["kind"], "label": meta["label"],
                    "probe_complete": self._probe_complete(name, meta["kind"]),
                    "snapshot": s["snapshot"],
                    "position": _pos_dict(pos),
                    "risk": {"kill_switch": {"active": rs.kill_switch_active,
                                             "reason": rs.kill_switch_reason},
                             "consecutive_losses": rs.consecutive_losses},
                })
```

For the not-running branch:

```python
                meta = managed_meta(name)
                strategies.append({
                    "name": name, "symbol": symbol,
                    "running": False,
                    "live_eligible": f["live_eligible"],
                    "kind": meta["kind"], "label": meta["label"],
                    "probe_complete": self._probe_complete(name, meta["kind"]),
                    "snapshot": {}, "position": None, "risk": None,
                })
```

Finally, build `pending_orders` and add it to the return dict:

```python
        pending = []
        if self._store is not None:
            try:
                for strat, order in self._store.load_all_pending_orders().items():
                    pending.append(_pending_dict(strat, order))
            except Exception:
                pending = []
        return {"portfolio": self._summary or {"mode": self.mode, "running": self._running},
                "strategies": strategies, "pending_orders": pending}
```

- [x] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_supervisor_managed.py -q`
Expected: PASS (including the two new tests).

- [x] **Step 6: Lint + commit**

```bash
ruff check src/
git add src/swingbot/supervisor.py tests/test_supervisor_managed.py
git commit -m "feat(api): status() exposes pending orders, managed labels, and probe completion"
```

---

## Task 3: `status()` — unrealized P&L with source timestamp on open positions

**Files:**
- Modify: `src/swingbot/supervisor.py` (`status()` running branch; new `_mark` helper)
- Test: `tests/test_supervisor_managed.py`

Unrealized P&L = `(mark_price - entry_price) * qty`, where `mark_price`/`mark_ts` come from the **latest local market bar** (no broker network). When no local price is available, all three fields are `null` and the UI shows "—".

- [x] **Step 1: Write the failing test**

Add to `tests/test_supervisor_managed.py`:

```python
def test_status_open_position_has_unrealized_pnl(tmp_path):
    """An open position is annotated with mark_price/mark_ts/unrealized from the local market."""
    sup, broker, marker = _probe_supervisor(tmp_path)
    # Find the live strategy dict and inject a fake open position + market bar.
    name = "paper_probe"
    strat = sup._strategies[name]

    class _Pos:
        symbol = "BTC/USD"; entry_price = 100.0; qty = 2.0
        stop = 90.0; tp = 120.0
        from datetime import datetime, timezone
        max_hold_until = datetime(2026, 6, 17, tzinfo=timezone.utc)
        entry_ts = datetime(2026, 6, 16, tzinfo=timezone.utc)
    strat["view"].load_position = lambda: _Pos()

    st = sup.status()
    s = next(x for x in st["strategies"] if x["name"] == name)
    assert s["position"] is not None
    # FakeMarket._bars last close is deterministic; just assert the math is consistent.
    mp = s["position"]["mark_price"]
    assert mp is not None
    assert s["position"]["mark_ts"] is not None
    assert abs(s["position"]["unrealized"] - (mp - 100.0) * 2.0) < 1e-9


def test_status_unrealized_null_without_market(tmp_path):
    sup = _supervisor(tmp_path)  # no market wired
    sup.build()
    # Not running / no market → any positions report null marks (no crash).
    st = sup.status()
    for s in st["strategies"]:
        if s["position"]:
            assert s["position"]["mark_price"] is None
            assert s["position"]["unrealized"] is None
```

> `_probe_supervisor` wires a `FakeMarket({"BTC/USD": _bars(100.0)})`; `FakeMarket.get(symbol, tf, limit, max_age=None)` returns bars whose dicts contain `"time"` (epoch seconds) and `"close"`. Confirm the exact bar key names with `grep -n "def _bars" tests/test_supervisor.py` and adjust `_mark` (Step 3) to read whatever keys those bars use (`"time"`/`"close"`).

- [x] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_supervisor_managed.py::test_status_open_position_has_unrealized_pnl tests/test_supervisor_managed.py::test_status_unrealized_null_without_market -v`
Expected: FAIL with `KeyError: 'mark_price'`.

- [x] **Step 3: Add a `_mark` helper and annotate positions**

In `src/swingbot/supervisor.py`, add a method on `PortfolioSupervisor` (near `_probe_complete`):

```python
    def _mark(self, symbol: str, timeframe: str):
        """Latest local-market (close_price, bar_ts_iso) for marking a position.

        Local read only — never a broker call. Returns (None, None) when unavailable.
        """
        if self._market is None:
            return None, None
        try:
            bars = self._market.get(symbol, timeframe, 1)
        except Exception:
            return None, None
        if not bars:
            return None, None
        last = bars[-1]
        ts = last.get("time")
        ts_iso = (
            datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            if isinstance(ts, (int, float)) else None
        )
        return float(last["close"]), ts_iso
```

> Ensure `datetime` and `timezone` are imported at the top of `supervisor.py` (they are already used by `_cycle_dict`/`lifecycle`). If `self._market` is stored under a different attribute name, use that name — grep `self._market` in the file to confirm.

In `status()`'s **running branch**, after computing `pos = s["view"].load_position()` and building the strategy dict's `position` via `_pos_dict(pos)`, annotate it:

```python
                pos_dict = _pos_dict(pos)
                if pos_dict is not None:
                    tf = getattr(s["profile"], "timeframe", "15m")
                    mark_price, mark_ts = self._mark(pos.symbol, tf)
                    pos_dict["mark_price"] = mark_price
                    pos_dict["mark_ts"] = mark_ts
                    pos_dict["unrealized"] = (
                        (mark_price - pos.entry_price) * pos.qty
                        if mark_price is not None else None
                    )
```

Then use `pos_dict` (not `_pos_dict(pos)`) when appending to `strategies` in the running branch. In the **not-running branch**, `position` is `None`, so no annotation is needed.

> Confirm the profile timeframe attribute name (`s["profile"].timeframe`) by grepping the profile object; if it is a dict or uses a different attribute, adapt the `getattr` accordingly.

- [x] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_supervisor_managed.py -q`
Expected: PASS.

- [x] **Step 5: Full backend gate + commit**

```bash
.venv/bin/python -m pytest -q
ruff check src/
git add src/swingbot/supervisor.py tests/test_supervisor_managed.py
git commit -m "feat(api): annotate open positions with unrealized P&L and source timestamp"
```
Expected: full suite green (≥ the prior 551 passed, 6 skipped).

---

## Task 4: Frontend API client + Dashboard polling for trading health

**Files:**
- Modify: `frontend/src/api.js`
- Modify: `frontend/src/App.jsx`

- [x] **Step 1: Add `tradingHealth` to the API client**

In `frontend/src/api.js`, inside the `api` object (next to `metrics:`), add:

```js
  tradingHealth: () => req('GET', '/api/health/trading'),
```

- [x] **Step 2: Poll trading health in App and pass to Dashboard**

In `frontend/src/App.jsx`:

Add state near the other `useState` calls:

```js
  const [health, setHealth] = useState(null)
```

In `refresh`, after `setMetrics(...)`, add the trading-health fetch (tolerant — never breaks the dashboard):

```js
      try { setHealth(await api.tradingHealth()) } catch { /* keep last */ }
```

In the `slow` interval body, after the journal/metrics line, add:

```js
      try { setHealth(await api.tradingHealth()) } catch {}
```

Pass `health` into the Dashboard render:

```js
        <Dashboard state={state} trades={trades} metrics={metrics} health={health} onChange={refresh} />
```

- [x] **Step 3: Build to verify it compiles**

Run: `cd frontend && npm run build`
Expected: build succeeds (no syntax/import errors).

- [x] **Step 4: Commit**

```bash
git add frontend/src/api.js frontend/src/App.jsx
git commit -m "feat(ui): poll /api/health/trading and thread it to the dashboard"
```

---

## Task 5: LifecycleBanner (desired vs actual + startup error)

**Files:**
- Create: `frontend/src/components/LifecycleBanner.jsx`
- Modify: `frontend/src/pages/Dashboard.jsx`

- [x] **Step 1: Create the component**

`frontend/src/components/LifecycleBanner.jsx`:

```jsx
import Hint from './Hint.jsx'

// Truthful desired-vs-actual lifecycle, from /api/health/trading.
export default function LifecycleBanner({ health }) {
  const lc = health?.lifecycle
  if (!lc) return null
  const desired = lc.running_desired
  const actual = lc.running_actual
  const statusLabel = { active: 'ACTIVE', inactive: 'STOPPED', unhealthy: 'UNHEALTHY' }[health.status] || '—'
  const statusColor = health.status === 'active' ? 'var(--green)'
    : health.status === 'inactive' ? 'var(--muted)' : 'var(--red)'
  const desiredText = desired === true ? 'yes' : desired === false ? 'no' : 'unknown'
  return (
    <div className="panel full">
      <h3>Bot lifecycle
        <Hint text="Desired = whether you asked the bot to run (survives restarts). Actual = whether the loop thread is really alive right now. They should match; a mismatch means a failed start or crash." />
        <span className="chip" style={{ marginLeft: 8, color: statusColor }}>{statusLabel}</span>
      </h3>
      <div className="row"><span>Desired running</span><span>{desiredText}</span></div>
      <div className="row"><span>Actually running</span>
        <span className={actual ? 'pos' : 'neg'}>{actual ? 'yes' : 'no'}</span></div>
      <div className="row"><span>Mode</span><span>{(lc.mode || 'paper').toUpperCase()}</span></div>
      {lc.paused && <div className="row"><span>Paused</span><span className="neg">yes</span></div>}
      {lc.halted && <div className="row"><span>Halted (kill switch)</span><span className="neg">yes</span></div>}
      {lc.running_desired_error && (
        <div className="err">Desire unreadable: {lc.running_desired_error}</div>)}
      {lc.startup_error && (
        <div className="err">Startup error: {lc.startup_error}</div>)}
    </div>
  )
}
```

- [x] **Step 2: Render it at the top of the Dashboard**

In `frontend/src/pages/Dashboard.jsx`, add the import and render it first. Update the signature to accept `health`:

```jsx
import LifecycleBanner from '../components/LifecycleBanner.jsx'
// ...existing imports...

export default function Dashboard({ state, trades, metrics, health, onChange }){
  const strategies = state?.strategies || []
  const mode = state?.portfolio?.mode
  return (
    <div className="wrap">
      <LifecycleBanner health={health} />
      <PositionGrid strategies={strategies} />
      {/* ...rest unchanged for now (StrategyCard / MetricsPanel / JournalTable)... */}
```

- [x] **Step 3: Build**

Run: `cd frontend && npm run build`
Expected: success.

- [x] **Step 4: Commit**

```bash
git add frontend/src/components/LifecycleBanner.jsx frontend/src/pages/Dashboard.jsx
git commit -m "feat(ui): lifecycle banner showing desired vs actual state and startup error"
```

---

## Task 6: StrategyCard — labels, probe state, last decision, unrealized P&L, markers

**Files:**
- Modify: `frontend/src/components/StrategyCard.jsx`
- Modify: `frontend/src/pages/Dashboard.jsx` (pass `health` to each card)

- [x] **Step 1: Pass per-strategy decisions into each card**

In `frontend/src/pages/Dashboard.jsx`, where strategies are mapped, pass the decision for that strategy from trading health:

```jsx
      {strategies.map(s => (
        <StrategyCard key={s.symbol || s.name} strategy={s} mode={mode}
          decision={health?.last_decisions_by_strategy?.[s.name]} onChange={onChange} />
      ))}
```

- [x] **Step 2: Rebuild StrategyCard**

Replace `frontend/src/components/StrategyCard.jsx` with:

```jsx
import { useEffect, useState } from 'react'
import { api } from '../api.js'
import ChartPanel from './ChartPanel.jsx'
import SignalPanel from './SignalPanel.jsx'
import PositionPanel from './PositionPanel.jsx'
import Hint from './Hint.jsx'

const fmtTs = (iso) => iso ? new Date(iso).toLocaleString() : '—'

export default function StrategyCard({ strategy, mode, decision, onChange }){
  const [err, setErr] = useState('')
  const [trades, setTrades] = useState([])
  const s = strategy || {}

  // Per-strategy durable entry/exit markers (the chart renders these arrows).
  useEffect(() => {
    let live = true
    api.journal(s.name).then(t => { if (live) setTrades(t || []) }).catch(() => {})
    return () => { live = false }
  }, [s.name])

  const run = async (fn, confirmMsg) => {
    if (confirmMsg && !window.confirm(confirmMsg)) return
    setErr('')
    try { await fn(); onChange?.() } catch (e) { setErr(e.message) }
  }
  const paperOnly = mode === 'live' && !s.live_eligible
  const isProbe = s.kind === 'probe'
  const pos = s.position
  const unreal = pos?.unrealized
  return (
    <div className="panel full strategy-card">
      <h3>{s.label || s.name} — {s.symbol}
        <Hint text="One armed strategy trading one symbol. Its signal, position, and controls are scoped to this card." />
        {isProbe
          ? <span className="chip" title="Deterministic proof-of-life probe, not a trading strategy">probe</span>
          : <span className="chip" title="Managed/honest trading strategy">strategy</span>}
        {isProbe && s.probe_complete != null && (
          <span className={`chip ${s.probe_complete ? '' : 'warn'}`}
            title="Whether the one-shot probe has fired and recorded its durable completion marker">
            {s.probe_complete ? 'probe complete' : 'probe pending'}</span>)}
        {paperOnly && <span className="chip warn" title="Armed but not live-eligible — manages open trades but opens none in LIVE mode">paper-only</span>}
      </h3>
      {err && <div className="err">{err}</div>}

      <div className="row"><span>Last decision
        <Hint text="The terminal decision code from the most recent completed strategy cycle, with the human reason and the bar timestamp it was based on." /></span>
        <span>{decision ? `${decision.decision_code}` : '—'}</span></div>
      {decision && (
        <div className="row"><span className="muted">{decision.decision_reason}</span>
          <span className="muted">bar {fmtTs(decision.bar_ts)}</span></div>)}

      {pos && (
        <div className="row"><span>Unrealized P&amp;L
          <Hint text="Mark-to-market gain/loss on the open position: (mark price − entry) × qty, using the latest local close. Source timestamp shown alongside." /></span>
          <span className={unreal == null ? '' : (unreal >= 0 ? 'pos' : 'neg')}>
            {unreal == null ? '—' : unreal.toFixed(2)}
            {pos.mark_price != null && <span className="muted"> @ {pos.mark_price} · {fmtTs(pos.mark_ts)}</span>}
          </span></div>)}

      <ChartPanel symbol={s.symbol} mini position={pos} trades={trades} />
      <div className="card-cols">
        <SignalPanel signal={s.snapshot} symbol={s.symbol} />
        <PositionPanel position={pos} />
      </div>
      <div className="card-actions">
        <button className="act danger"
          onClick={() => run(() => api.flattenStrategy(s.name), `Flatten ${s.symbol} now?`)}>Flatten</button>
        <button className="act danger"
          onClick={() => run(() => api.disarm(s.name), `Disarm ${s.name}? Its open position is flattened first.`)}>Disarm</button>
      </div>
    </div>
  )
}
```

- [x] **Step 3: Build**

Run: `cd frontend && npm run build`
Expected: success.

- [x] **Step 4: Commit**

```bash
git add frontend/src/components/StrategyCard.jsx frontend/src/pages/Dashboard.jsx
git commit -m "feat(ui): strategy card shows label/kind, probe state, last decision, unrealized P&L, trade markers"
```

---

## Task 7: PendingOrders + ReliabilityPanel + realized P&L; keep usage-agent health separate

**Files:**
- Create: `frontend/src/components/PendingOrders.jsx`
- Create: `frontend/src/components/ReliabilityPanel.jsx`
- Modify: `frontend/src/components/MetricsPanel.jsx`
- Modify: `frontend/src/pages/Dashboard.jsx`

- [x] **Step 1: Create PendingOrders**

`frontend/src/components/PendingOrders.jsx`:

```jsx
import Hint from './Hint.jsx'

const fmtTs = (iso) => iso ? new Date(iso).toLocaleString() : '—'

// Broker-submitted orders awaiting fill (from /api/state pending_orders).
export default function PendingOrders({ orders = [] }) {
  if (!orders.length) return null
  return (
    <div className="panel full">
      <h3>Pending orders <span className="chip">{orders.length}</span>
        <Hint text="Orders that have been sent to the broker but not yet confirmed filled. They survive restarts and are reconciled against the broker before any position is created." />
      </h3>
      <table className="tbl">
        <thead><tr><th>Strategy</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Submitted</th><th>Client order id</th></tr></thead>
        <tbody>
          {orders.map(o => (
            <tr key={o.client_order_id}>
              <td>{o.strategy}</td><td>{o.symbol}</td><td>{o.side}</td>
              <td>{o.requested_qty}</td><td>{fmtTs(o.submitted_at)}</td><td>{o.client_order_id}</td>
            </tr>))}
        </tbody>
      </table>
    </div>
  )
}
```

> If `table.tbl` / `JournalTable`'s table classes differ, mirror whatever `frontend/src/components/JournalTable.jsx` uses so styling is consistent.

- [x] **Step 2: Create ReliabilityPanel**

`frontend/src/components/ReliabilityPanel.jsx`:

```jsx
import Hint from './Hint.jsx'

const fmtTs = (iso) => iso ? new Date(iso).toLocaleString() : '—'
const pct = (x) => (typeof x === 'number' ? `${(x * 100).toFixed(1)}%` : '—')

// Trading reliability with sample counts and window — never a bare percentage.
export default function ReliabilityPanel({ health }) {
  const r = health?.reliability
  if (!r) return null
  const stages = r.stages || r.per_stage || {}
  return (
    <div className="panel full">
      <h3>Trading reliability
        <Hint text="Per-stage success rate over the latest completed cycles. Each rate is shown with the ok/total sample counts and the time window — never a bare percentage." />
      </h3>
      <div className="row"><span>Window</span>
        <span className="muted">{fmtTs(r.window_start)} → {fmtTs(r.window_end)}</span></div>
      {typeof r.sample_count === 'number' && (
        <div className="row"><span>Cycles in window</span><span>{r.sample_count}</span></div>)}
      {typeof r.cycle_completion === 'number' && (
        <div className="row"><span>Cycle completion</span><span>{pct(r.cycle_completion)}</span></div>)}
      {typeof r.critical_floor === 'number' && (
        <div className="row"><span>Critical-stage floor</span><span>{pct(r.critical_floor)}</span></div>)}
      {Object.entries(stages).map(([name, st]) => (
        <div className="row" key={name}><span>{name}</span>
          <span>{pct(st.reliability ?? st.rate)}
            <span className="muted"> ({st.ok ?? 0}/{(st.ok ?? 0) + (st.failed ?? 0)})</span></span>
        </div>))}
    </div>
  )
}
```

> The exact shape of `trading_health().reliability` is produced by `_telemetry.reliability(limit=200)`. Before finishing, **read that method** (`grep -n "def reliability" src/swingbot/telemetry.py`) and align the field names (`window_start`/`window_end`, per-stage `ok`/`failed`/`reliability`, `cycle_completion`, `critical_floor`, `sample_count`) with what it actually returns. Keep the "counts + window, never a bare percentage" contract (spec §3.3).

- [x] **Step 3: Realized P&L total + source timestamp in MetricsPanel**

In `frontend/src/components/MetricsPanel.jsx`, change the signature to also accept `trades`, compute the realized total and its source timestamp, and add a row. Update the export line and add the computation + row:

```jsx
export default function MetricsPanel({ metrics, trades = [] }){
  const m = metrics || {}
  const f = (x,d=2)=> (typeof x==='number' ? x.toFixed(d) : '—')
  const realized = trades.reduce((sum, t) => sum + (t.pnl || 0), 0)
  const lastExit = trades.reduce((mx, t) => (t.exit_ts && t.exit_ts > mx ? t.exit_ts : mx), '')
  const fmtTs = (iso) => iso ? new Date(iso).toLocaleString() : '—'
  return (
    <div className="panel full">
      <h3>Metrics
        <Hint text="Performance of all closed trades so far. With only a handful of trades these numbers are noisy — judge the strategy over many trades, not a few." />
      </h3>
      <div className="row"><span>Realized P&amp;L
        <Hint text="Sum of profit/loss across every closed trade, in account currency. The timestamp is the most recent exit that contributed to it." /></span>
        <span className={realized >= 0 ? 'pos' : 'neg'}>{f(realized,2)}
          <span className="muted"> · as of {fmtTs(lastExit)}</span></span></div>
      {/* ...existing Expectancy / Win rate / Profit factor / Max drawdown / Trades rows unchanged... */}
```

Keep all existing rows below the new Realized P&L row.

- [x] **Step 4: Compose the new panels into the Dashboard**

In `frontend/src/pages/Dashboard.jsx`, render `PendingOrders` and `ReliabilityPanel`, and pass `trades` to `MetricsPanel`. Final structure:

```jsx
import StrategyCard from '../components/StrategyCard.jsx'
import JournalTable from '../components/JournalTable.jsx'
import MetricsPanel from '../components/MetricsPanel.jsx'
import PositionGrid from '../components/PositionGrid.jsx'
import LifecycleBanner from '../components/LifecycleBanner.jsx'
import PendingOrders from '../components/PendingOrders.jsx'
import ReliabilityPanel from '../components/ReliabilityPanel.jsx'

export default function Dashboard({ state, trades, metrics, health, onChange }){
  const strategies = state?.strategies || []
  const mode = state?.portfolio?.mode
  return (
    <div className="wrap">
      <LifecycleBanner health={health} />
      <PositionGrid strategies={strategies} />
      <PendingOrders orders={state?.pending_orders || []} />
      {strategies.length === 0 && (
        <div className="panel full"><h3>No strategies armed</h3>
          <div>Arm one or more strategies on the <b>Strategy</b> tab to start trading them concurrently.</div>
        </div>
      )}
      {strategies.map(s => (
        <StrategyCard key={s.symbol || s.name} strategy={s} mode={mode}
          decision={health?.last_decisions_by_strategy?.[s.name]} onChange={onChange} />
      ))}
      <ReliabilityPanel health={health} />
      <MetricsPanel metrics={metrics} trades={trades} />
      <JournalTable trades={trades} />
    </div>
  )
}
```

- [x] **Step 5: Build**

Run: `cd frontend && npm run build`
Expected: success.

- [x] **Step 6: Verify usage-agent health stays separate**

Confirm `frontend/src/pages/Health.jsx` is unchanged and still renders the usage-agent runs; the Dashboard must NOT import or render usage-agent data. (Read-only check — no edit. Run `grep -n "agentLatest\|agentRuns" frontend/src/pages/Dashboard.jsx` and expect no matches.)

- [x] **Step 7: Commit**

```bash
git add frontend/src/components/PendingOrders.jsx frontend/src/components/ReliabilityPanel.jsx frontend/src/components/MetricsPanel.jsx frontend/src/pages/Dashboard.jsx
git commit -m "feat(ui): pending orders, trading reliability, and realized P&L on the dashboard"
```

---

## Task 8: Regression gate + Docker rebuild + ROADMAP_STATUS update

**Files:**
- Modify: `docs/ROADMAP_STATUS.md`

- [x] **Step 1: Full gate**

```bash
.venv/bin/python -m pytest -q
ruff check src/
cd frontend && npm run build && cd ..
```
Expected: pytest green (≥ 551 + the new tests passed), ruff clean, build OK. If any fails, fix before continuing — do not proceed to the doc update on red.

- [x] **Step 2: Rebuild + restart the container (standing policy)**

```bash
docker compose build swingbot && docker compose up -d swingbot
```

- [x] **Step 3: Live smoke check**

```bash
curl -s localhost:8000/api/state | python3 -m json.tool | head -40
curl -s localhost:8000/api/health/trading | python3 -m json.tool | head -40
```
Expected: `/api/state` strategies carry `kind`/`label`/`probe_complete` and a top-level `pending_orders`; `/api/health/trading` returns `status`, `lifecycle` (with `running_desired`/`running_actual`/`startup_error`), `last_decisions_by_strategy`, and `reliability`. Note the actual values in the commit/roadmap update.

- [x] **Step 4: Update ROADMAP_STATUS.md**

In `docs/ROADMAP_STATUS.md`, update the **NEXT ACTION** block: mark Phase 5 DONE (list the commits and the gate result), and set the next anchor to **Phase 6 (live acceptance)** per spec §Phase 6 — run acceptance in paper mode: back up the data dir, start from a managed-canvas/probe config, rebuild without pressing Start, verify desired/actual + fresh closed bars + cycle records + decision reasons, (if probe enabled) verify an Alpaca-confirmed fill + durable position + chart marker + persisted completion marker, restart and verify no duplicate probe/order, then simulate credential/network failure and verify the UI stays available without clearing positions or duplicating orders. Bump **Last updated** to the current date.

- [x] **Step 5: Commit + push**

```bash
git add docs/ROADMAP_STATUS.md
git commit -m "docs: Phase 5 dashboard rebuild done; set Phase 6 (live acceptance) anchor"
git push origin master
```

---

## Self-Review (completed by plan author)

**Spec coverage** — every Phase 5 "show" bullet maps to a task:
- desired vs actual + startup error → Task 4 (data) + Task 5 (LifecycleBanner). ✓
- broker-confirmed positions + pending orders → existing `status()` positions + Task 2 (`pending_orders`) + Task 7 (PendingOrders) + PositionGrid (unchanged, already shows positions). ✓
- last cycle/bar timestamp + last decision code/reason → Task 4 (data) + Task 6 (per-card row). ✓
- realized + unrealized P&L with source timestamps → Task 3 (unrealized backend) + Task 6 (unrealized UI) + Task 7 (realized UI). ✓
- durable entry/exit markers → Task 6 (per-strategy `api.journal(name)` → `ChartPanel trades`). ✓
- trading reliability with counts + window → Task 7 (ReliabilityPanel, "never a bare percentage"). ✓
- usage-agent health as a separate section → Task 7 Step 6 (Health.jsx untouched; verified absent from Dashboard). ✓
- managed labels + probe state → Task 1 + Task 2 + Task 6. ✓
- "Do not remove operational controls" → ControlBar and card Flatten/Disarm retained (Task 6 keeps actions; App keeps ControlBar). ✓
- "Hide strategy creation only per managed-canvas contract" → out of scope per Phase 4 decision; no change. ✓ (documented in preamble)

**Type/name consistency:** `kind`/`label`/`probe_complete` defined in Task 1/2 and consumed in Task 6; `pending_orders` defined Task 2, consumed Task 7; `mark_price`/`mark_ts`/`unrealized` defined Task 3, consumed Task 6; `tradingHealth()` defined Task 4, consumed Tasks 5/6/7; `health.last_decisions_by_strategy`/`health.reliability`/`health.lifecycle` are the documented `trading_health()` keys.

**Open verification flagged inline** (the implementer must confirm against the real code, not guess): exact import paths for `PendingOrder`/`OrderSide`/`Regime` (Task 2), bar dict keys + market attribute name + profile timeframe accessor (Task 3), and the precise `reliability` field names from `telemetry.py` (Task 7). These are explicit "confirm with grep" notes, not placeholders.

## Implementation notes from Codex execution

- Baseline after sync: `.venv/bin/python -m pytest -q` passed with `551 passed, 6 skipped`; `.venv/bin/ruff check src/` passed; `cd frontend && npm run build` passed. Bare `ruff` is not on PATH in this environment, so lint commands are executed as `.venv/bin/ruff check src/`.
- Confirmed `PendingOrder`, `OrderSide`, and `Regime` all live in `swingbot.types`.
- Confirmed `PortfolioSupervisor` stores local market data as `self.market` (not `self._market`).
- Adapted Task 3's no-market test: building with no market raises by design, so the test builds with a market, clears `sup.market`, and verifies status marks are null without crashing.
- Confirmed `TelemetryStore.reliability()` returns `stages.*.ratio`, `completed_cycles`, `successful_cycles`, `cycle_completion_ratio`, `critical_stage_floor`, `window_started_at`, and `window_completed_at`.
- Task 6 requires a small `ChartPanel.jsx` adjustment even though it was not listed in the file table: existing mini charts default `markers: false` and have no visible settings button, so passing `trades` alone would not show durable entry/exit markers. The implementation adds an explicit mini-marker prop and uses it only from `StrategyCard`.
- Final gate: `.venv/bin/python -m pytest -q` passed with `556 passed, 6 skipped`; `.venv/bin/ruff check src/` passed; `cd frontend && npm run build` passed.
- Docker image rebuild succeeded. Default `docker compose up -d swingbot` failed because this host's daemon lacks the compose file's hardcoded `runtime: nvidia`; live smoke was completed by starting the same service/image with a temporary local compose override `runtime: runc`.
