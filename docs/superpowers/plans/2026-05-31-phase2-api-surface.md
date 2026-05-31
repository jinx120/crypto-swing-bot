# Phase 2 — API Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the Phase-1 `PortfolioSupervisor` over HTTP: a portfolio + per-strategy `/api/state`, arm/disarm + live-eligible endpoints, portfolio-settings endpoints, portfolio-level and per-strategy controls, and aggregate (filterable) journal/metrics. Wire the supervisor into `webmain` with an always-on poller that keeps all armed symbols warm.

**Architecture:** `PortfolioSupervisor` becomes the `controller` the FastAPI app depends on (a `PortfolioController` Protocol). The web layer stays thin — it validates input and delegates. Arming mutates `ProfileStore` then calls `controller.reload()` to rebuild the live strategy set.

**Tech Stack:** FastAPI, pydantic, pytest + `fastapi.testclient.TestClient`. Run tests with `.venv/bin/python -m pytest -q`.

**Reference:** Design spec `docs/superpowers/specs/2026-05-31-multi-asset-concurrent-trading-design.md` §7. Depends on Phase 1.

---

### Task 1: Supervisor control surface — journal, metrics, controls, reload

Add the methods the web layer calls. Reuses Phase-1 internals.

**Files:**
- Modify: `src/swingbot/supervisor.py`
- Test: `tests/test_supervisor_control.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_supervisor_control.py` (reuses the Phase-1 test fakes):

```python
from datetime import datetime, timezone

from swingbot.profiles import ProfileStore
from swingbot.supervisor import PortfolioSupervisor
from tests.test_supervisor import FakeMarket, FakeBroker, _profile, _bars

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _sup(tmp_path, symbols):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    for sym in symbols:
        name = sym.split("/")[0].lower()
        profiles.save(name, _profile(sym)); profiles.arm(name)
    market = FakeMarket({sym: _bars(100.0 + i * 10) for i, sym in enumerate(symbols)})
    sup = PortfolioSupervisor(profiles=profiles, creds=None,
                              state_db=str(tmp_path / "s.db"), market=market,
                              broker=FakeBroker(), mode="paper")
    sup.build()
    return sup


def test_journal_and_metrics_aggregate(tmp_path):
    sup = _sup(tmp_path, ["BTC/USD", "ETH/USD"])
    sup.tick_all(now=T0)
    assert isinstance(sup.journal(), list)
    assert "n_trades" in sup.metrics()
    # per-strategy filter returns a subset
    assert isinstance(sup.journal(strategy="btc"), list)


def test_halt_and_reset_portfolio_kill_switch(tmp_path):
    sup = _sup(tmp_path, ["BTC/USD"])
    sup.tick_all(now=T0)
    sup.halt()
    assert sup.status()["portfolio"]["kill_switch"]["active"] is True
    sup.reset()
    assert sup.status()["portfolio"]["kill_switch"]["active"] is False


def test_flatten_one_and_all(tmp_path):
    sup = _sup(tmp_path, ["BTC/USD", "ETH/USD"])
    sup.tick_all(now=T0)
    sup.flatten("btc")
    assert sup._store.load_position("btc") is None
    sup.flatten()                                  # all remaining
    assert sup._store.load_all_positions() == {}


def test_set_mode_live_blocked_without_graduation(tmp_path):
    sup = _sup(tmp_path, ["BTC/USD"])
    sup.tick_all(now=T0)
    ok, reason = sup.set_mode("live")
    assert ok is False and "blocked" in reason.lower()


def test_reload_picks_up_newly_armed(tmp_path):
    sup = _sup(tmp_path, ["BTC/USD"])
    sup.profiles.save("eth", _profile("ETH/USD")); sup.profiles.arm("eth")
    sup.reload()
    names = {s["name"] for s in sup.status()["strategies"]}
    assert names == {"btc", "eth"}
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_supervisor_control.py -q`
Expected: FAIL — `AttributeError: 'PortfolioSupervisor' object has no attribute 'journal'`.

- [ ] **Step 3: Add imports and methods to the supervisor**

In `src/swingbot/supervisor.py`, add these imports near the top (after the existing
`from swingbot.snapshot import signal_snapshot` line):

