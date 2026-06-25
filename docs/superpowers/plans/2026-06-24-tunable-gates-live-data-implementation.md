# Tunable Gates, Researched Strategies, Live Data & Faster UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every entry gate visible and tunable per coin from the UI (no rebuild), unblock live trading by flipping the regime gate off, re-introduce the researched TA signals as both gates and standalone (badged demo) strategies, add a cheap ~3s live-price feed, and kill the slow initial page load.

**Architecture:** Backend reuses the existing `ProfileStore → controller.reload()` hot-reload path (same as `PUT /api/portfolio/settings`) for a new `PUT /api/strategies/{name}/profile`. Gates are an additive hard-veto layer inside the existing `Orchestrator._maybe_enter` pipeline driven by two reserved per-signal keys (`gate`, `min_score`); no new engine. Live price wraps the existing `MarketProvider.get_latest_prices` behind a small TTL cache. The frontend adds a Gates & Parameters panel on Coin Detail, a researched-preset option in the Add dialog, a 3s `useLivePrice` poller, and `localStorage` stale-while-revalidate hydration + skeletons.

**Tech Stack:** Python 3 / FastAPI / Pydantic / SQLite (`ProfileStore`); pytest; React 18 + Vite + Tailwind v3 + hand-authored shadcn-style primitives (Radix Dialog); `react-router-dom` v6; Vitest.

## Global Constraints

- Python venv is **`.venv/bin/python`** (plain `python`/`pytest` are not on PATH). Lint with **`.venv/bin/ruff check src/`**.
- Frontend gate: **`cd frontend && npm run build`** and **`npm run test`** (Vitest; uses `--passWithNoTests`).
- Per the standing **Docker rebuild rule**: every backend code change requires `docker compose build swingbot && docker compose up -d swingbot` before live-verify. This is pre-authorized; do not ask. It interrupts the live paper bot — that is acceptable here.
- Profile **patch whitelist** (server-side, exact set): `entry_threshold`, `allowed_regimes`, `regime_ma_period`, `signals`, `stop_atr_mult`, `take_profit_atr_mult`, `tp_pct`, `sl_pct`, `bracket_mode`, `max_hold_bars`, `risk_per_trade`, `max_position_frac`, `daily_loss_limit_pct`, `max_consecutive_losses`, `max_concurrent`, `cooldown_minutes`.
- Reserved per-signal gate keys (exact): `gate` (bool, default false), `min_score` (float, default 0.0). `build_signals` MUST strip these before `cls(**params)`.
- New decision code (exact value): `GATE_BLOCKED`. Final decision pipeline order: `BROKER_POSITION_EXISTS → PAUSED/HALTED → RISK_BLOCKED → REGIME_BLOCKED → GATE_BLOCKED → SIGNAL_BELOW_THRESHOLD → ATR_INVALID → SIZE_ZERO → PORTFOLIO_BLOCKED → ORDER_SUBMITTED`.
- Regime toggle is stored as `allowed_regimes`: OFF = `["uptrend","neutral","downtrend"]`, ON = `["uptrend","neutral"]`. No new field.
- The four live armed kronos strategies are named `kronos-btc-usd`, `kronos-eth-usd`, `kronos-sol-usd`, `kronos-xrp-usd` (`kronos-<symbol with / → -, lowercased>`).
- Researched standalone presets ship behind a **"backtested negative-edge — demo only"** badge; never claim profitability.
- DRY, YAGNI, TDD, frequent commits. Each task is one shippable, live-verifiable deliverable.

---

## File Structure

**Backend (Python):**
- `src/swingbot/web.py` — MODIFY: add `GET`/`PUT /api/strategies/{name}/profile`, `GET`/`POST /api/strategies/researched`, `GET /api/price`; add `kind`/`label` to `/api/strategies`. (Routes only; logic delegates.)
- `src/swingbot/confluence.py` — MODIFY: `build_signals` strips reserved keys.
- `src/swingbot/types.py` — MODIFY: add `DecisionCode.GATE_BLOCKED`.
- `src/swingbot/orchestrator.py` — MODIFY: add `_check_gates` between regime and confluence-threshold checks.
- `src/swingbot/profile.py` — MODIFY: add `kind`/`label` fields to `StrategyProfile`.
- `src/swingbot/presets.py` — MODIFY: add four researched preset builders + a dispatch map + metadata list.
- `src/swingbot/supervisor.py` — MODIFY: surface `kind`/`label` in `status()` strategy entries.
- `src/swingbot/price_cache.py` — CREATE: `PriceCache` (per-symbol TTL, stale fallback, thread-safe).

**Frontend (React):**
- `frontend/src/api.js` — MODIFY: add `getStrategyProfile`, `updateStrategyProfile`, `listResearched`, `addResearched`, `price`.
- `frontend/src/lib/derive.js` — MODIFY: add `buildProfilePatch`, `livePriceFor` helpers.
- `frontend/src/lib/cache.js` — CREATE: `readCache`/`writeCache` (localStorage SWR).
- `frontend/src/components/ui/switch.jsx` — CREATE: minimal button-based toggle (no new dep).
- `frontend/src/components/ui/skeleton.jsx` — CREATE: placeholder shimmer.
- `frontend/src/components/useLivePrice.js` — CREATE: 3s price poller hook.
- `frontend/src/components/detail/GatesParametersPanel.jsx` — CREATE: the tuning panel.
- `frontend/src/pages/CoinDetail.jsx` — MODIFY: mount the panel; hydrate from cache; live-price header.
- `frontend/src/pages/MissionControl.jsx` — MODIFY: cache hydration; pass live prices into the grid.
- `frontend/src/components/AddCoinDialog.jsx` — MODIFY: researched-preset section (badged).
- `frontend/src/components/CoinsGrid.jsx` / `CoinCard.jsx` — MODIFY: pass + render live price and researched badge.
- `frontend/src/components/StatusStrip.jsx` / `LiveJournal.jsx` — MODIFY: skeleton when no data.

**Tests:**
- `tests/test_web_strategy_profile.py` — CREATE (Phase 1).
- `tests/test_confluence.py` — MODIFY (Phase 2, reserved-key strip).
- `tests/test_types_decisions.py` — MODIFY (Phase 2, contract).
- `tests/test_orchestrator_decisions.py` — MODIFY (Phase 2, gate path).
- `tests/test_profile.py` — MODIFY (Phase 3, kind/label).
- `tests/test_presets.py` — MODIFY (Phase 3, researched builders).
- `tests/test_web_strategy.py` — MODIFY (Phase 3, kind/label in listing + researched endpoints).
- `tests/test_price_cache.py` — CREATE (Phase 4).
- `tests/test_web_price.py` — CREATE (Phase 4).
- `frontend/src/lib/derive.test.js` — MODIFY (Phase 3/4, helpers).
- `frontend/src/lib/cache.test.js` — CREATE (Phase 5).

---

# Phase 1 — Tuning backend + regime unblock

Delivers success criteria 1–2: a param changes live with no rebuild, and the regime flip produces a trade.

### Task 1.1: `GET`/`PUT /api/strategies/{name}/profile`

**Files:**
- Modify: `src/swingbot/web.py` (add the whitelist constant + body model near the other `BaseModel`s ~line 24–86; add the two routes in the `# ---- strategies / arming ----` block after `live_eligible`, ~line 205)
- Test: `tests/test_web_strategy_profile.py`

**Interfaces:**
- Consumes: `profiles.get(name) -> dict|None`, `profiles.save(name, dict)` (raises `ValueError` on invalid), `controller.reload()`.
- Produces: `PUT /api/strategies/{name}/profile` body `{"patch": {...}}` → `200 {"name","profile"}`; `404` unknown strategy; `400` non-tunable key or invalid value. `GET /api/strategies/{name}/profile` → `{"name","profile"}` or `404`.

- [x] **Step 1: Write the failing test**

Create `tests/test_web_strategy_profile.py`:

```python
from fastapi.testclient import TestClient

from swingbot.kronos_preset import kronos_bracket_profile
from swingbot.profiles import ProfileStore
from swingbot.web import create_app


class FakeController:
    def __init__(self):
        self.reloaded = 0
    def status(self): return {}
    def reload(self): self.reloaded += 1


def _client(tmp_path, token="tok"):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    profiles.save("kronos-btc-usd", kronos_bracket_profile("BTC/USD"))
    profiles.arm("kronos-btc-usd")
    ctl = FakeController()
    app = create_app(controller=ctl, profiles=profiles, creds=None, token=token)
    return TestClient(app), profiles, ctl


def test_get_strategy_profile_returns_full_profile(tmp_path):
    c, _, _ = _client(tmp_path)
    r = c.get("/api/strategies/kronos-btc-usd/profile")
    assert r.status_code == 200
    assert r.json()["profile"]["symbol"] == "BTC/USD"
    assert c.get("/api/strategies/nope/profile").status_code == 404


def test_put_profile_patch_merges_validates_and_reloads(tmp_path):
    c, profiles, ctl = _client(tmp_path)
    h = {"X-Token": "tok"}
    r = c.put("/api/strategies/kronos-btc-usd/profile",
              json={"patch": {"entry_threshold": 0.2}}, headers=h)
    assert r.status_code == 200
    assert r.json()["profile"]["entry_threshold"] == 0.2
    assert profiles.get("kronos-btc-usd")["entry_threshold"] == 0.2
    assert ctl.reloaded == 1


def test_put_regime_off_persists_all_three_regimes(tmp_path):
    c, profiles, _ = _client(tmp_path)
    h = {"X-Token": "tok"}
    r = c.put("/api/strategies/kronos-btc-usd/profile",
              json={"patch": {"allowed_regimes": ["uptrend", "neutral", "downtrend"]}},
              headers=h)
    assert r.status_code == 200
    assert profiles.get("kronos-btc-usd")["allowed_regimes"] == \
        ["uptrend", "neutral", "downtrend"]


def test_put_profile_rejects_unknown_key_404_and_400(tmp_path):
    c, _, _ = _client(tmp_path)
    h = {"X-Token": "tok"}
    assert c.put("/api/strategies/nope/profile",
                 json={"patch": {"entry_threshold": 0.2}}, headers=h).status_code == 404
    assert c.put("/api/strategies/kronos-btc-usd/profile",
                 json={"patch": {"poll_seconds": 5}}, headers=h).status_code == 400
    assert c.put("/api/strategies/kronos-btc-usd/profile",
                 json={"patch": {"allowed_regimes": ["sideways"]}}, headers=h).status_code == 400


def test_put_profile_requires_token(tmp_path):
    c, _, _ = _client(tmp_path)
    assert c.put("/api/strategies/kronos-btc-usd/profile",
                 json={"patch": {"entry_threshold": 0.2}}).status_code == 401
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_web_strategy_profile.py -q`
Expected: FAIL (404 for the new routes — they don't exist yet).

- [x] **Step 3: Write the implementation**

In `src/swingbot/web.py`, add near the other module-level `BaseModel`s (after `class WatchlistBody` ~line 69):

```python
class ProfilePatchBody(BaseModel):
    patch: dict


_PROFILE_PATCH_KEYS = {
    "entry_threshold", "allowed_regimes", "regime_ma_period", "signals",
    "stop_atr_mult", "take_profit_atr_mult", "tp_pct", "sl_pct", "bracket_mode",
    "max_hold_bars", "risk_per_trade", "max_position_frac",
    "daily_loss_limit_pct", "max_consecutive_losses", "max_concurrent",
    "cooldown_minutes",
}
```

In the `# ---- strategies / arming ----` block, after the `live_eligible` route (~line 205), add:

```python
    @app.get("/api/strategies/{name}/profile")
    def get_strategy_profile(name: str):
        p = profiles.get(name)
        if p is None:
            raise HTTPException(status_code=404, detail=f"no strategy {name!r}")
        return {"name": name, "profile": p}

    @app.put("/api/strategies/{name}/profile")
    def update_strategy_profile(name: str, body: ProfilePatchBody,
                                _=Depends(require_token)):
        cur = profiles.get(name)
        if cur is None:
            raise HTTPException(status_code=404, detail=f"no strategy {name!r}")
        bad = set(body.patch) - _PROFILE_PATCH_KEYS
        if bad:
            raise HTTPException(status_code=400, detail=f"non-tunable keys: {sorted(bad)}")
        merged = {**cur, **body.patch}
        try:
            profiles.save(name, merged)          # validates via StrategyProfile.from_dict
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        controller.reload()
        return {"name": name, "profile": merged}
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_web_strategy_profile.py -q`
Expected: PASS (6 tests).

- [x] **Step 5: Lint + commit**

```bash
.venv/bin/ruff check src/
git add src/swingbot/web.py tests/test_web_strategy_profile.py
git commit -m "feat(web): PUT/GET /api/strategies/{name}/profile with whitelist + hot-reload"
```

### Task 1.2: Frontend client methods for profile tuning

**Files:**
- Modify: `frontend/src/api.js` (in the `// --- portfolio / arming ---` group, after `setLiveEligible`)

**Interfaces:**
- Produces: `api.getStrategyProfile(name) -> {name, profile}`; `api.updateStrategyProfile(name, patch) -> {name, profile}`.

- [x] **Step 1: Add the client methods**

In `frontend/src/api.js`, after the `setLiveEligible` line (~line 56), add:

```javascript
  getStrategyProfile: (name) =>
    req('GET', `/api/strategies/${encodeURIComponent(name)}/profile`),
  updateStrategyProfile: (name, patch) =>
    req('PUT', `/api/strategies/${encodeURIComponent(name)}/profile`, { patch }),
```

- [x] **Step 2: Verify the build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [x] **Step 3: Commit**

```bash
git add frontend/src/api.js
git commit -m "feat(api): client methods for strategy-profile get/update"
```

### Task 1.3: Live regime unblock (ops verification)

**Files:** none (operational). This is the Phase 1 live-verify deliverable.

- [ ] **Step 1: Rebuild + restart the container**

```bash
cd /home/redji/crypto-swing-bot
docker compose build swingbot && docker compose up -d swingbot
```

- [ ] **Step 2: Flip the regime gate OFF for the four armed kronos strategies**

```bash
for n in kronos-btc-usd kronos-eth-usd kronos-sol-usd kronos-xrp-usd; do
  curl -s -X PUT "http://localhost:8000/api/strategies/$n/profile" \
    -H 'Content-Type: application/json' \
    -d '{"patch":{"allowed_regimes":["uptrend","neutral","downtrend"]}}' | head -c 200; echo
done
```
Expected: each returns `200` JSON with `"allowed_regimes":["uptrend","neutral","downtrend"]`. (If a name is absent, list live names with `curl -s localhost:8000/api/strategies | python3 -m json.tool` and repeat for the real names.)

- [ ] **Step 3: Confirm the unblock (criterion 1)**

Wait for 1–2 closed 15m bars, then:
```bash
curl -s "http://localhost:8000/api/decisions?limit=20" | python3 -m json.tool | grep -E 'decision_code' | sort | uniq -c
```
Expected: at least one non-`REGIME_BLOCKED` outcome (`ORDER_SUBMITTED` / `ORDER_PENDING` / `ENTERED`, or `SIGNAL_BELOW_THRESHOLD` if a score dipped) — regime no longer vetoes. Record the result in `docs/ROADMAP_STATUS.md`.

---

# Phase 2 — Gate layer (toggleable per-signal hard vetoes)

Delivers success criterion 3.

### Task 2.1: `build_signals` strips reserved keys

**Files:**
- Modify: `src/swingbot/confluence.py:23-28`
- Test: `tests/test_confluence.py`

**Interfaces:**
- Produces: `build_signals(profile)` constructs each signal from `params` minus `{"gate","min_score"}`.

- [x] **Step 1: Write the failing test**

Append to `tests/test_confluence.py`:

```python
def test_build_signals_strips_reserved_gate_keys():
    from swingbot.confluence import build_signals
    from swingbot.profile import StrategyProfile
    from swingbot.signals.oversold import OversoldSignal

    profile = StrategyProfile.from_dict({
        "symbol": "BTC/USD",
        "signals": {"oversold": {"weight": 1.0, "oversold_level": 45,
                                 "gate": True, "min_score": 0.4}},
    })
    sigs = build_signals(profile)            # must not raise on gate/min_score
    assert len(sigs) == 1
    assert isinstance(sigs[0], OversoldSignal)
    assert not hasattr(sigs[0], "gate")
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_confluence.py::test_build_signals_strips_reserved_gate_keys -q`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'gate'`.

- [x] **Step 3: Write the implementation**

Replace `build_signals` in `src/swingbot/confluence.py` (lines 23-28) with:

```python
_RESERVED_SIGNAL_KEYS = {"gate", "min_score"}


def build_signals(profile: StrategyProfile) -> list[Signal]:
    signals: list[Signal] = []
    for name, params in profile.signals.items():
        cls = _REGISTRY[name]
        kwargs = {k: v for k, v in params.items() if k not in _RESERVED_SIGNAL_KEYS}
        signals.append(cls(**kwargs))
    return signals
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_confluence.py -q`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
.venv/bin/ruff check src/
git add src/swingbot/confluence.py tests/test_confluence.py
git commit -m "feat(confluence): strip reserved gate/min_score keys in build_signals"
```

### Task 2.2: Add `DecisionCode.GATE_BLOCKED`

**Files:**
- Modify: `src/swingbot/types.py:36` (insert after `REGIME_BLOCKED`)
- Test: `tests/test_types_decisions.py:14-34`

- [x] **Step 1: Update the contract test (failing)**

In `tests/test_types_decisions.py`, add `"GATE_BLOCKED",` to the expected set in `test_decision_codes_match_phase3_api_contract` (after `"REGIME_BLOCKED",`).

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_types_decisions.py::test_decision_codes_match_phase3_api_contract -q`
Expected: FAIL (set mismatch — enum lacks `GATE_BLOCKED`).

- [x] **Step 3: Add the enum member**

In `src/swingbot/types.py`, in `class DecisionCode`, add after the `REGIME_BLOCKED` line:

```python
    GATE_BLOCKED = "GATE_BLOCKED"
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_types_decisions.py -q`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
.venv/bin/ruff check src/
git add src/swingbot/types.py tests/test_types_decisions.py
git commit -m "feat(types): add DecisionCode.GATE_BLOCKED"
```

### Task 2.3: Orchestrator gate evaluation

**Files:**
- Modify: `src/swingbot/orchestrator.py` (insert gate check in `_maybe_enter` after `conf = self.engine.evaluate(ctx)` (~line 164) and before `if not conf.passed`; add `_check_gates` helper)
- Test: `tests/test_orchestrator_decisions.py`

**Interfaces:**
- Consumes: `ConfluenceResult.signals[name].score` (raw per-signal score), `self.profile.signals[name]` (reads `gate`/`min_score`).
- Produces: `DecisionResult(DecisionCode.GATE_BLOCKED, "<signal> gate not satisfied", {"signal","score","min_score"})` when a gated signal's raw score `< min_score`; otherwise `None` (pipeline continues).

- [x] **Step 1: Write the failing test**

Append to `tests/test_orchestrator_decisions.py` (it already imports `ConfluenceResult`, `RegimeResult`, `Regime`, `DecisionCode`; add `SignalResult` to that import block):

```python
def test_gate_blocks_when_raw_signal_score_below_min(tmp_path, monkeypatch):
    from swingbot.types import SignalResult
    profile = StrategyProfile.from_dict({
        "symbol": "TRX/USD", "timeframe": "15m",
        "signals": {"oversold": {"weight": 1.0, "gate": True, "min_score": 0.5}},
        "entry_threshold": 0.25, "regime_ma_period": 50,
    })
    state = StateStore(str((tmp_path / "gate")) + ".db")
    orch = Orchestrator(profile, Data(), Broker(), state,
                        RiskManager(profile, state.load_risk_state()), TradeJournal())
    monkeypatch.setattr(orch.regime, "evaluate", lambda ctx: RegimeResult(Regime.UPTREND))
    monkeypatch.setattr(orch.engine, "evaluate", lambda ctx: ConfluenceResult(
        1.0, 0.25, True, {"oversold": 0.3},
        {"oversold": SignalResult("oversold", 0.3)}))
    r = orch._maybe_enter(T0, 1000)
    assert r.code is DecisionCode.GATE_BLOCKED
    assert r.details["signal"] == "oversold"


def test_gate_satisfied_lets_entry_proceed(tmp_path, monkeypatch):
    from swingbot.types import SignalResult
    profile = StrategyProfile.from_dict({
        "symbol": "TRX/USD", "timeframe": "15m",
        "signals": {"oversold": {"weight": 1.0, "gate": True, "min_score": 0.5}},
        "entry_threshold": 0.25, "regime_ma_period": 50, "atr_period": 14,
        "stop_atr_mult": 2.0, "take_profit_atr_mult": 2.0, "risk_per_trade": 0.02,
    })
    state = StateStore(str((tmp_path / "ok")) + ".db")
    orch = Orchestrator(profile, Data(), Broker(), state,
                        RiskManager(profile, state.load_risk_state()), TradeJournal())
    monkeypatch.setattr(orch.regime, "evaluate", lambda ctx: RegimeResult(Regime.UPTREND))
    monkeypatch.setattr(orch.engine, "evaluate", lambda ctx: ConfluenceResult(
        1.0, 0.25, True, {"oversold": 0.6},
        {"oversold": SignalResult("oversold", 0.6)}))
    assert orch._maybe_enter(T0, 1000).code is DecisionCode.ORDER_SUBMITTED
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_orchestrator_decisions.py::test_gate_blocks_when_raw_signal_score_below_min -q`
Expected: FAIL (`ORDER_SUBMITTED`, not `GATE_BLOCKED` — gate not enforced yet).

- [x] **Step 3: Write the implementation**

In `src/swingbot/orchestrator.py`, in `_maybe_enter`, immediately after `conf = self.engine.evaluate(ctx)` (line 164) and before `if not conf.passed:`, insert:

```python
        gate_block = self._check_gates(conf)
        if gate_block is not None:
            return gate_block
```

Add this method to the `Orchestrator` class (e.g. right after `_maybe_enter`):

```python
    def _check_gates(self, conf) -> DecisionResult | None:
        """Hard per-signal vetoes. A signal whose profile entry has gate=True must
        have a raw score >= its min_score, else the entry is blocked. Reads the
        reserved keys from the profile (not the signal instance)."""
        for name, params in self.profile.signals.items():
            if not params.get("gate", False):
                continue
            min_score = float(params.get("min_score", 0.0))
            sig = conf.signals.get(name)
            score = sig.score if sig is not None else 0.0
            if score < min_score:
                return DecisionResult(
                    DecisionCode.GATE_BLOCKED,
                    f"{name} gate not satisfied",
                    {"signal": name, "score": score, "min_score": min_score},
                )
        return None
```

- [x] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_orchestrator_decisions.py -q`
Expected: PASS (existing + 2 new).

- [x] **Step 5: Full gate + commit + live**

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check src/
git add src/swingbot/orchestrator.py tests/test_orchestrator_decisions.py
git commit -m "feat(orchestrator): GATE_BLOCKED hard-veto layer between regime and confluence"
docker compose build swingbot && docker compose up -d swingbot
```
Live-verify (optional smoke): add a gate to one strategy and watch the feed:
```bash
curl -s -X PUT localhost:8000/api/strategies/kronos-btc-usd/profile \
  -H 'Content-Type: application/json' \
  -d '{"patch":{"signals":{"kronos_forecast":{"weight":1.0,"pred_len":4,"threshold_pct":0.0075,"gate":true,"min_score":0.99}}}}'
```
Then after a bar: `curl -s "localhost:8000/api/decisions?strategy=kronos-btc-usd&limit=5" | python3 -m json.tool` should show `GATE_BLOCKED`. Revert `min_score` to a sane value afterward.

---

# Phase 3 — Frontend Gates & Parameters panel + researched presets

Delivers Components 3b and 4.

### Task 3.1: `kind`/`label` on `StrategyProfile` and surfaced in the API

**Files:**
- Modify: `src/swingbot/profile.py:8-45` (add two fields)
- Modify: `src/swingbot/web.py:171-179` (`list_strategies` includes `kind`/`label`)
- Modify: `src/swingbot/supervisor.py` (`status()` strategy entries include `kind`/`label`, both branches ~lines 829-850)
- Test: `tests/test_profile.py`, `tests/test_web_strategy.py`

**Interfaces:**
- Produces: `StrategyProfile(kind: str = "kronos", label: str = "")`; `/api/strategies` items gain `"kind"`, `"label"`; `status()` strategy entries gain `"kind"`, `"label"`.

- [x] **Step 1: Write the failing test**

Append to `tests/test_profile.py`:

```python
def test_profile_accepts_kind_and_label():
    from swingbot.profile import StrategyProfile
    p = StrategyProfile.from_dict({
        "symbol": "BTC/USD", "signals": {}, "kind": "researched", "label": "VWAP pullback"})
    assert p.kind == "researched"
    assert p.label == "VWAP pullback"


def test_profile_kind_defaults_to_kronos():
    from swingbot.profile import StrategyProfile
    assert StrategyProfile.from_dict({"symbol": "BTC/USD", "signals": {}}).kind == "kronos"
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_profile.py::test_profile_accepts_kind_and_label -q`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'kind'`.

- [x] **Step 3: Add the fields**

In `src/swingbot/profile.py`, inside `@dataclass class StrategyProfile`, add after `htf_timeframe: str = "4h"` (line 13):

```python
    # provenance: "kronos" (default) | "researched" (badged demo) | "custom"
    kind: str = "kronos"
    label: str = ""
```

- [x] **Step 4: Surface in `list_strategies`**

In `src/swingbot/web.py`, replace the `out.append(...)` inside `list_strategies` (lines 177-178) with:

```python
            out.append({"name": name, "symbol": p.get("symbol"),
                        "kind": p.get("kind", "kronos"), "label": p.get("label", ""),
                        "armed": name in flags, "live_eligible": flags.get(name, False)})
```

- [x] **Step 5: Surface in `supervisor.status()`**

In `src/swingbot/supervisor.py`, in `status()`, add `kind`/`label` to both strategy-dict branches.
Running branch (the dict starting ~line 829 `strategies.append({"name": name, ...})`): add after `"symbol": s["profile"].symbol,`:

```python
                    "kind": getattr(s["profile"], "kind", "kronos"),
                    "label": getattr(s["profile"], "label", ""),
```

Not-running branch (~line 845): add after `"name": name, "symbol": symbol,`:

```python
                    "kind": (pdict or {}).get("kind", "kronos"),
                    "label": (pdict or {}).get("label", ""),
```

- [x] **Step 6: Update the web listing test**

In `tests/test_web_strategy.py::test_strategies_list_generic_fields`, assert the new fields exist (additive). After the existing assertions, add:

```python
    rows = c.get("/api/strategies").json()
    assert all("kind" in r and "label" in r for r in rows)
```
(If the test's `FakeProfiles.get` returns a dict without `kind`, the endpoint defaults it to `"kronos"` — no change needed there.)

- [x] **Step 7: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_profile.py tests/test_web_strategy.py -q`
Expected: PASS.

- [x] **Step 8: Commit**

```bash
.venv/bin/ruff check src/
git add src/swingbot/profile.py src/swingbot/web.py src/swingbot/supervisor.py \
        tests/test_profile.py tests/test_web_strategy.py
git commit -m "feat: kind/label on StrategyProfile, surfaced in /api/strategies and status()"
```

### Task 3.2: Researched standalone preset builders

**Files:**
- Modify: `src/swingbot/presets.py` (append builders + dispatch map + metadata)
- Test: `tests/test_presets.py`

**Interfaces:**
- Produces: `vwap_pullback_profile(symbol) -> dict`, `ema_trend_profile(symbol) -> dict`, `fvg_retrace_profile(symbol) -> dict`, `eth_rel_strength_profile(symbol) -> dict` — each a valid profile dict with `kind="researched"`. `RESEARCHED_PRESETS: dict[str, callable]` and `RESEARCHED_META: list[dict]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_presets.py`:

```python
def test_researched_preset_builders_are_valid():
    from swingbot.presets import (
        RESEARCHED_PRESETS, RESEARCHED_META,
        vwap_pullback_profile, ema_trend_profile,
        fvg_retrace_profile, eth_rel_strength_profile,
    )
    builders = {
        "vwap_pullback": (vwap_pullback_profile, {"vwap", "oversold", "ema_trend"}),
        "ema_trend": (ema_trend_profile, {"ema_trend"}),
        "fvg_retrace": (fvg_retrace_profile, {"fvg", "ema_trend"}),
        "eth_rel_strength": (eth_rel_strength_profile,
                             {"relative_strength", "ema_trend", "vwap"}),
    }
    for key, (fn, sigs) in builders.items():
        p = fn("ETH/USD")
        StrategyProfile.from_dict(p)                  # must not raise
        assert p["kind"] == "researched"
        assert p["label"]
        assert set(p["signals"]) == sigs
        assert p["symbol"] == "ETH/USD"
        assert RESEARCHED_PRESETS[key] is fn
    assert {m["preset"] for m in RESEARCHED_META} == set(builders)


def test_eth_rel_strength_uses_btc_benchmark():
    from swingbot.presets import eth_rel_strength_profile
    assert eth_rel_strength_profile("ETH/USD")["benchmark_symbol"] == "BTC/USD"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_presets.py::test_researched_preset_builders_are_valid -q`
Expected: FAIL with `ImportError` (builders not defined).

- [ ] **Step 3: Write the implementation**

Append to `src/swingbot/presets.py`:

```python
_DEMO_LABEL = "backtested negative-edge — demo only"


def vwap_pullback_profile(symbol: str = "BTC/USD") -> dict:
    return {
        "symbol": symbol, "timeframe": "15m", "kind": "researched",
        "label": f"VWAP pullback ({_DEMO_LABEL})",
        "signals": {
            "vwap": {"weight": 0.4, "window": 96, "max_dist": 0.03},
            "oversold": {"weight": 0.3, "oversold_level": 45, "period": 14},
            "ema_trend": {"weight": 0.3, "fast": 12, "slow": 26, "band": 0.01},
        },
        "entry_threshold": 0.35, "regime_ma_period": 50,
        "bracket_mode": "atr", "stop_atr_mult": 1.2, "take_profit_atr_mult": 2.0,
    }


def ema_trend_profile(symbol: str = "BTC/USD") -> dict:
    return {
        "symbol": symbol, "timeframe": "15m", "kind": "researched",
        "label": f"EMA trend-momentum ({_DEMO_LABEL})",
        "signals": {"ema_trend": {"weight": 1.0, "fast": 12, "slow": 26, "band": 0.01}},
        "entry_threshold": 0.3, "regime_ma_period": 50,
        "bracket_mode": "atr", "stop_atr_mult": 1.5, "take_profit_atr_mult": 3.0,
    }


def fvg_retrace_profile(symbol: str = "BTC/USD") -> dict:
    return {
        "symbol": symbol, "timeframe": "15m", "kind": "researched",
        "label": f"FVG retrace ({_DEMO_LABEL})",
        "signals": {
            "fvg": {"weight": 0.6, "lookback": 50, "min_gap_pct": 0.0005},
            "ema_trend": {"weight": 0.4, "fast": 12, "slow": 26, "band": 0.01},
        },
        "entry_threshold": 0.35, "regime_ma_period": 50,
        "bracket_mode": "atr", "stop_atr_mult": 1.5, "take_profit_atr_mult": 2.0,
    }


def eth_rel_strength_profile(symbol: str = "ETH/USD") -> dict:
    return {
        "symbol": symbol, "benchmark_symbol": "BTC/USD", "timeframe": "15m",
        "kind": "researched", "label": f"ETH relative strength ({_DEMO_LABEL})",
        "signals": {
            "relative_strength": {"weight": 0.4, "band": 0.02, "lookback": 96},
            "ema_trend": {"weight": 0.3, "fast": 12, "slow": 26, "band": 0.01},
            "vwap": {"weight": 0.3, "window": 96, "max_dist": 0.03},
        },
        "entry_threshold": 0.35, "regime_ma_period": 50,
        "bracket_mode": "atr", "stop_atr_mult": 1.5, "take_profit_atr_mult": 2.0,
    }


RESEARCHED_PRESETS = {
    "vwap_pullback": vwap_pullback_profile,
    "ema_trend": ema_trend_profile,
    "fvg_retrace": fvg_retrace_profile,
    "eth_rel_strength": eth_rel_strength_profile,
}

RESEARCHED_META = [
    {"preset": "vwap_pullback", "label": "VWAP pullback",
     "signals": ["vwap", "oversold", "ema_trend"]},
    {"preset": "ema_trend", "label": "EMA trend-momentum", "signals": ["ema_trend"]},
    {"preset": "fvg_retrace", "label": "FVG retrace", "signals": ["fvg", "ema_trend"]},
    {"preset": "eth_rel_strength", "label": "ETH relative strength",
     "signals": ["relative_strength", "ema_trend", "vwap"]},
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_presets.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff check src/
git add src/swingbot/presets.py tests/test_presets.py
git commit -m "feat(presets): four researched standalone preset builders (kind=researched)"
```

### Task 3.3: Researched-strategy listing + arm endpoints

**Files:**
- Modify: `src/swingbot/web.py` (import builders; add `GET`/`POST /api/strategies/researched`; add body model)
- Test: `tests/test_web_strategy.py`

**Interfaces:**
- Consumes: `RESEARCHED_PRESETS`, `RESEARCHED_META`, `profiles.save`, `profiles.arm`, `controller.reload`.
- Produces: `GET /api/strategies/researched -> RESEARCHED_META`; `POST /api/strategies/researched` body `{"preset","symbol"}` → `200 {"name"}` (saves + arms + reload); `400` on unknown preset.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web_strategy.py` (reuse its `_Ctl`/`FakeMarket`; this test uses a real `ProfileStore`):

```python
def test_researched_listing_and_add(tmp_path):
    from swingbot.profiles import ProfileStore

    class Ctl(_Ctl):
        def __init__(self): self.reloaded = 0
        def reload(self): self.reloaded += 1

    profiles = ProfileStore(str(tmp_path / "p.db"))
    ctl = Ctl()
    app = create_app(ctl, profiles=profiles, creds=None, token="t",
                     store=None, market=FakeMarket())
    c = TestClient(app)

    listed = c.get("/api/strategies/researched").json()
    assert {m["preset"] for m in listed} == \
        {"vwap_pullback", "ema_trend", "fvg_retrace", "eth_rel_strength"}

    r = c.post("/api/strategies/researched",
               json={"preset": "ema_trend", "symbol": "SOL/USD"},
               headers={"X-Token": "t"})
    assert r.status_code == 200
    name = r.json()["name"]
    assert name in profiles.list_armed()
    assert profiles.get(name)["kind"] == "researched"
    assert ctl.reloaded == 1

    assert c.post("/api/strategies/researched",
                  json={"preset": "nope", "symbol": "SOL/USD"},
                  headers={"X-Token": "t"}).status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_web_strategy.py::test_researched_listing_and_add -q`
Expected: FAIL (404 — routes don't exist).

- [ ] **Step 3: Write the implementation**

In `src/swingbot/web.py`, add to the imports near the top (after the `kronos_bracket_profile` import, line 16):

```python
from swingbot.presets import RESEARCHED_META, RESEARCHED_PRESETS
```

Add a body model near the other `BaseModel`s:

```python
class ResearchedBody(BaseModel):
    preset: str
    symbol: str
```

Add the routes in the `# ---- strategies / arming ----` block (after the profile routes from Task 1.1). **Order matters:** declare `/api/strategies/researched` BEFORE `/api/strategies/{name}/profile` is matched — FastAPI matches by registration order and `researched` would otherwise be captured as a `{name}`. Since `researched` has no `/profile` suffix it cannot collide with the `{name}/profile` path, but register it first to be safe:

```python
    @app.get("/api/strategies/researched")
    def list_researched():
        return RESEARCHED_META

    @app.post("/api/strategies/researched")
    def add_researched(body: ResearchedBody, _=Depends(require_token)):
        builder = RESEARCHED_PRESETS.get(body.preset)
        if builder is None:
            raise HTTPException(status_code=400, detail=f"unknown preset {body.preset!r}")
        name = f"researched-{body.preset}-{body.symbol.replace('/', '-').lower()}"
        try:
            profiles.save(name, builder(body.symbol))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        profiles.arm(name)
        controller.reload()
        return {"name": name}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_web_strategy.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff check src/
git add src/swingbot/web.py tests/test_web_strategy.py
git commit -m "feat(web): GET/POST /api/strategies/researched (list + arm badged demo presets)"
```

### Task 3.4: Frontend client + helpers + Switch primitive

**Files:**
- Modify: `frontend/src/api.js` (add `listResearched`, `addResearched`)
- Modify: `frontend/src/lib/derive.js` (add `buildProfilePatch`)
- Create: `frontend/src/components/ui/switch.jsx`
- Test: `frontend/src/lib/derive.test.js`

**Interfaces:**
- Produces: `api.listResearched()`, `api.addResearched(preset, symbol)`; `buildProfilePatch(profile, edits) -> patch` (returns only whitelisted, changed keys); `<Switch checked onCheckedChange />`.

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/lib/derive.test.js`:

```javascript
import { buildProfilePatch } from './derive.js'

describe('buildProfilePatch', () => {
  it('returns only whitelisted changed keys', () => {
    const cur = { symbol: 'BTC/USD', entry_threshold: 0.05, poll_seconds: 60 }
    const patch = buildProfilePatch(cur, { entry_threshold: 0.2, poll_seconds: 5, symbol: 'X' })
    expect(patch).toEqual({ entry_threshold: 0.2 })
  })

  it('encodes regime toggle as allowed_regimes', () => {
    const patch = buildProfilePatch({ allowed_regimes: ['uptrend', 'neutral'] },
      { allowed_regimes: ['uptrend', 'neutral', 'downtrend'] })
    expect(patch.allowed_regimes).toEqual(['uptrend', 'neutral', 'downtrend'])
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/derive.test.js`
Expected: FAIL (`buildProfilePatch` is not exported).

- [ ] **Step 3: Write the helper**

Append to `frontend/src/lib/derive.js`:

```javascript
const PROFILE_PATCH_KEYS = new Set([
  'entry_threshold', 'allowed_regimes', 'regime_ma_period', 'signals',
  'stop_atr_mult', 'take_profit_atr_mult', 'tp_pct', 'sl_pct', 'bracket_mode',
  'max_hold_bars', 'risk_per_trade', 'max_position_frac',
  'daily_loss_limit_pct', 'max_consecutive_losses', 'max_concurrent',
  'cooldown_minutes',
])

// Returns a minimal patch of whitelisted keys whose value differs from `cur`.
export function buildProfilePatch(cur, edits) {
  const patch = {}
  for (const [k, v] of Object.entries(edits || {})) {
    if (!PROFILE_PATCH_KEYS.has(k)) continue
    if (JSON.stringify(v) !== JSON.stringify(cur?.[k])) patch[k] = v
  }
  return patch
}
```

- [ ] **Step 4: Add the client methods + Switch primitive**

In `frontend/src/api.js`, after the `addResearched` group (near `arm`/`disarm`), add:

```javascript
  listResearched: () => req('GET', '/api/strategies/researched'),
  addResearched: (preset, symbol) =>
    req('POST', '/api/strategies/researched', { preset, symbol }),
```

Create `frontend/src/components/ui/switch.jsx`:

```javascript
import { cn } from '../../lib/utils.js'

export function Switch({ checked, onCheckedChange, disabled }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onCheckedChange?.(!checked)}
      className={cn(
        'relative inline-flex h-5 w-9 items-center rounded-full transition-colors',
        checked ? 'bg-primary' : 'bg-muted',
        disabled && 'opacity-50',
      )}
    >
      <span className={cn(
        'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
        checked ? 'translate-x-4' : 'translate-x-0.5',
      )} />
    </button>
  )
}
```

- [ ] **Step 5: Run tests + build**

```bash
cd frontend && npx vitest run src/lib/derive.test.js && npm run build
```
Expected: PASS + build green.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api.js frontend/src/lib/derive.js \
        frontend/src/lib/derive.test.js frontend/src/components/ui/switch.jsx
git commit -m "feat(frontend): buildProfilePatch helper, researched client methods, Switch primitive"
```

### Task 3.5: Gates & Parameters panel on Coin Detail

**Files:**
- Create: `frontend/src/components/detail/GatesParametersPanel.jsx`
- Modify: `frontend/src/pages/CoinDetail.jsx` (mount the panel)

**Interfaces:**
- Consumes: `api.getStrategyProfile(name)`, `api.updateStrategyProfile(name, patch)`, `buildProfilePatch`, `<Switch>`.

- [ ] **Step 1: Create the panel**

Create `frontend/src/components/detail/GatesParametersPanel.jsx`:

```javascript
import { useEffect, useState } from 'react'
import { api } from '../../api.js'
import { Card, CardContent } from '../ui/card.jsx'
import { Button } from '../ui/button.jsx'
import { Switch } from '../ui/switch.jsx'
import { buildProfilePatch } from '../../lib/derive.js'

const REGIME_ON = ['uptrend', 'neutral']
const REGIME_OFF = ['uptrend', 'neutral', 'downtrend']
const NUMERIC = [
  ['entry_threshold', 'Entry threshold'],
  ['tp_pct', 'Take-profit %'],
  ['sl_pct', 'Stop-loss %'],
  ['stop_atr_mult', 'Stop ATR×'],
  ['take_profit_atr_mult', 'TP ATR×'],
  ['max_hold_bars', 'Max hold (bars)'],
  ['risk_per_trade', 'Risk per trade'],
  ['max_position_frac', 'Max position frac'],
  ['daily_loss_limit_pct', 'Daily loss limit'],
  ['max_consecutive_losses', 'Max consecutive losses'],
]

export default function GatesParametersPanel({ name }) {
  const [profile, setProfile] = useState(null)
  const [draft, setDraft] = useState(null)
  const [open, setOpen] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const load = async () => {
    try {
      const r = await api.getStrategyProfile(name)
      setProfile(r.profile); setDraft(JSON.parse(JSON.stringify(r.profile)))
    } catch (e) { setErr(e.message) }
  }
  useEffect(() => { load() /* eslint-disable-next-line */ }, [name])

  if (!draft) return null
  const regimeOn = !(draft.allowed_regimes || REGIME_ON).includes('downtrend')
  const signals = draft.signals || {}

  const setNum = (k, v) => setDraft({ ...draft, [k]: v === '' ? '' : Number(v) })
  const setSignalGate = (sig, on) =>
    setDraft({ ...draft, signals: { ...signals, [sig]: { ...signals[sig], gate: on } } })
  const setSignalMin = (sig, v) =>
    setDraft({ ...draft, signals: { ...signals, [sig]: { ...signals[sig], min_score: Number(v) } } })

  const save = async () => {
    setErr(''); setMsg('')
    const edits = { ...draft }
    edits.allowed_regimes = regimeOn ? REGIME_ON : REGIME_OFF
    const patch = buildProfilePatch(profile, edits)
    if (Object.keys(patch).length === 0) { setMsg('no changes'); return }
    try {
      const r = await api.updateStrategyProfile(name, patch)
      setProfile(r.profile); setMsg('saved, live — no rebuild')
    } catch (e) { setErr(e.message) }
  }

  return (
    <Card>
      <CardContent className="p-4">
        <button className="flex w-full items-center justify-between text-sm font-semibold"
          onClick={() => setOpen(!open)}>
          <span>Gates &amp; Parameters</span>
          <span className="text-muted-foreground">{open ? '▾' : '▸'}</span>
        </button>
        {open && (
          <div className="mt-3 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm">Regime gate</div>
                <div className="text-xs text-muted-foreground">
                  ON blocks entries during a 4h downtrend; OFF permits any regime.
                </div>
              </div>
              <Switch checked={regimeOn}
                onCheckedChange={(on) => setDraft({
                  ...draft, allowed_regimes: on ? REGIME_ON : REGIME_OFF })} />
            </div>

            <div className="space-y-2">
              <div className="text-xs font-semibold text-muted-foreground">Signal gates</div>
              {Object.keys(signals).map((sig) => (
                <div key={sig} className="flex items-center gap-3 text-sm">
                  <span className="w-32 font-mono">{sig}</span>
                  <Switch checked={!!signals[sig].gate}
                    onCheckedChange={(on) => setSignalGate(sig, on)} />
                  <span className="text-xs text-muted-foreground">gate</span>
                  <input type="number" step="0.05" className="ml-auto w-20 rounded border bg-background px-2 py-1 text-right"
                    value={signals[sig].min_score ?? 0}
                    onChange={(e) => setSignalMin(sig, e.target.value)} />
                  <span className="text-xs text-muted-foreground">min score</span>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-2 gap-2">
              {NUMERIC.filter(([k]) => draft[k] !== undefined).map(([k, label]) => (
                <label key={k} className="text-xs">
                  <span className="text-muted-foreground">{label}</span>
                  <input type="number" step="any"
                    className="mt-1 w-full rounded border bg-background px-2 py-1"
                    value={draft[k]} onChange={(e) => setNum(k, e.target.value)} />
                </label>
              ))}
            </div>

            {err && <div className="text-xs text-down">{err}</div>}
            {msg && <div className="text-xs text-up">{msg}</div>}
            <div className="flex justify-end">
              <Button size="sm" onClick={save}>Save</Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 2: Mount it in CoinDetail**

In `frontend/src/pages/CoinDetail.jsx`, add the import (after the `JournalFeedPanel` import, line 13):

```javascript
import GatesParametersPanel from '../components/detail/GatesParametersPanel.jsx'
```

In the rendered panels block (inside the `<>...</>` after `<ChartPanel .../>`, ~line 61), add as the first panel:

```javascript
          <GatesParametersPanel name={strategyName} />
```

- [ ] **Step 3: Build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit + live**

```bash
git add frontend/src/components/detail/GatesParametersPanel.jsx frontend/src/pages/CoinDetail.jsx
git commit -m "feat(frontend): Gates & Parameters tuning panel on Coin Detail"
docker compose build swingbot && docker compose up -d swingbot
```
Live-verify: open `http://localhost:8000/#/coin/kronos-btc-usd`, expand the panel, toggle the regime switch, change a number, Save → see "saved, live — no rebuild"; confirm via `curl -s localhost:8000/api/strategies/kronos-btc-usd/profile`.

### Task 3.6: Researched-preset option in the Add dialog

**Files:**
- Modify: `frontend/src/components/AddCoinDialog.jsx`

**Interfaces:**
- Consumes: `api.listResearched()`, `api.addResearched(preset, symbol)`, `api.universe()`.

- [ ] **Step 1: Add a researched section to the dialog**

In `frontend/src/components/AddCoinDialog.jsx`, extend the component to load researched presets and render a second section with the demo badge. Replace the body with:

```javascript
import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog.jsx'
import { Button } from './ui/button.jsx'
import { Badge } from './ui/badge.jsx'
import { availableToAdd } from '../lib/derive.js'

export default function AddCoinDialog({ open, onOpenChange, onAdded }) {
  const [options, setOptions] = useState([])
  const [watchlist, setWatchlist] = useState({ symbols: [] })
  const [strategies, setStrategies] = useState([])
  const [researched, setResearched] = useState([])
  const [universe, setUniverse] = useState([])
  const [preset, setPreset] = useState('')
  const [symbol, setSymbol] = useState('')
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!open) return
    setErr('')
    Promise.all([api.universe(), api.watchlist(), api.strategies(), api.listResearched()])
      .then(([u, w, s, r]) => {
        setOptions(availableToAdd(u, w)); setWatchlist(w); setStrategies(s)
        setResearched(r); setUniverse(u.symbols || [])
      })
      .catch((e) => setErr(e.message))
  }, [open])

  const add = async (sym) => {
    setBusy(sym); setErr('')
    try {
      await api.setWatchlist([...(watchlist.symbols || []), sym])
      const match = strategies.find((st) => st.symbol === sym)
      if (match) await api.arm(match.name)
      await onAdded?.(); onOpenChange(false)
    } catch (e) { setErr(e.message) } finally { setBusy('') }
  }

  const addResearched = async () => {
    if (!preset || !symbol) { setErr('pick a preset and a symbol'); return }
    setBusy('researched'); setErr('')
    try {
      await api.addResearched(preset, symbol)
      await onAdded?.(); onOpenChange(false)
    } catch (e) { setErr(e.message) } finally { setBusy('') }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Add coin</DialogTitle></DialogHeader>
        {err && <div className="mb-2 rounded-md bg-down/15 px-3 py-2 text-sm text-down">{err}</div>}

        <div className="text-xs font-semibold text-muted-foreground">Kronos (default)</div>
        <div className="max-h-48 space-y-1 overflow-y-auto">
          {options.length === 0
            ? <div className="p-3 text-center text-sm text-muted-foreground">All symbols already added.</div>
            : options.map((sym) => (
              <button key={sym} disabled={busy === sym} onClick={() => add(sym)}
                className="flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm hover:bg-accent disabled:opacity-50">
                <span className="font-medium">{sym}</span>
                <span className="text-xs text-muted-foreground">{busy === sym ? 'adding…' : 'add →'}</span>
              </button>
            ))}
        </div>

        <div className="mt-4 flex items-center gap-2">
          <span className="text-xs font-semibold text-muted-foreground">Researched strategies</span>
          <Badge variant="outline" className="text-down">⚠️ backtested negative-edge — demo only</Badge>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <select className="rounded border bg-background px-2 py-1 text-sm"
            value={preset} onChange={(e) => setPreset(e.target.value)}>
            <option value="">preset…</option>
            {researched.map((r) => <option key={r.preset} value={r.preset}>{r.label}</option>)}
          </select>
          <select className="rounded border bg-background px-2 py-1 text-sm"
            value={symbol} onChange={(e) => setSymbol(e.target.value)}>
            <option value="">symbol…</option>
            {universe.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <Button size="sm" variant="outline" disabled={busy === 'researched'}
            onClick={addResearched}>{busy === 'researched' ? 'adding…' : 'arm demo'}</Button>
        </div>

        <div className="mt-3 flex justify-end">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>Close</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 2: Build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit + live**

```bash
git add frontend/src/components/AddCoinDialog.jsx
git commit -m "feat(frontend): researched-preset (badged demo) option in Add dialog"
docker compose build swingbot && docker compose up -d swingbot
```
Live-verify: Mission Control → Add coin → pick a researched preset + symbol → "arm demo" → a new `researched-*` card appears.

---

# Phase 4 — Live-price feed

Delivers success criterion 4.

### Task 4.1: `PriceCache` (per-symbol TTL, stale fallback)

**Files:**
- Create: `src/swingbot/price_cache.py`
- Test: `tests/test_price_cache.py`

**Interfaces:**
- Produces: `PriceCache(fetch, ttl=2.0, clock=time.monotonic)` with `.get(symbols) -> {symbol: {"price": float|None, "ts": str|None, "stale": bool}}`. `fetch(symbols) -> {symbol: float}`; on `fetch` exception, serves last cached and marks `stale=True`; only fetches symbols whose cache entry is missing or older than `ttl`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_price_cache.py`:

```python
from swingbot.price_cache import PriceCache


class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


def test_collapses_calls_within_ttl():
    clock = Clock()
    calls = []
    def fetch(syms):
        calls.append(tuple(syms)); return {s: 100.0 for s in syms}
    pc = PriceCache(fetch, ttl=2.0, clock=clock)
    pc.get(["BTC/USD"]); pc.get(["BTC/USD"])
    assert len(calls) == 1                       # second call served from cache
    clock.t += 3.0
    pc.get(["BTC/USD"])
    assert len(calls) == 2                       # ttl expired -> refetch


def test_serves_last_value_and_marks_stale_on_error():
    clock = Clock()
    state = {"fail": False}
    def fetch(syms):
        if state["fail"]:
            raise RuntimeError("upstream down")
        return {s: 60810.2 for s in syms}
    pc = PriceCache(fetch, ttl=2.0, clock=clock)
    first = pc.get(["BTC/USD"])
    assert first["BTC/USD"]["price"] == 60810.2 and first["BTC/USD"]["stale"] is False
    state["fail"] = True
    clock.t += 5.0
    out = pc.get(["BTC/USD"])
    assert out["BTC/USD"]["price"] == 60810.2     # last good value retained
    assert out["BTC/USD"]["stale"] is True


def test_unknown_symbol_after_failed_first_fetch_is_null_stale():
    def fetch(syms):
        raise RuntimeError("down")
    pc = PriceCache(fetch, ttl=2.0, clock=Clock())
    out = pc.get(["ETH/USD"])
    assert out["ETH/USD"] == {"price": None, "ts": None, "stale": True}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_price_cache.py -q`
Expected: FAIL (`ModuleNotFoundError: swingbot.price_cache`).

- [ ] **Step 3: Write the implementation**

Create `src/swingbot/price_cache.py`:

```python
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Callable


class PriceCache:
    """Per-symbol TTL cache over a last-price fetcher. Multiple clients / a fast
    poll collapse to <=1 upstream call per symbol per `ttl` seconds. On a fetch
    error the last cached value is served with stale=True; never raises."""

    def __init__(self, fetch: Callable[[list[str]], dict],
                 ttl: float = 2.0, clock: Callable[[], float] = time.monotonic):
        self._fetch = fetch
        self._ttl = ttl
        self._clock = clock
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, float, str]] = {}  # sym -> (price, mono_ts, iso)

    def get(self, symbols: list[str]) -> dict:
        now = self._clock()
        stale_syms = [s for s in symbols if self._expired(s, now)]
        if stale_syms:
            try:
                fresh = self._fetch(stale_syms)
                iso = datetime.now(timezone.utc).isoformat()
                with self._lock:
                    for s, price in fresh.items():
                        self._cache[s] = (float(price), now, iso)
            except Exception:
                pass  # serve last cached; stale flag computed below
        out: dict = {}
        with self._lock:
            for s in symbols:
                entry = self._cache.get(s)
                if entry is None:
                    out[s] = {"price": None, "ts": None, "stale": True}
                else:
                    price, mono_ts, iso = entry
                    out[s] = {"price": price, "ts": iso,
                              "stale": (now - mono_ts) > self._ttl}
        return out

    def _expired(self, symbol: str, now: float) -> bool:
        entry = self._cache.get(symbol)
        return entry is None or (now - entry[1]) > self._ttl
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_price_cache.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff check src/
git add src/swingbot/price_cache.py tests/test_price_cache.py
git commit -m "feat: PriceCache (per-symbol TTL + stale fallback)"
```

### Task 4.2: `GET /api/price` endpoint

**Files:**
- Modify: `src/swingbot/web.py` (import `PriceCache`; lazily build a cache over `market._provider().get_latest_prices`; add the route in the `# ---- read ----` block)
- Test: `tests/test_web_price.py`

**Interfaces:**
- Consumes: `market._provider()` → provider with `get_latest_prices(symbols) -> {sym: float}`; `PriceCache`.
- Produces: `GET /api/price?symbols=BTC/USD,ETH/USD` → `{sym: {"price","ts","stale"}}`; `{}` when no symbols or no market.

- [ ] **Step 1: Write the failing test**

Create `tests/test_web_price.py`:

```python
from fastapi.testclient import TestClient

from swingbot.web import create_app


class FakeProvider:
    def __init__(self): self.calls = 0
    def get_latest_prices(self, symbols):
        self.calls += 1
        return {s: 100.0 + i for i, s in enumerate(symbols)}


class FakeMarket:
    def __init__(self): self.prov = FakeProvider()
    def _provider(self): return self.prov


class _Ctl:
    def status(self): return {}


def _client(market):
    app = create_app(_Ctl(), profiles=None, creds=None, token="t", market=market)
    return TestClient(app)


def test_price_returns_cached_quotes():
    market = FakeMarket()
    c = _client(market)
    r = c.get("/api/price?symbols=BTC/USD,ETH/USD")
    assert r.status_code == 200
    body = r.json()
    assert body["BTC/USD"]["price"] == 100.0
    assert body["ETH/USD"]["price"] == 101.0
    assert body["BTC/USD"]["stale"] is False
    # second immediate call is served from the 2s cache (no extra upstream call)
    c.get("/api/price?symbols=BTC/USD,ETH/USD")
    assert market.prov.calls == 1


def test_price_empty_when_no_symbols():
    assert _client(FakeMarket()).get("/api/price").json() == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_web_price.py -q`
Expected: FAIL (404 — route missing).

- [ ] **Step 3: Write the implementation**

In `src/swingbot/web.py`, add the import near the top (after the `RebalanceSettings` import, line 19):

```python
from swingbot.price_cache import PriceCache
```

Inside `create_app`, before the `# ---- read ----` block (after `app = FastAPI(...)` and the `auto_dashboard` include, ~line 115), add a lazily-built cache holder:

```python
    _price_holder: dict = {}

    def _price_cache():
        if "pc" not in _price_holder and market is not None:
            def fetch(syms):
                prov = market._provider()
                if prov is None or not hasattr(prov, "get_latest_prices"):
                    return {}
                return prov.get_latest_prices(syms)
            _price_holder["pc"] = PriceCache(fetch, ttl=2.0)
        return _price_holder.get("pc")
```

In the `# ---- read ----` block, add the route (e.g. after `/api/candles`, ~line 168):

```python
    @app.get("/api/price")
    def price(symbols: str = ""):
        syms = [s for s in symbols.split(",") if s]
        cache = _price_cache()
        if not syms or cache is None:
            return {}
        return cache.get(syms)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_web_price.py -q`
Expected: PASS.

- [ ] **Step 5: Commit + live**

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check src/
git add src/swingbot/web.py tests/test_web_price.py
git commit -m "feat(web): GET /api/price (2s TTL cached last-trade feed)"
docker compose build swingbot && docker compose up -d swingbot
```
Live-verify (criterion 4): `time curl -s "localhost:8000/api/price?symbols=BTC/USD,ETH/USD" | python3 -m json.tool` returns sub-second with `price`/`ts`/`stale` for both, and a repeated call within 2s does not increase upstream calls.

### Task 4.3: Frontend `useLivePrice` + live prices on cards and header

**Files:**
- Create: `frontend/src/components/useLivePrice.js`
- Modify: `frontend/src/api.js` (add `price`)
- Modify: `frontend/src/lib/derive.js` + `derive.test.js` (add `livePriceFor`)
- Modify: `frontend/src/pages/MissionControl.jsx` (poll prices, pass to grid)
- Modify: `frontend/src/components/CoinsGrid.jsx` + `CoinCard.jsx` (render live price)
- Modify: `frontend/src/pages/CoinDetail.jsx` (header live price)

**Interfaces:**
- Produces: `api.price(symbols: string[])`; `useLivePrice(symbols, intervalMs=3000) -> pricesMap`; `livePriceFor(prices, symbol) -> {price, stale}|null`.

- [ ] **Step 1: Write the failing helper test**

Append to `frontend/src/lib/derive.test.js`:

```javascript
import { livePriceFor } from './derive.js'

describe('livePriceFor', () => {
  it('returns the quote for a symbol or null', () => {
    const prices = { 'BTC/USD': { price: 60810.2, stale: false } }
    expect(livePriceFor(prices, 'BTC/USD')).toEqual({ price: 60810.2, stale: false })
    expect(livePriceFor(prices, 'ETH/USD')).toBeNull()
    expect(livePriceFor(null, 'BTC/USD')).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/derive.test.js`
Expected: FAIL (`livePriceFor` not exported).

- [ ] **Step 3: Implement helper, api method, and hook**

Append to `frontend/src/lib/derive.js`:

```javascript
export function livePriceFor(prices, symbol) {
  const q = prices?.[symbol]
  return q ? { price: q.price, stale: !!q.stale } : null
}
```

In `frontend/src/api.js`, add (near the `candles` method):

```javascript
  price: (symbols) =>
    req('GET', `/api/price?symbols=${encodeURIComponent((symbols || []).join(','))}`),
```

Create `frontend/src/components/useLivePrice.js`:

```javascript
import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'

// Polls /api/price every `intervalMs` for the given symbols. Returns a map
// { symbol: { price, ts, stale } }. Candle/chart cadence is unaffected.
export default function useLivePrice(symbols, intervalMs = 3000) {
  const [prices, setPrices] = useState({})
  const key = (symbols || []).slice().sort().join(',')
  const ref = useRef(symbols)
  ref.current = symbols

  useEffect(() => {
    if (!key) return
    let alive = true
    const tick = async () => {
      try { const d = await api.price(ref.current); if (alive) setPrices(d) } catch { /* keep last */ }
    }
    tick()
    const id = setInterval(tick, intervalMs)
    return () => { alive = false; clearInterval(id) }
  }, [key, intervalMs])

  return prices
}
```

- [ ] **Step 4: Wire into Mission Control + grid + card**

In `frontend/src/pages/MissionControl.jsx`: import the hook and derive symbols from state, then pass `prices` to `CoinsGrid`.
Add imports:
```javascript
import useLivePrice from '../components/useLivePrice.js'
```
After `const [addOpen, setAddOpen] = useState(false)`:
```javascript
  const symbols = (state?.strategies || []).map((s) => s.symbol).filter(Boolean)
  const prices = useLivePrice(symbols)
```
Change the grid usage to pass prices:
```javascript
      <CoinsGrid state={state} health={health} prices={prices} onChange={refresh} onAdd={() => setAddOpen(true)} />
```

In `frontend/src/components/CoinsGrid.jsx`: thread `prices` through to each `CoinCard` (pass `price={prices?.[strategy.symbol]}`). Open the file and add `prices` to the destructured props and to the `<CoinCard ... price={prices?.[s.symbol]} />` render.

In `frontend/src/components/CoinCard.jsx`: accept `price` and render it. Add `price` to the props (`{ strategy, health, prices, onChange, price }` — keep existing props), import `livePriceFor` is not needed since the parent passes the per-symbol object; render under the symbol line. After the symbol/header `<div className="flex items-center justify-between">...</div>` (line 33-36), add:
```javascript
        {price?.price != null && (
          <div className="font-mono text-xs text-muted-foreground">
            ${Number(price.price).toFixed(2)}{price.stale ? ' (stale)' : ''}
          </div>
        )}
```
Also render the researched badge: in the header, after the status `<Badge>`, add:
```javascript
          {strategy.kind === 'researched' && (
            <Badge variant="outline" className="text-down">demo</Badge>
          )}
```

In `frontend/src/pages/CoinDetail.jsx`: add a single-symbol live price to the header. Add import + hook:
```javascript
import useLivePrice from '../components/useLivePrice.js'
```
After `const symbol = strat?.symbol`:
```javascript
  const prices = useLivePrice(symbol ? [symbol] : [])
  const live = symbol ? prices[symbol] : null
```
In the header `<h1>` row, after the `<Badge variant="outline">{status}</Badge>`:
```javascript
        {live?.price != null && (
          <span className="font-mono text-sm text-muted-foreground">
            ${Number(live.price).toFixed(2)}{live.stale ? ' (stale)' : ''}
          </span>
        )}
```

- [ ] **Step 5: Run tests + build**

```bash
cd frontend && npx vitest run && npm run build
```
Expected: PASS + build green.

- [ ] **Step 6: Commit + live**

```bash
git add frontend/src/components/useLivePrice.js frontend/src/api.js \
        frontend/src/lib/derive.js frontend/src/lib/derive.test.js \
        frontend/src/pages/MissionControl.jsx frontend/src/pages/CoinDetail.jsx \
        frontend/src/components/CoinsGrid.jsx frontend/src/components/CoinCard.jsx
git commit -m "feat(frontend): useLivePrice 3s poller; live price on cards + coin header"
docker compose build swingbot && docker compose up -d swingbot
```
Live-verify: Mission Control cards and the coin header show a price that updates ~every 3s.

---

# Phase 5 — Faster initial load

Delivers success criterion 5.

### Task 5.1: `localStorage` SWR cache helpers

**Files:**
- Create: `frontend/src/lib/cache.js`
- Test: `frontend/src/lib/cache.test.js`

**Interfaces:**
- Produces: `readCache(key) -> any|null`; `writeCache(key, data) -> void`. Both swallow all storage errors (quota / no-localStorage).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/cache.test.js`:

```javascript
import { describe, it, expect, beforeEach } from 'vitest'
import { readCache, writeCache } from './cache.js'

describe('localStorage cache', () => {
  beforeEach(() => {
    const store = new Map()
    globalThis.localStorage = {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k),
    }
  })

  it('round-trips JSON', () => {
    writeCache('k', { a: 1 })
    expect(readCache('k')).toEqual({ a: 1 })
  })

  it('returns null for a missing key', () => {
    expect(readCache('missing')).toBeNull()
  })

  it('never throws when storage is unavailable', () => {
    globalThis.localStorage = undefined
    expect(() => writeCache('k', { a: 1 })).not.toThrow()
    expect(readCache('k')).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/cache.test.js`
Expected: FAIL (`cache.js` does not exist).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/lib/cache.js`:

```javascript
// Stale-while-revalidate cache backed by localStorage. All errors are swallowed
// so the UI never breaks on quota limits or a missing storage API.
export function readCache(key) {
  try {
    const raw = globalThis.localStorage?.getItem(key)
    return raw ? JSON.parse(raw) : null
  } catch { return null }
}

export function writeCache(key, data) {
  try { globalThis.localStorage?.setItem(key, JSON.stringify(data)) } catch { /* ignore */ }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/lib/cache.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/cache.js frontend/src/lib/cache.test.js
git commit -m "feat(frontend): localStorage SWR cache helpers"
```

### Task 5.2: Skeleton primitive + Mission Control hydration

**Files:**
- Create: `frontend/src/components/ui/skeleton.jsx`
- Modify: `frontend/src/pages/MissionControl.jsx` (hydrate from cache; persist on success)
- Modify: `frontend/src/components/StatusStrip.jsx` + `LiveJournal.jsx` (skeleton when no data)

**Interfaces:**
- Consumes: `readCache`/`writeCache`. Produces: `<Skeleton className />` placeholder.

- [ ] **Step 1: Create the Skeleton primitive**

Create `frontend/src/components/ui/skeleton.jsx`:

```javascript
import { cn } from '../../lib/utils.js'

export function Skeleton({ className }) {
  return <div className={cn('animate-pulse rounded-md bg-muted/60', className)} />
}
```

- [ ] **Step 2: Hydrate Mission Control from cache**

In `frontend/src/pages/MissionControl.jsx`, import the cache helpers:
```javascript
import { readCache, writeCache } from '../lib/cache.js'
```
Change the state initializers to hydrate immediately:
```javascript
  const [state, setState] = useState(() => readCache('swingbot:state'))
  const [health, setHealth] = useState(() => readCache('swingbot:health'))
```
In `refresh`, persist on success:
```javascript
  const refresh = useCallback(async () => {
    try { const s = await api.state(); setState(s); writeCache('swingbot:state', s) } catch { /* keep last */ }
    try { const h = await api.tradingHealth(); setHealth(h); writeCache('swingbot:health', h) } catch { /* keep last */ }
  }, [])
```

- [ ] **Step 3: Add skeletons when data is still null**

In `frontend/src/components/StatusStrip.jsx`, at the top of the component, when `state == null` render a skeleton bar. Add near the top of the render (import `Skeleton` from `./ui/skeleton.jsx`):
```javascript
  if (!state) return <Skeleton className="h-12 w-full" />
```
(Place this guard before the existing JSX that dereferences `state`.)

In `frontend/src/components/LiveJournal.jsx`, when there are no decisions yet, render three skeleton rows instead of an empty panel. Import `Skeleton` and, where it currently shows the empty/loading state, render:
```javascript
      <div className="space-y-2">
        <Skeleton className="h-6 w-full" />
        <Skeleton className="h-6 w-full" />
        <Skeleton className="h-6 w-full" />
      </div>
```
(Only in the no-data branch; keep the real list when data exists.)

- [ ] **Step 4: Build**

Run: `cd frontend && npm run build && npx vitest run`
Expected: build + tests green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ui/skeleton.jsx frontend/src/pages/MissionControl.jsx \
        frontend/src/components/StatusStrip.jsx frontend/src/components/LiveJournal.jsx
git commit -m "feat(frontend): skeletons + localStorage hydration on Mission Control"
```

### Task 5.3: Coin Detail hydration + non-blocking panels

**Files:**
- Modify: `frontend/src/pages/CoinDetail.jsx` (hydrate `/api/state` from cache; panels already render their own shells via `usePolling`)

**Interfaces:**
- Consumes: `readCache`/`writeCache`.

- [ ] **Step 1: Hydrate Coin Detail state from cache**

In `frontend/src/pages/CoinDetail.jsx`, import the cache helpers:
```javascript
import { readCache, writeCache } from '../lib/cache.js'
```
Change the state initializer and the `refresh` writer:
```javascript
  const [state, setState] = useState(() => readCache('swingbot:state'))
```
```javascript
  const refresh = useCallback(async () => {
    try { const s = await api.state(); setState(s); writeCache('swingbot:state', s) } catch { /* keep last */ }
  }, [])
```
The shared `swingbot:state` key means navigating from Mission Control paints the coin immediately from the warm cache. The per-panel children (`ChartPanel`, `BacktestComparisonPanel`, `LiveStatsPanel`, etc.) already poll independently via `usePolling`, so they render their own shells and never block the page — no change needed there.

- [ ] **Step 2: Build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Full gate + commit + live (criterion 5 + 6)**

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check src/
cd frontend && npm run build && npx vitest run && cd ..
git add frontend/src/pages/CoinDetail.jsx
git commit -m "feat(frontend): localStorage hydration on Coin Detail (instant paint)"
docker compose build swingbot && docker compose up -d swingbot
```
Live-verify (criterion 5): hard-reload `http://localhost:8000/#/` — Mission Control paints cached cards/status immediately (no ~10s blank), then revalidates. Optionally confirm with a Playwright snapshot like prior smokes.

- [ ] **Step 4: Update the roadmap**

Update `crypto-swing-bot/docs/ROADMAP_STATUS.md` NEXT ACTION + add a LATEST SESSION block summarizing the five shipped phases, the new endpoints, and the regime-off unblock. Commit:
```bash
git add docs/ROADMAP_STATUS.md
git commit -m "docs: roadmap — tunable gates / live data / faster UI shipped"
```

---

## Self-Review (completed against the spec)

**Spec coverage:**
- Component 1 (live profile tuning + regime toggle): Tasks 1.1–1.3. ✓
- Component 2 (gate layer: reserved-key strip, GATE_BLOCKED, orchestrator wiring, contract): Tasks 2.1–2.3. ✓
- Component 3a (researched signals as gates/contributors): enabled by the strip (2.1) + tuning panel add-signal/gate controls (3.5). ✓
- Component 3b (standalone researched presets, badged): Tasks 3.2, 3.3, 3.6. ✓
- Component 4 (Gates & Parameters panel; Add dialog preset option): Tasks 3.4–3.6. ✓
- Component 5 (live-price feed: cache + endpoint + `useLivePrice`): Tasks 4.1–4.3. ✓
- Component 6 (faster load: SWR cache + skeletons + non-blocking panels): Tasks 5.1–5.3. ✓
- Success criteria 1 (regime-off trade): 1.3. 2 (param live, no rebuild): 1.1. 3 (GATE_BLOCKED): 2.3. 4 (price ≤1 call/2s, sub-second): 4.1–4.2. 5 (instant paint): 5.2–5.3. 6 (full gate green): run at the end of 2.3, 4.2, 5.3. ✓
- Final decision-pipeline order (`…REGIME_BLOCKED → GATE_BLOCKED → SIGNAL_BELOW_THRESHOLD…`): enforced by inserting `_check_gates` between the regime and confluence-threshold checks (2.3). ✓

**Type consistency:** `kind`/`label` added to `StrategyProfile` (3.1) before any preset sets them (3.2) and before `from_dict` validates them (used in 1.1 save path, 3.3 save path). `_PROFILE_PATCH_KEYS` (backend, 1.1) mirrors `PROFILE_PATCH_KEYS` (frontend `buildProfilePatch`, 3.4). `PriceCache.get` return shape `{price, ts, stale}` is consumed identically by the `/api/price` test (4.2), `livePriceFor` (4.3), and the card/header renders (4.3). `RESEARCHED_PRESETS`/`RESEARCHED_META` defined in 3.2 are imported in 3.3.

**Placeholder scan:** none — every code step carries complete code and exact commands.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-24-tunable-gates-live-data-implementation.md`. Two execution options:

1. **Subagent-Driven (recommended)** — a fresh subagent per task with two-stage review between tasks.
2. **Inline Execution** — execute tasks in this session via `superpowers:executing-plans`, with checkpoints.

Phase 1 is the immediate-value unblock (ships the tuning endpoint + flips the regime gate off so the bot trades). Which approach?