```python
from dataclasses import asdict

from swingbot.graduation import can_go_live
from swingbot.metrics import compute_metrics
from swingbot.types import ExitReason  # noqa: F401 (kept for _trade_dict regime/reason values)
```

Add these methods to the `PortfolioSupervisor` class (after `status`):

```python
    # ---- aggregate journal + metrics ----
    def _trades(self, strategy: str | None = None) -> list:
        out = []
        for name, s in self._strategies.items():
            if strategy and name != strategy:
                continue
            out.extend(s["orch"].journal.trades)
        return out

    def journal(self, strategy: str | None = None) -> list[dict]:
        return [_trade_dict(t) for t in self._trades(strategy)]

    def metrics(self, strategy: str | None = None) -> dict:
        return asdict(compute_metrics(self._trades(strategy)))

    # ---- controls ----
    def halt(self) -> None:
        if not self._portfolio_risk:
            return
        self._portfolio_risk.state.kill_switch_active = True
        self._portfolio_risk.state.kill_switch_reason = "manual halt"
        self._store.save_portfolio_risk_state(self._portfolio_risk.state)

    def reset(self) -> None:
        if not self._portfolio_risk:
            return
        self._portfolio_risk.state.kill_switch_active = False
        self._portfolio_risk.state.kill_switch_reason = ""
        self._store.save_portfolio_risk_state(self._portfolio_risk.state)

    def flatten(self, name: str | None = None) -> None:
        targets = [name] if name else list(self._strategies)
        for n in targets:
            s = self._strategies.get(n)
            if s:
                s["orch"].flatten()

    def set_mode(self, mode: str) -> tuple[bool, str]:
        if mode not in ("paper", "live"):
            return (False, "mode must be 'paper' or 'live'")
        if mode == "live":
            ok, reason = can_go_live(compute_metrics(self._trades()))
            if not ok:
                return (False, f"go-live blocked: {reason}")
        was_running = self._running
        self.stop()
        self.mode = mode
        self._broker = None                       # force rebuild with the new mode's keys
        if was_running:
            self.start()
        else:
            self.build()
        return (True, f"mode set to {mode}")

    def reload(self) -> None:
        """Rebuild the live strategy set after arming/disarming or settings changes."""
        self.build()
```

Add this module-level helper at the very bottom of the file (after `_pos_dict`):

```python
def _trade_dict(t):
    return {"entry_ts": t.entry_ts.isoformat(), "exit_ts": t.exit_ts.isoformat(),
            "entry_price": t.entry_price, "exit_price": t.exit_price, "qty": t.qty,
            "pnl": t.pnl, "exit_reason": t.exit_reason.value,
            "score_at_entry": t.score_at_entry, "regime_at_entry": t.regime_at_entry.value}
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_supervisor_control.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/supervisor.py tests/test_supervisor_control.py
git commit -m "feat(supervisor): aggregate journal/metrics, portfolio controls, mode switch, reload"
```

---

### Task 2: Rework the FastAPI app for the portfolio surface

**Files:**
- Modify (full rewrite): `src/swingbot/web.py`
- Test: `tests/test_web_portfolio.py` (new). `tests/test_web_credentials.py` and
  `tests/test_web_strategy.py` are unaffected; `tests/test_web_profiles.py` and
  `tests/test_candle_store.py` are migrated to the armed model in Step 5;
  `tests/test_web_read.py` and `tests/test_web_control.py` get new controller signatures in
  Step 6.

- [ ] **Step 1: Write the failing test**

Create `tests/test_web_portfolio.py`:

```python
from fastapi.testclient import TestClient
from swingbot.web import create_app
from swingbot.profiles import ProfileStore


class FakeController:
    def __init__(self): self.calls = []; self.armed_reloaded = 0
    def status(self): return {"portfolio": {"mode": "paper", "open_positions": 0},
                              "strategies": []}
    def journal(self, strategy=None): self.calls.append(("journal", strategy)); return []
    def metrics(self, strategy=None): self.calls.append(("metrics", strategy)); return {"n_trades": 0}
    def halt(self): self.calls.append("halt")
    def reset(self): self.calls.append("reset")
    def pause(self): self.calls.append("pause")
    def resume(self): self.calls.append("resume")
    def flatten(self, name=None): self.calls.append(("flatten", name))
    def set_mode(self, mode): self.calls.append(("mode", mode)); return (mode == "paper", "ok")
    def start(self): self.calls.append("start")
    def stop(self): self.calls.append("stop")
    def reload(self): self.armed_reloaded += 1


def _client(tmp_path, token="t"):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    ctrl = FakeController()
    app = create_app(controller=ctrl, profiles=profiles, creds=None, token=token)
    return TestClient(app), ctrl, profiles


def test_state_is_portfolio_shaped(tmp_path):
    c, _, _ = _client(tmp_path)
    body = c.get("/api/state").json()
    assert "portfolio" in body and "strategies" in body


def test_arm_disarm_reload_and_require_token(tmp_path):
    c, ctrl, profiles = _client(tmp_path)
    profiles.save("btc", {"symbol": "BTC/USD", "signals": {"oversold": {"weight": 1.0}},
                          "entry_threshold": 0.3})
    assert c.post("/api/strategies/arm", json={"name": "btc"}).status_code == 401
    h = {"X-Token": "t"}
    assert c.post("/api/strategies/arm", json={"name": "btc"}, headers=h).status_code == 200
    assert ctrl.armed_reloaded == 1
    assert "btc" in {s["name"] for s in c.get("/api/strategies").json() if s["armed"]}
    assert c.post("/api/strategies/disarm", json={"name": "btc"}, headers=h).status_code == 200
    assert ("flatten", "btc") in ctrl.calls         # disarm flattens first


def test_live_eligible_endpoint(tmp_path):
    c, _, profiles = _client(tmp_path)
    profiles.save("btc", {"symbol": "BTC/USD", "signals": {"oversold": {"weight": 1.0}},
                          "entry_threshold": 0.3})
    profiles.arm("btc")
    h = {"X-Token": "t"}
    assert c.post("/api/strategies/live-eligible",
                  json={"name": "btc", "eligible": True}, headers=h).status_code == 200
    assert profiles.is_live_eligible("btc") is True


def test_portfolio_settings_get_put(tmp_path):
    c, _, _ = _client(tmp_path)
    assert c.get("/api/portfolio/settings").json()["max_concurrent"] == 5
    r = c.put("/api/portfolio/settings", json={"max_concurrent": 9}, headers={"X-Token": "t"})
    assert r.status_code == 200 and r.json()["max_concurrent"] == 9


def test_per_strategy_flatten(tmp_path):
    c, ctrl, _ = _client(tmp_path)
    assert c.post("/api/control/btc/flatten", headers={"X-Token": "t"}).status_code == 200
    assert ("flatten", "btc") in ctrl.calls


def test_journal_metrics_strategy_filter(tmp_path):
    c, ctrl, _ = _client(tmp_path)
    c.get("/api/journal?strategy=btc"); c.get("/api/metrics?strategy=btc")
    assert ("journal", "btc") in ctrl.calls and ("metrics", "btc") in ctrl.calls
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_web_portfolio.py -q`
Expected: FAIL — new routes 404 / missing.

- [ ] **Step 3: Rewrite `src/swingbot/web.py`**

Replace the entire contents of `src/swingbot/web.py` with:

```python
from __future__ import annotations

import os
import pathlib

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from swingbot.data.market import timeframe_seconds
from swingbot import presets as presets_mod
from swingbot.strategy_search import backtest_profile, search as run_strategy_search

_DIST = str(pathlib.Path(__file__).parent.parent.parent / "frontend" / "dist")


class ProfileBody(BaseModel):
    name: str
    profile: dict


class NameBody(BaseModel):
    name: str


class CredBody(BaseModel):
    key_id: str
    secret_key: str
    base_url: str = "https://paper-api.alpaca.markets"


class ModeBody(BaseModel):
    mode: str


class LiveEligibleBody(BaseModel):
    name: str
    eligible: bool


class PortfolioSettingsBody(BaseModel):
    max_concurrent: int | None = None
    max_total_deployed_frac: float | None = None
    portfolio_daily_loss_limit_pct: float | None = None


class BuildBody(BaseModel):
    symbol: str
    risk: str = "balanced"
    style: str = "swing"
    ai: bool = False


class BacktestBody(BaseModel):
    profile: dict


def create_app(controller, profiles, creds, token: str, store=None, market=None) -> FastAPI:
    app = FastAPI(title="swingbot")

    def require_token(x_token: str | None = Header(default=None)):
        if x_token != token:
            raise HTTPException(status_code=401, detail="bad or missing token")

    # ---- read ----
    @app.get("/api/state")
    def state():
        return controller.status()

    @app.get("/api/journal")
    def journal(strategy: str | None = None):
        return controller.journal(strategy)

    @app.get("/api/metrics")
    def metrics(strategy: str | None = None):
        return controller.metrics(strategy)

    @app.get("/api/candles")
    def candles(symbol: str | None = None, timeframe: str | None = None, limit: int = 500):
        if symbol is None or timeframe is None:
            armed = profiles.list_armed() if profiles else []
            first = (profiles.get(armed[0]) if armed else None) or {}
            symbol = symbol or first.get("symbol")
            timeframe = timeframe or first.get("timeframe", "15m")
        if not symbol:
            return {"symbol": symbol, "timeframe": timeframe, "candles": []}
        limit = max(1, min(limit, 1500))
        if market is not None:
            bars = market.get(symbol, timeframe, limit, max_age=timeframe_seconds(timeframe))
        elif store is not None:
            bars = store.get(symbol, timeframe, limit)
        else:
            bars = []
        return {"symbol": symbol, "timeframe": timeframe, "candles": bars}

    # ---- strategies / arming ----
    @app.get("/api/strategies")
    def list_strategies():
        flags = {f["name"]: f["live_eligible"] for f in profiles.armed_with_flags()}
        out = []
        for name in profiles.list():
            p = profiles.get(name) or {}
            out.append({"name": name, "symbol": p.get("symbol"),
                        "armed": name in flags, "live_eligible": flags.get(name, False)})
        return out

    @app.post("/api/strategies/arm")
    def arm(body: NameBody, _=Depends(require_token)):
        try:
            profiles.arm(body.name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        controller.reload()
        return {"ok": True}

    @app.post("/api/strategies/disarm")
    def disarm(body: NameBody, _=Depends(require_token)):
        controller.flatten(body.name)
        profiles.disarm(body.name)
        controller.reload()
        return {"ok": True}

    @app.post("/api/strategies/live-eligible")
    def live_eligible(body: LiveEligibleBody, _=Depends(require_token)):
        try:
            profiles.set_live_eligible(body.name, body.eligible)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True}

    # ---- portfolio settings ----
    @app.get("/api/portfolio/settings")
    def get_portfolio_settings():
        return profiles.get_portfolio_settings()

    @app.put("/api/portfolio/settings")
    def set_portfolio_settings(body: PortfolioSettingsBody, _=Depends(require_token)):
        patch = {k: v for k, v in body.model_dump().items() if v is not None}
        try:
            profiles.set_portfolio_settings(patch)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        controller.reload()
        return profiles.get_portfolio_settings()

    # ---- profiles CRUD ----
    @app.get("/api/profiles")
    def list_profiles():
        return profiles.list()

    @app.post("/api/profiles")
    def save_profile(body: ProfileBody, _=Depends(require_token)):
        try:
            profiles.save(body.name, body.profile)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True}

    @app.get("/api/profiles/{name}")
    def get_profile(name: str):
        p = profiles.get(name)
        if p is None:
            raise HTTPException(status_code=404, detail=f"no profile {name!r}")
        return {"name": name, "profile": p}

    @app.delete("/api/profiles/{name}")
    def delete_profile(name: str, _=Depends(require_token)):
        profiles.delete(name)
        return {"ok": True}

    # ---- credentials ----
    @app.get("/api/credentials")
    def cred_status():
        return creds.status()

    @app.put("/api/credentials")
    def set_creds(body: CredBody, _=Depends(require_token)):
        creds.set(body.key_id, body.secret_key, body.base_url)
        return {"ok": True}

    # ---- presets / strategy build (unchanged behavior) ----
    def _require_market_ready():
        if market is None or (creds is not None and creds.get() is None):
            raise HTTPException(status_code=400, detail="set Alpaca credentials in Settings first")

    @app.get("/api/presets")
    def list_presets():
        return [{"key": a.key, "name": a.name, "description": a.description,
                 "signals": a.signals, "profile": presets_mod.archetype_profile(a)}
                for a in presets_mod.ARCHETYPES]

    @app.post("/api/strategy/backtest")
    def strategy_backtest(body: BacktestBody, _=Depends(require_token)):
        _require_market_ready()
        try:
            m = backtest_profile(market, body.profile)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"metrics": {k: getattr(m, k, None) for k in
                ("n_trades", "win_rate", "expectancy", "profit_factor", "max_drawdown")}}

    @app.post("/api/strategy/build")
    def strategy_build(body: BuildBody, _=Depends(require_token)):
        _require_market_ready()
        try:
            return run_strategy_search(market, body.symbol, body.risk, body.style, body.ai)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ---- controls (portfolio-level + per-strategy) ----
    @app.post("/api/control/halt")
    def halt(_=Depends(require_token)):
        controller.halt(); return {"ok": True}

    @app.post("/api/control/reset")
    def control_reset(_=Depends(require_token)):
        controller.reset(); return {"ok": True}

    @app.post("/api/control/pause")
    def control_pause(_=Depends(require_token)):
        controller.pause(); return {"ok": True}

    @app.post("/api/control/resume")
    def control_resume(_=Depends(require_token)):
        controller.resume(); return {"ok": True}

    @app.post("/api/control/start")
    def control_start(_=Depends(require_token)):
        try:
            controller.start()
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True}

    @app.post("/api/control/stop")
    def control_stop(_=Depends(require_token)):
        controller.stop(); return {"ok": True}

    @app.post("/api/control/flatten")
    def control_flatten(_=Depends(require_token)):
        controller.flatten(); return {"ok": True}

    @app.post("/api/control/mode")
    def control_mode(body: ModeBody, _=Depends(require_token)):
        ok, reason = controller.set_mode(body.mode)
        return {"ok": ok, "reason": reason}

    @app.post("/api/control/{name}/flatten")
    def control_flatten_one(name: str, _=Depends(require_token)):
        controller.flatten(name); return {"ok": True}

    app.state.controller = controller
    app.state.profiles = profiles
    app.state.creds = creds
    app.state.token = token

    if os.path.isdir(_DIST):
        app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")

    return app
```

- [ ] **Step 4: Run the new portfolio web test**

Run: `.venv/bin/python -m pytest tests/test_web_portfolio.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Update existing web tests affected by the removed active-pointer routes**

Two existing suites assume the old single-active surface and must be migrated to the armed
model.

(a) `tests/test_web_profiles.py` — its `test_profile_crud_and_active` posts to
`/api/profiles/active`, which no longer exists, and its `FakeController` lacks `reload()`.
In its `FakeController`, add:

```python
    def flatten(self, name=None): pass
    def reload(self): pass
```

Replace `test_profile_crud_and_active` with `test_profile_crud_and_arm`:

```python
def test_profile_crud_and_arm(tmp_path):
    c, _ = _client(tmp_path)
    h = {"X-Token": "tok"}
    body = {"name": "trx", "profile": {"symbol": "TRX/USD",
            "signals": {"oversold": {"weight": 1.0}}, "entry_threshold": 0.3}}
    assert c.post("/api/profiles", json=body, headers=h).status_code == 200
    assert "trx" in c.get("/api/profiles").json()
    assert c.post("/api/strategies/arm", json={"name": "trx"}, headers=h).status_code == 200
    armed = [s for s in c.get("/api/strategies").json() if s["armed"]]
    assert any(s["name"] == "trx" for s in armed)
```

(b) `tests/test_candle_store.py` — its `_FakeProfiles` only implements `get_active`, but the
candles endpoint now reads `list_armed()`/`get()`. Replace the `_FakeProfiles` class with:

```python
class _FakeProfiles:
    def list_armed(self): return ["trx"]
    def get(self, name): return {"symbol": "TRX/USD", "timeframe": "15m"}
```

(Leave `tests/test_web_credentials.py` and `tests/test_web_strategy.py` unchanged — they pass
`profiles=None` and exercise only credentials/presets/build routes, which don't touch the
armed model.)

- [ ] **Step 6: Update `tests/test_web_control.py` and `tests/test_web_read.py` to the new controller**

These two suites use a `controller` whose `journal()/metrics()` now accept an optional
`strategy` arg and whose `status()` is portfolio-shaped. Update their fake controllers:

In `tests/test_web_read.py`, change `FakeController` methods:

```python
    def status(self): return {"portfolio": {"mode": "paper", "open_positions": 0}, "strategies": []}
    def journal(self, strategy=None): return [{"pnl": 1.0}]
    def metrics(self, strategy=None): return {"n_trades": 1, "expectancy": 1.0}
    def flatten(self, name=None): pass
    def reload(self): pass
```

and update `test_state_ok` to assert on the new shape:

```python
def test_state_ok():
    r = _client().get("/api/state")
    assert r.status_code == 200 and r.json()["portfolio"]["mode"] == "paper"
```

In `tests/test_web_control.py`, give `RecordingController` the new signatures:

```python
    def journal(self, strategy=None): return []
    def metrics(self, strategy=None): return {}
    def flatten(self, name=None): self.calls.append(("flatten", name))
    def reload(self): self.calls.append("reload")
```

- [ ] **Step 7: Run all updated + unchanged web suites**

Run: `.venv/bin/python -m pytest tests/test_web_read.py tests/test_web_control.py tests/test_web_profiles.py tests/test_web_credentials.py tests/test_web_strategy.py tests/test_candle_store.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/swingbot/web.py tests/test_web_portfolio.py tests/test_web_read.py tests/test_web_control.py tests/test_web_profiles.py tests/test_candle_store.py
git commit -m "feat(web): portfolio API surface (state, arming, live-eligible, settings, per-strategy controls)"
```

---

### Task 3: Wire the supervisor into webmain + warm all armed symbols

**Files:**
- Modify: `src/swingbot/webmain.py`
- Modify: `src/swingbot/data/poller.py`
- Test: `tests/test_poller_armed.py` (new)

- [ ] **Step 1: Write the failing test for the poller**

Create `tests/test_poller_armed.py`:

```python
from swingbot.data.poller import CandlePoller


class FakeMarket:
    def __init__(self): self.calls = []
    def refresh_many(self, symbols, timeframe, lookback=None):
        self.calls.append((tuple(sorted(symbols)), timeframe)); return len(symbols)


class FakeProfiles:
    def __init__(self, profs): self._p = profs
    def list_armed(self): return list(self._p)
    def get(self, name): return self._p[name]


def test_poll_once_warms_all_armed_grouped_by_timeframe():
    market = FakeMarket()
    profiles = FakeProfiles({
        "btc": {"symbol": "BTC/USD", "timeframe": "15m"},
        "eth": {"symbol": "ETH/USD", "timeframe": "15m"},
        "sol": {"symbol": "SOL/USD", "timeframe": "1h"},
    })
    poller = CandlePoller(market, profiles)
    n = poller.poll_once()
    assert n == 3
    assert (("BTC/USD", "ETH/USD"), "15m") in market.calls
    assert (("SOL/USD",), "1h") in market.calls
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_poller_armed.py -q`
Expected: FAIL — current `poll_once` reads `get_active()` and calls `refresh`, not
`refresh_many` over armed symbols.

- [ ] **Step 3: Update `CandlePoller.poll_once`**

In `src/swingbot/data/poller.py`, replace the `poll_once` method with:

```python
    def poll_once(self) -> int:
        names = self.profiles.list_armed()
        by_tf: dict = {}
        for name in names:
            pdict = self.profiles.get(name)
            if not pdict or not pdict.get("symbol"):
                continue
            by_tf.setdefault(pdict.get("timeframe", "15m"), set()).add(pdict["symbol"])
        total = 0
        for tf, syms in by_tf.items():
            total += self.market.refresh_many(sorted(syms), tf)
        return total
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_poller_armed.py -q`
Expected: PASS.

- [ ] **Step 5: Rewrite `webmain.py` to use the supervisor**

Replace the `main()` function body in `src/swingbot/webmain.py`. The new file:

```python
from __future__ import annotations

import os
import secrets

import uvicorn

from swingbot.credentials import CredentialStore
from swingbot.data.market import MarketData
from swingbot.data.poller import CandlePoller
from swingbot.data.store import CandleStore
from swingbot.profiles import ProfileStore
from swingbot.supervisor import PortfolioSupervisor
from swingbot.web import create_app

HOST = os.environ.get("SWINGBOT_HOST", "127.0.0.1")
DATA_DIR = os.environ.get("SWINGBOT_DATA_DIR", os.path.expanduser("~/.swingbot"))


def _ensure_token(path: str) -> str:
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    tok = secrets.token_urlsafe(24)
    with open(path, "w") as f:
        f.write(tok)
    os.chmod(path, 0o600)
    return tok


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    token = _ensure_token(os.path.join(DATA_DIR, "token"))
    profiles = ProfileStore(os.path.join(DATA_DIR, "swingbot.db"))
    creds = CredentialStore(os.path.join(DATA_DIR, "credentials.json"))
    store = CandleStore(os.path.join(DATA_DIR, "candles.db"))
    market = MarketData(store, creds)
    supervisor = PortfolioSupervisor(
        profiles=profiles, creds=creds,
        state_db=os.path.join(DATA_DIR, "swingbot.db"), market=market)
    poller = CandlePoller(market, profiles)        # keeps all armed symbols warm for charts
    poller.start()
    app = create_app(controller=supervisor, profiles=profiles, creds=creds,
                     token=token, store=store, market=market)
    print(f"[swingbot-web] token: {token}")
    print(f"[swingbot-web] http://{HOST}:8000")
    uvicorn.run(app, host=HOST, port=8000)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Verify the env-var tests still pass**

Run: `.venv/bin/python -m pytest tests/test_web_read.py -q`
Expected: PASS (`test_webmain_respects_swingbot_host_env` / `_data_dir_env` reload `webmain`
and only read `HOST`/`DATA_DIR`, which are unchanged).

- [ ] **Step 7: Full suite + manual smoke**

Run: `.venv/bin/python -m pytest -q`
Expected: all green.

Manual smoke (optional, needs no Alpaca creds): `SWINGBOT_DATA_DIR=/tmp/sb-smoke swingbot-web`
should start, print a token, and serve `GET /api/state` returning
`{"portfolio": {...}, "strategies": []}` (empty until profiles are armed).

- [ ] **Step 8: Commit**

```bash
git add src/swingbot/webmain.py src/swingbot/data/poller.py tests/test_poller_armed.py
git commit -m "feat(web): run PortfolioSupervisor in webmain; poller warms all armed symbols"
```

---

## Self-Review Notes (for the implementer)

- **Spec coverage:** §7 every endpoint — `/api/state` (Task 2), strategies/arm/disarm/
  live-eligible (Task 2), portfolio settings (Task 2), portfolio + per-strategy controls
  (Tasks 1-2), aggregate journal/metrics with filter (Tasks 1-2), poller warming (Task 3).
- **Removed routes:** the single-active `/api/profiles/active` GET/POST are gone (replaced
  by the armed model). `service.py` (`BotService`) is now unused by `webmain` but left in
  the tree; `tests/test_service.py` only asserts the `BotController` Protocol shape and is
  unaffected. Leave `service.py` for now; a later cleanup can remove it.
- **Known limitation:** in-memory journals reset on `reload()` (arming/disarming), matching
  the pre-existing single-strategy behavior where journals were never persisted. Persisting
  trades is out of scope (future archive work).
- **Type consistency:** controller methods `journal(strategy=None)`, `metrics(strategy=None)`,
  `flatten(name=None)`, `reload()`, `set_mode(mode)->(bool,str)` match Task 1's supervisor
  and the Phase-3 frontend's expectations.
