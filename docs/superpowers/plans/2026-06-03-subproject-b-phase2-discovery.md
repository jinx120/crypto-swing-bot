# Auto-Strategy Discovery (Sub-project B Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sweep every universe coin across the non-AI archetypes over the deep historical archive, rank by expectancy, flag which are "eligible now," and let the user arm a winner in one click (paper).

**Architecture:** A pure-compute `DiscoveryEngine` (`src/swingbot/discovery.py`) loads each symbol's deep candle history once, runs all archetypes through the existing `run_backtest`, and ranks the rows. The web layer mirrors the Phase 1 archive pattern: a daemon-thread background sweep writes a JSON cache, `GET /api/discovery` serves it, `POST /api/discovery/refresh` triggers it, `POST /api/discovery/arm` saves+arms a row. A `Discover` page renders the ranked list with a one-click arm.

**Tech Stack:** Python 3 / FastAPI / pandas / pytest (backend); React + Vite (frontend). Venv: `.venv/bin/python`. Tests run with `.venv/bin/python -m pytest`.

**Conventions to follow:**
- Mirror `src/swingbot/strategy_search.py` (reuse `_df_from_market`, `metrics_dict`) and the archive endpoints in `src/swingbot/web.py` (daemon thread + `app.state`, token guard via `Depends(require_token)`).
- Test style mirrors `tests/test_strategy_search.py` (a `FakeMarket` with `.get(symbol, timeframe, limit, max_age=None)`) and `tests/test_web_strategy.py` (`TestClient`, `X-Token: t`).
- Scope each `git add` to the files in the task; the working tree carries unrelated uncommitted work — do not `git add -A`.

---

### Task 1: Pure helpers — `good_history`, `windows_for`, `_apply_window`

**Files:**
- Create: `src/swingbot/discovery.py`
- Test: `tests/test_discovery.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_discovery.py
import pandas as pd

from swingbot.discovery import good_history, windows_for, _apply_window, MIN_TRADES


def test_good_history_requires_trades_expectancy_profit_factor():
    assert good_history({"n_trades": 25, "expectancy": 0.5, "profit_factor": 1.3})
    assert not good_history({"n_trades": 5, "expectancy": 0.5, "profit_factor": 1.3})   # too few
    assert not good_history({"n_trades": 25, "expectancy": -0.1, "profit_factor": 1.3}) # losing
    assert not good_history({"n_trades": 25, "expectancy": 0.5, "profit_factor": 0.9})  # pf<=1
    assert not good_history({"n_trades": None, "expectancy": None, "profit_factor": None})
    assert MIN_TRADES == 20


def test_windows_for_only_offers_covered_windows():
    day = 86400
    short = windows_for({"min_ts": 1_700_000_000, "max_ts": 1_700_000_000 + 10 * day})
    assert [w["key"] for w in short] == ["full"]                 # 10 days -> full only
    deep = windows_for({"min_ts": 1_700_000_000, "max_ts": 1_700_000_000 + 400 * day})
    assert [w["key"] for w in deep] == ["full", "last_1y", "last_90d", "last_30d"]
    assert windows_for({}) == [{"key": "full", "label": "Full history", "days": None}]


def test_apply_window_slices_trailing_days():
    ts = pd.date_range("2024-01-01", periods=200, freq="D", tz="UTC")
    df = pd.DataFrame({"ts": ts, "close": range(200)})
    full = _apply_window(df, "full")
    last30 = _apply_window(df, "last_30d")
    assert len(full) == 200
    assert 29 <= len(last30) <= 31                               # ~30 trailing days
    assert last30["ts"].iloc[-1] == df["ts"].iloc[-1]
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_discovery.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.discovery'`.

- [x] **Step 3: Write minimal implementation**

```python
# src/swingbot/discovery.py
from __future__ import annotations

import json
import os
import time

import pandas as pd

from swingbot.backtest import run_backtest
from swingbot.confluence import ConfluenceEngine, build_signals
from swingbot.presets import ARCHETYPES, STYLE, archetype_profile
from swingbot.profile import StrategyProfile
from swingbot.regime import RegimeFilter
from swingbot.strategy_search import _df_from_market, metrics_dict
from swingbot.types import MarketContext

MIN_TRADES = 20


def good_history(metrics: dict) -> bool:
    """Ranked-well predicate: enough trades, positive expectancy, profit factor > 1."""
    nt = metrics.get("n_trades") or 0
    exp = metrics.get("expectancy") or 0
    pf = metrics.get("profit_factor") or 0
    return nt >= MIN_TRADES and exp > 0 and pf > 1


_WINDOW_DEFS = [
    ("full", "Full history", None),
    ("last_1y", "Last 1y", 365),
    ("last_90d", "Last 90d", 90),
    ("last_30d", "Last 30d", 30),
]
_WINDOW_DAYS = {key: days for key, _label, days in _WINDOW_DEFS}


def windows_for(coverage: dict) -> list[dict]:
    """Selectable windows derived from store coverage, so each always has data."""
    min_ts, max_ts = coverage.get("min_ts"), coverage.get("max_ts")
    span_days = ((max_ts - min_ts) / 86400) if (min_ts and max_ts) else 0
    return [{"key": k, "label": lbl, "days": d}
            for k, lbl, d in _WINDOW_DEFS if d is None or span_days >= d]


def _apply_window(df: pd.DataFrame, window_key: str) -> pd.DataFrame:
    days = _WINDOW_DAYS.get(window_key)
    if not days:
        return df
    cutoff = df["ts"].iloc[-1] - pd.Timedelta(days=days)
    return df[df["ts"] >= cutoff].reset_index(drop=True)
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_discovery.py -q`
Expected: PASS (3 passed).

- [x] **Step 5: Commit**

```bash
git add src/swingbot/discovery.py tests/test_discovery.py
git commit -m "feat(discovery): good_history + coverage-derived windows helpers"
```

---

### Task 2: `DiscoveryEngine.sweep` — the ranked cross-universe sweep

**Files:**
- Modify: `src/swingbot/discovery.py`
- Test: `tests/test_discovery.py`

- [x] **Step 1: Write the failing test**

Add to `tests/test_discovery.py` (top, after imports add `from types import SimpleNamespace` and `import swingbot.discovery as ds` and `from swingbot.discovery import DiscoveryEngine`):

```python
def _bars(n=300, start=100.0, up=True):
    out, p, t0 = [], start, 1_700_000_000
    for i in range(n):
        p *= (1.001 if i % 3 else 0.999) if up else (0.999 if i % 3 else 1.001)
        out.append({"time": t0 + i * 900, "open": p, "high": p * 1.01,
                    "low": p * 0.99, "close": p * 1.002, "volume": 1000 + i})
    return out


class FakeMarket:
    def __init__(self, bars):
        self._bars = bars
    def get(self, symbol, timeframe, limit=500, max_age=None):
        return self._bars[-limit:]


def _fake_metrics(expectancy, n_trades=25, pf=1.5, win_rate=0.6):
    return SimpleNamespace(n_trades=n_trades, win_rate=win_rate, expectancy=expectancy,
                           profit_factor=pf, max_drawdown=0.1, avg_win=1.0, avg_loss=-0.5,
                           total_return=0.2)


def test_sweep_ranks_rows_by_expectancy(monkeypatch):
    # each archetype gets a deterministic expectancy keyed off its entry_threshold
    monkeypatch.setattr(ds, "run_backtest",
                        lambda df, profile, benchmark_df=None: ([], _fake_metrics(1.0 - profile.entry_threshold)))
    rows = DiscoveryEngine(FakeMarket(_bars())).sweep(["BTC/USD", "ETH/USD"], window_key="full")
    exps = [r["metrics"]["expectancy"] for r in rows if r["metrics"]]
    assert exps == sorted(exps, reverse=True)                       # ranked desc
    assert {r["symbol"] for r in rows} == {"BTC/USD", "ETH/USD"}
    assert all(r["error"] is None for r in rows)


def test_sweep_eligibility_needs_good_history_and_regime(monkeypatch):
    monkeypatch.setattr(ds, "run_backtest",
                        lambda df, profile, benchmark_df=None: ([], _fake_metrics(0.8)))
    up = DiscoveryEngine(FakeMarket(_bars(up=True))).sweep(["BTC/USD"], window_key="full")
    down = DiscoveryEngine(FakeMarket(_bars(up=False))).sweep(["BTC/USD"], window_key="full")
    assert any(r["eligible_now"] for r in up)        # good history + uptrend regime
    assert all(not r["eligible_now"] for r in down)  # downtrend blocks eligibility
    assert all(isinstance(r["fires_now"], bool) for r in up)


def test_sweep_isolates_per_symbol_errors(monkeypatch):
    monkeypatch.setattr(ds, "run_backtest",
                        lambda df, profile, benchmark_df=None: ([], _fake_metrics(0.5)))
    short = FakeMarket(_bars(n=10))                  # <30 bars -> InsufficientData on load
    rows = DiscoveryEngine(short).sweep(["BTC/USD"], window_key="full")
    assert len(rows) == 1 and rows[0]["metrics"] is None and rows[0]["error"]


def test_sweep_respects_max_symbols(monkeypatch):
    monkeypatch.setattr(ds, "run_backtest",
                        lambda df, profile, benchmark_df=None: ([], _fake_metrics(0.5)))
    rows = DiscoveryEngine(FakeMarket(_bars())).sweep(
        ["BTC/USD", "ETH/USD", "SOL/USD"], window_key="full", max_symbols=1)
    assert {r["symbol"] for r in rows} == {"BTC/USD"}
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_discovery.py -q`
Expected: FAIL — `ImportError: cannot import name 'DiscoveryEngine'`.

- [x] **Step 3: Write minimal implementation**

Append to `src/swingbot/discovery.py`:

```python
def _rank_key(row: dict):
    m = row.get("metrics") or {}
    return (m.get("expectancy") or -1e9, m.get("win_rate") or 0, m.get("n_trades") or 0)


class DiscoveryEngine:
    """Sweeps symbols across the non-AI archetypes over the deep archive,
    ranking by expectancy. Pure compute — caching/threading live in web.py."""

    def __init__(self, market, lookback: int = 100_000):
        self.market = market
        self.lookback = lookback

    def _candidates(self, symbol: str, style: str) -> list[tuple]:
        return [(a.key, a.name, archetype_profile(a, symbol, style))
                for a in ARCHETYPES if not a.needs_ai]

    def _now_state(self, profile: StrategyProfile, df, bench) -> tuple[bool, bool, str]:
        ctx = MarketContext(candles=df, benchmark=bench)
        regime = RegimeFilter(profile)
        reg = regime.evaluate(ctx)
        engine = ConfluenceEngine(build_signals(profile), profile)
        return regime.permits_entry(reg.regime), bool(engine.evaluate(ctx).passed), reg.regime.value

    def _err_row(self, symbol, key, label, profile, err) -> dict:
        return {"symbol": symbol, "archetype": key, "label": label, "profile": profile,
                "metrics": None, "eligible_now": False, "fires_now": False,
                "regime": None, "error": str(err)}

    def sweep(self, symbols, window_key="full", style="swing", max_symbols=50) -> list[dict]:
        timeframe = STYLE[style]["timeframe"]
        rows: list[dict] = []
        for symbol in list(symbols)[:max_symbols]:
            try:
                df = _apply_window(
                    _df_from_market(self.market, symbol, timeframe, self.lookback), window_key)
            except Exception as e:                       # InsufficientData / load failure
                rows.append(self._err_row(symbol, None, None, None, e))
                continue
            bench = None
            for key, name, profile_dict in self._candidates(symbol, style):
                needs_bench = "relative_strength" in profile_dict["signals"]
                try:
                    if needs_bench and bench is None:
                        bench = _apply_window(
                            _df_from_market(self.market, profile_dict["benchmark_symbol"],
                                            timeframe, self.lookback), window_key)
                    b = bench if needs_bench else None
                    profile = StrategyProfile.from_dict(profile_dict)
                    _trades, m = run_backtest(df, profile, benchmark_df=b)
                    mrow = metrics_dict(m)
                    regime_ok, fires, regime = self._now_state(profile, df, b)
                    rows.append({"symbol": symbol, "archetype": key, "label": name,
                                 "profile": profile_dict, "metrics": mrow,
                                 "eligible_now": good_history(mrow) and regime_ok,
                                 "fires_now": fires, "regime": regime, "error": None})
                except Exception as e:                   # one bad candidate never aborts
                    rows.append(self._err_row(symbol, key, name, profile_dict, e))
        rows.sort(key=_rank_key, reverse=True)
        return rows
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_discovery.py -q`
Expected: PASS (7 passed). If `test_sweep_eligibility...` is flaky on the down series, confirm the down generator trends below its `regime_ma_period` SMA — it does (mostly-down random walk over 300 bars).

- [x] **Step 5: Commit**

```bash
git add src/swingbot/discovery.py tests/test_discovery.py
git commit -m "feat(discovery): DiscoveryEngine.sweep — ranked cross-universe backtest sweep"
```

---

### Task 3: Cache load/save helpers (atomic JSON)

**Files:**
- Modify: `src/swingbot/discovery.py`
- Test: `tests/test_discovery.py`

- [x] **Step 1: Write the failing test**

Add to `tests/test_discovery.py`:

```python
def test_cache_roundtrip_and_missing(tmp_path):
    from swingbot.discovery import load_cache, save_cache
    p = str(tmp_path / "discovery.json")
    assert load_cache(p) is None                       # missing -> None
    data = {"status": "idle", "computed_at": 123, "window": "full", "rows": [{"symbol": "BTC/USD"}]}
    save_cache(p, data)
    assert load_cache(p) == data
    (tmp_path / "bad.json").write_text("{not json")
    assert load_cache(str(tmp_path / "bad.json")) is None   # corrupt -> None, never raises
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_discovery.py::test_cache_roundtrip_and_missing -q`
Expected: FAIL — `ImportError: cannot import name 'load_cache'`.

- [x] **Step 3: Write minimal implementation**

Append to `src/swingbot/discovery.py`:

```python
def load_cache(path: str) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_cache(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)                              # atomic on POSIX
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_discovery.py -q`
Expected: PASS (8 passed).

- [x] **Step 5: Commit**

```bash
git add src/swingbot/discovery.py tests/test_discovery.py
git commit -m "feat(discovery): atomic JSON cache load/save helpers"
```

---

### Task 4: Web — `GET /api/discovery` + `GET /api/discovery/windows` + wiring

**Files:**
- Modify: `src/swingbot/web.py` (imports near top; `create_app` signature line 66; universe helper refactor ~line 160; new endpoints; startup cache load near the archive wiring ~line 322)
- Test: `tests/test_web_discovery.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_web_discovery.py
from fastapi.testclient import TestClient

from swingbot.web import create_app


def _bars(n=300, start=100.0):
    out, p, t0 = [], start, 1_700_000_000
    for i in range(n):
        p *= 1.001 if i % 3 else 0.999
        out.append({"time": t0 + i * 900, "open": p, "high": p * 1.01,
                    "low": p * 0.99, "close": p * 1.002, "volume": 1000 + i})
    return out


class FakeMarket:
    def get(self, symbol, timeframe, limit=500, max_age=None):
        return _bars()[-limit:]


class FakeStore:
    def symbols(self):
        return [{"symbol": "BTC/USD", "timeframe": "15m"}]
    def coverage(self, symbol, timeframe):
        day = 86400
        return {"min_ts": 1_700_000_000, "max_ts": 1_700_000_000 + 400 * day, "count": 38000}


class _Ctl:
    def status(self): return {}
    def reload(self): pass


def _client(**kw):
    from swingbot.discovery import DiscoveryEngine
    app = create_app(_Ctl(), profiles=None, creds=None, token="t",
                     store=FakeStore(), market=FakeMarket(),
                     discovery=DiscoveryEngine(FakeMarket()), **kw)
    return TestClient(app)


def test_discovery_starts_empty():
    r = _client().get("/api/discovery")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "idle" and body["rows"] == [] and body["computed_at"] is None


def test_discovery_windows_from_coverage():
    r = _client().get("/api/discovery/windows")
    assert r.status_code == 200
    assert [w["key"] for w in r.json()] == ["full", "last_1y", "last_90d", "last_30d"]
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_web_discovery.py -q`
Expected: FAIL — `create_app()` got an unexpected keyword argument `discovery`.

- [x] **Step 3: Write minimal implementation**

In `src/swingbot/web.py`, add the discovery import alongside the other `swingbot` imports near the top of the file:

```python
import swingbot.discovery as discovery_mod
```

Confirm `import time` is present near the top (add it if missing — `discovery_refresh` in Task 5 needs it).

Change the `create_app` signature (line 66) to add two params:

```python
def create_app(controller, profiles, creds, token: str, store=None, market=None,
               backfiller=None, discovery=None, discovery_cache_path=None) -> FastAPI:
```

Refactor the universe resolution into a reusable helper. Replace the existing `universe()` endpoint body (lines ~162-177) so the live-pairs logic lives in a helper both endpoints can call:

```python
    # ---- universe / watchlist ----
    _universe_cache: dict = {}

    def _resolve_universe():
        if _universe_cache.get("symbols"):
            return _universe_cache["symbols"]
        symbols = fallback_universe()
        try:
            cr = creds.get() if creds is not None else None
            if cr is not None:
                broker = AlpacaBroker(cr.key_id, cr.secret_key, paper=True)
                live = broker.list_usd_pairs()
                if live:
                    symbols = live
                    _universe_cache["symbols"] = live
        except Exception:
            pass  # fall back to static list
        return symbols

    @app.get("/api/universe")
    def universe():
        return {"symbols": _resolve_universe()}
```

Add the two read endpoints (put them with the other read endpoints, e.g. just before the `# ---- archive` section ~line 294):

```python
    # ---- discovery (auto-strategy sweep) ----
    @app.get("/api/discovery")
    def get_discovery():
        return app.state.discovery

    @app.get("/api/discovery/windows")
    def discovery_windows():
        cov: dict = {}
        if store is not None:
            syms = store.symbols()
            pick = next((s for s in syms if s["symbol"] == "BTC/USD"),
                        syms[0] if syms else None)
            if pick:
                cov = store.coverage(pick["symbol"], pick["timeframe"])
        return discovery_mod.windows_for(cov)
```

Initialize discovery state + load the cache near the archive wiring (after `app.state.archive_config = ...`, ~line 322):

```python
    app.state.discovery = {"status": "idle", "computed_at": None, "window": None,
                           "scope": None, "error": None, "rows": []}
    if discovery_cache_path:
        cached = discovery_mod.load_cache(discovery_cache_path)
        if cached:
            app.state.discovery = cached
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_web_discovery.py -q`
Expected: PASS (2 passed).

- [x] **Step 5: Commit**

```bash
git add src/swingbot/web.py tests/test_web_discovery.py
git commit -m "feat(web): GET /api/discovery + /windows, universe helper refactor, cache load"
```

---

### Task 5: Web — `POST /api/discovery/refresh` (background sweep)

**Files:**
- Modify: `src/swingbot/web.py` (request model near the other `BaseModel`s ~line 55; endpoint in the discovery section)
- Test: `tests/test_web_discovery.py`

- [x] **Step 1: Write the failing test**

Add to `tests/test_web_discovery.py`:

```python
def test_refresh_requires_token():
    assert _client().post("/api/discovery/refresh", json={}).status_code == 401


def test_refresh_runs_sweep_and_caches(tmp_path):
    c = _client(discovery_cache_path=str(tmp_path / "discovery.json"))
    # seed a tiny universe by monkeypatching the resolver via watchlist scope
    r = c.post("/api/discovery/refresh", json={"scope": "watchlist", "window": "full"},
               headers={"X-Token": "t"})
    assert r.status_code == 200 and r.json()["started"] is True


def test_refresh_guards_against_concurrent_sweep():
    c = _client()
    c.app.state.discovery = {**c.app.state.discovery, "status": "computing"}
    r = c.post("/api/discovery/refresh", json={}, headers={"X-Token": "t"})
    assert r.json() == {"started": False, "status": "computing"}
```

Note: `test_refresh_runs_sweep_and_caches` uses `scope: "watchlist"`; with `profiles=None` the resolver yields `[]`, so the sweep is a no-op that still flips status back to `idle` and writes the cache — exercising the thread path without needing a populated store.

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_web_discovery.py -k refresh -q`
Expected: FAIL — 404 (route not defined) / `started` missing.

- [x] **Step 3: Write minimal implementation**

Add the request model next to the other `BaseModel`s (after `BacktestBody`, ~line 64) in `src/swingbot/web.py`:

```python
class DiscoveryRefreshBody(BaseModel):
    window: str = "full"
    scope: str = "universe"
    max_symbols: int = 50
```

Add the endpoint in the discovery section (after `discovery_windows`):

```python
    @app.post("/api/discovery/refresh")
    def discovery_refresh(body: DiscoveryRefreshBody, _=Depends(require_token)):
        if discovery is None:
            raise HTTPException(status_code=503,
                                detail="discovery is not configured on this server")
        if app.state.discovery.get("status") == "computing":
            return {"started": False, "status": "computing"}
        if body.scope == "watchlist":
            symbols = profiles.get_watchlist() if profiles is not None else []
        else:
            symbols = _resolve_universe()
        app.state.discovery = {**app.state.discovery, "status": "computing", "error": None}

        def job():
            try:
                rows = discovery.sweep(symbols, window_key=body.window,
                                       max_symbols=body.max_symbols)
                result = {"status": "idle", "error": None, "computed_at": int(time.time()),
                          "window": body.window, "scope": body.scope, "rows": rows}
                app.state.discovery = result
                if discovery_cache_path:
                    discovery_mod.save_cache(discovery_cache_path, result)
            except Exception as e:   # a sweep failure must never touch live trading
                app.state.discovery = {**app.state.discovery, "status": "idle",
                                       "error": str(e)}
                print(f"[discovery] {e}")

        threading.Thread(target=job, daemon=True).start()
        return {"started": True}
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_web_discovery.py -q`
Expected: PASS (5 passed). (`threading` is already imported in `web.py` for the archive endpoint.)

- [x] **Step 5: Commit**

```bash
git add src/swingbot/web.py tests/test_web_discovery.py
git commit -m "feat(web): POST /api/discovery/refresh — background sweep + cache write"
```

---

### Task 6: Web — `POST /api/discovery/arm` (save + arm, paper)

**Files:**
- Modify: `src/swingbot/web.py` (request model + endpoint in the discovery section)
- Test: `tests/test_web_discovery.py`

- [x] **Step 1: Write the failing test**

Add to `tests/test_web_discovery.py` (and at the top add `from swingbot.profile import StrategyProfile`):

```python
class FakeProfiles:
    def __init__(self):
        self.saved, self.armed, self.eligible = {}, [], {}
    def save(self, name, profile): self.saved[name] = profile
    def arm(self, name): self.armed.append(name)
    def set_live_eligible(self, name, eligible): self.eligible[name] = eligible
    def get_watchlist(self): return []


def test_arm_saves_and_arms_reconstructable_profile():
    from swingbot.discovery import DiscoveryEngine
    profs = FakeProfiles()
    app = create_app(_Ctl(), profiles=profs, creds=None, token="t",
                     store=FakeStore(), market=FakeMarket(),
                     discovery=DiscoveryEngine(FakeMarket()))
    c = TestClient(app)
    r = c.post("/api/discovery/arm",
               json={"symbol": "BTC/USD", "archetype": "aggressive"},
               headers={"X-Token": "t"})
    assert r.status_code == 200
    name = r.json()["name"]
    assert name == "disc-btcusd-aggressive"
    assert name in profs.armed and profs.eligible[name] is True
    StrategyProfile.from_dict(profs.saved[name])        # round-trips, valid profile
    assert profs.saved[name]["symbol"] == "BTC/USD"


def test_arm_rejects_unknown_archetype():
    from swingbot.discovery import DiscoveryEngine
    app = create_app(_Ctl(), profiles=FakeProfiles(), creds=None, token="t",
                     store=FakeStore(), market=FakeMarket(),
                     discovery=DiscoveryEngine(FakeMarket()))
    r = TestClient(app).post("/api/discovery/arm",
                             json={"symbol": "BTC/USD", "archetype": "nope"},
                             headers={"X-Token": "t"})
    assert r.status_code == 400
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_web_discovery.py -k arm -q`
Expected: FAIL — 404 (route not defined).

- [x] **Step 3: Write minimal implementation**

Add the request model next to `DiscoveryRefreshBody`:

```python
class DiscoveryArmBody(BaseModel):
    symbol: str
    archetype: str
    window: str | None = None
```

Add the endpoint in the discovery section. `presets_mod` is already imported in `web.py` (used by `/api/presets`):

```python
    @app.post("/api/discovery/arm")
    def discovery_arm(body: DiscoveryArmBody, _=Depends(require_token)):
        arch = next((a for a in presets_mod.ARCHETYPES if a.key == body.archetype), None)
        if arch is None:
            raise HTTPException(status_code=400,
                                detail=f"unknown archetype {body.archetype!r}")
        profile = presets_mod.archetype_profile(arch, body.symbol, "swing")
        name = f"disc-{body.symbol.replace('/', '').lower()}-{body.archetype}"
        try:
            profiles.save(name, profile)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        profiles.arm(name)
        profiles.set_live_eligible(name, True)
        controller.reload()
        return {"ok": True, "name": name}
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_web_discovery.py -q`
Expected: PASS (7 passed).

- [x] **Step 5: Commit**

```bash
git add src/swingbot/web.py tests/test_web_discovery.py
git commit -m "feat(web): POST /api/discovery/arm — save + arm a discovered strategy (paper)"
```

---

### Task 7: Wire the engine into the running server

**Files:**
- Modify: `src/swingbot/webmain.py` (import; construct engine; pass to `create_app` at lines 50-51)

- [x] **Step 1: Add the import**

In `src/swingbot/webmain.py`, add to the `swingbot` imports:

```python
from swingbot.discovery import DiscoveryEngine
```

- [x] **Step 2: Construct the engine and pass it through**

Replace the `create_app(...)` call (lines 50-51) with:

```python
    discovery = DiscoveryEngine(market)
    app = create_app(controller=supervisor, profiles=profiles, creds=creds,
                     token=token, store=store, market=market, backfiller=backfiller,
                     discovery=discovery,
                     discovery_cache_path=os.path.join(DATA_DIR, "discovery.json"))
```

- [x] **Step 3: Verify the module imports cleanly**

Run: `.venv/bin/python -c "import swingbot.webmain"`
Expected: no output, exit 0 (no ImportError / SyntaxError).

- [x] **Step 4: Commit**

```bash
git add src/swingbot/webmain.py
git commit -m "feat(web): wire DiscoveryEngine + discovery.json cache into webmain"
```

---

### Task 8: Frontend API client methods

**Files:**
- Modify: `frontend/src/api.js` (append before the closing `}` of the `api` object, after the universe/watchlist block)

- [x] **Step 1: Add the client methods**

In `frontend/src/api.js`, after the `setWatchlist` line, add:

```javascript
  // --- discovery ---
  getDiscovery: () => req('GET', '/api/discovery'),
  discoveryWindows: () => req('GET', '/api/discovery/windows'),
  refreshDiscovery: (body) => req('POST', '/api/discovery/refresh', body),
  armDiscovery: (symbol, archetype, window) =>
    req('POST', '/api/discovery/arm', { symbol, archetype, window }),
```

- [x] **Step 2: Verify the frontend still builds**

Run: `cd frontend && npm run build`
Expected: build succeeds (no syntax error).

- [x] **Step 3: Commit**

```bash
git add frontend/src/api.js
git commit -m "feat(ui): api client methods for discovery endpoints"
```

---

### Task 9: Frontend `Discover` page + nav tab + styles

**Files:**
- Create: `frontend/src/pages/Discover.jsx`
- Modify: `frontend/src/App.jsx` (import ~line 6; nav button ~line 45; render branch ~line 65)
- Modify: `frontend/src/theme.css` (append the discovery styles)

- [x] **Step 1: Create the page component**

```jsx
// frontend/src/pages/Discover.jsx
import { useEffect, useState, useCallback } from 'react'
import { api } from '../api.js'

function fmtPct(x) { return x == null ? '—' : `${(x * 100).toFixed(1)}%` }
function fmtNum(x) { return x == null ? '—' : Number(x).toFixed(2) }
function ago(ts) {
  if (!ts) return 'never'
  const m = Math.round((Date.now() / 1000 - ts) / 60)
  return m < 1 ? 'just now' : `${m}m ago`
}
function expTier(x) {
  if (x == null) return ''
  if (x > 0.5) return 'tier-good'
  if (x > 0) return 'tier-ok'
  return 'tier-bad'
}

export default function Discover() {
  const [data, setData] = useState({ status: 'idle', rows: [], computed_at: null })
  const [windows, setWindows] = useState([{ key: 'full', label: 'Full history' }])
  const [window, setWindow] = useState('full')
  const [scope, setScope] = useState('universe')

  const load = useCallback(async () => {
    try { setData(await api.getDiscovery()) } catch { /* keep prior */ }
  }, [])

  useEffect(() => {
    load()
    api.discoveryWindows().then(setWindows).catch(() => {})
  }, [load])

  // poll while a sweep is computing
  useEffect(() => {
    if (data.status !== 'computing') return
    const id = setInterval(load, 2000)
    return () => clearInterval(id)
  }, [data.status, load])

  const refresh = async () => {
    await api.refreshDiscovery({ window, scope })
    load()
  }

  const arm = async (row) => {
    await api.armDiscovery(row.symbol, row.archetype, window)
    alert(`Armed ${row.symbol} · ${row.label}`)
  }

  // group rows by coin
  const groups = {}
  for (const r of data.rows) (groups[r.symbol] ||= []).push(r)

  return (
    <div className="discover">
      <div className="discover-controls">
        <select value={window} onChange={(e) => setWindow(e.target.value)}>
          {windows.map((w) => <option key={w.key} value={w.key}>{w.label}</option>)}
        </select>
        <select value={scope} onChange={(e) => setScope(e.target.value)}>
          <option value="universe">Universe</option>
          <option value="watchlist">Watchlist</option>
        </select>
        <button onClick={refresh} disabled={data.status === 'computing'}>
          {data.status === 'computing' ? 'Computing…' : 'Refresh'}
        </button>
        <span className="discover-fresh">computed {ago(data.computed_at)}</span>
      </div>

      {data.error && <p className="discover-error">Last sweep error: {data.error}</p>}
      {data.rows.length === 0 && data.status !== 'computing' &&
        <p className="muted">No results yet — hit Refresh to sweep the universe.</p>}

      {Object.entries(groups).map(([symbol, rows]) => (
        <div key={symbol} className="discover-coin">
          <h3>{symbol}</h3>
          <table className="discover-table">
            <thead>
              <tr><th>Strategy</th><th>Trades</th><th>Win</th><th>Exp</th>
                <th>PF</th><th>MaxDD</th><th>Now</th><th></th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.archetype || 'err'} className={r.error ? 'row-err' : ''}>
                  <td>{r.label || '—'}</td>
                  <td>{r.metrics?.n_trades ?? '—'}</td>
                  <td>{fmtPct(r.metrics?.win_rate)}</td>
                  <td className={expTier(r.metrics?.expectancy)}>{fmtNum(r.metrics?.expectancy)}</td>
                  <td>{fmtNum(r.metrics?.profit_factor)}</td>
                  <td>{fmtPct(r.metrics?.max_drawdown)}</td>
                  <td>
                    {r.eligible_now && <span className="badge badge-eligible">eligible</span>}
                    {r.fires_now && <span className="dot dot-fires" title="signal fires now" />}
                  </td>
                  <td>{r.archetype &&
                    <button className="arm-btn" onClick={() => arm(r)}>Arm</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}
```

- [x] **Step 2: Add the nav tab and render branch in `App.jsx`**

Add the import after the other page imports (~line 6):

```jsx
import Discover from './pages/Discover.jsx'
```

Add the nav button after the Strategy button (~line 44):

```jsx
        <button className={tab==='discover'?'active':''} onClick={()=>setTab('discover')}>Discover</button>
```

Add the render branch after the Strategy branch (~line 64):

```jsx
      {tab==='discover' && <Discover />}
```

- [x] **Step 3: Append styles to `theme.css`**

Append to `frontend/src/theme.css`:

```css
/* --- discovery --- */
.discover-controls { display: flex; gap: .5rem; align-items: center; margin-bottom: 1rem; }
.discover-fresh { color: var(--muted, #888); font-size: .85rem; }
.discover-error { color: #c0392b; }
.discover-coin { margin-bottom: 1.25rem; }
.discover-table { width: 100%; border-collapse: collapse; font-size: .9rem; }
.discover-table th, .discover-table td { padding: .35rem .5rem; text-align: right; }
.discover-table th:first-child, .discover-table td:first-child { text-align: left; }
.discover-table tr.row-err { opacity: .5; }
.tier-good { color: #1e8e3e; font-weight: 600; }
.tier-ok { color: #b8860b; }
.tier-bad { color: #c0392b; }
.badge-eligible { background: #1e8e3e; color: #fff; border-radius: 4px; padding: 0 .4rem; font-size: .75rem; }
.dot-fires { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #2e7dd1; margin-left: .35rem; }
.arm-btn { padding: .15rem .6rem; }
```

- [x] **Step 4: Verify the frontend builds**

Run: `cd frontend && npm run build`
Expected: build succeeds with no errors; `dist/` updated.

- [x] **Step 5: Commit**

```bash
git add frontend/src/pages/Discover.jsx frontend/src/App.jsx frontend/src/theme.css
git commit -m "feat(ui): Discover page — ranked sweep results, eligible badges, one-click arm"
```

---

### Task 10: Full verification + graph/roadmap update

**Files:**
- Modify: `docs/DEVLOG.md` (append a Phase 2 entry)
- Modify: `docs/ROADMAP_STATUS.md` (mark B2 done; set next action to Sub-project C)
- Regenerate: `graphify-out/` via `python3 -m graphify update .`

- [x] **Step 1: Run the full backend test suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — previous `235 passed, 5 skipped` plus the new discovery tests (≈11 new), i.e. roughly `246 passed, 5 skipped`. Zero failures.

- [x] **Step 2: Confirm the frontend builds**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [x] **Step 3: Append a DEVLOG entry**

Append to `docs/DEVLOG.md`:

```markdown
## Sub-project B Phase 2 — Auto-Strategy Discovery (2026-06-03)

- `DiscoveryEngine` (`src/swingbot/discovery.py`): sweeps the universe × non-AI archetypes
  over the deep archive, ranks by expectancy; `eligible_now = good_history + regime OK`,
  `fires_now` shown as a non-gating indicator; coverage-derived scenario windows.
- API: `GET /api/discovery`, `GET /api/discovery/windows`, `POST /api/discovery/refresh`
  (daemon-thread sweep + `discovery.json` cache), `POST /api/discovery/arm` (save + arm, paper).
- UI: `Discover` page — ranked-by-coin table, eligible badges, fires dot, one-click arm.
- Deferred: per-row equity curves / trade tables, hardcoded crisis windows, timer recompute,
  real-money live gating.
```

- [x] **Step 4: Update the roadmap board**

In `docs/ROADMAP_STATUS.md`: set `Last updated` to 2026-06-03; change the B2 row Status to `✅ DONE` with Spec `specs/2026-06-03-subproject-b-phase2-discovery-design.md` and Plan `plans/2026-06-03-subproject-b-phase2-discovery.md`; rewrite the **NEXT ACTION** to point at **Sub-project C (Ollama decision brain)** — "write its spec via `superpowers:brainstorming`, output to `docs/superpowers/specs/2026-06-04-subproject-c-decision-brain-design.md`". Update the pytest expectation line to the new count from Step 1.

- [x] **Step 5: Regenerate the knowledge graph**

Run: `python3 -m graphify update .`
Expected: graph updated (AST-only, no API cost).

- [x] **Step 6: Commit**

```bash
git add docs/DEVLOG.md docs/ROADMAP_STATUS.md graphify-out
git commit -m "docs(roadmap): Sub-project B Phase 2 done; devlog + graph; next = Sub-project C"
```

---

## Self-Review

**Spec coverage** (each spec section → task):
- `DiscoveryEngine.sweep`, single-df-load reuse, benchmark reuse, ranking → Task 2.
- Eligibility (`good_history` + regime) & `fires_now` non-gating → Tasks 1, 2.
- Coverage-derived windows (`windows_for`, `_apply_window`) → Tasks 1, 4.
- Caching (atomic JSON, startup load) → Tasks 3, 4, 7.
- API `GET /api/discovery`, `/windows`, `refresh`, `arm` → Tasks 4, 5, 6.
- Deep lookback (100_000, not 1000) → Task 2 (`DiscoveryEngine.__init__ lookback=100_000`).
- One-click arm = save + arm + live_eligible ON (paper), name scheme → Task 6.
- UI Discover panel (window/scope/refresh, grouped table, eligible badge, fires dot, arm), api.js methods → Tasks 8, 9.
- Error handling (per-row isolation, sweep never touches trading, 503 when unconfigured) → Tasks 2, 5.
- Testing (engine ranking/eligibility/error-isolation/max_symbols, windows math, arm round-trip, refresh guard) → Tasks 1-6.
- Success criteria (sweep → ranked GET, one-click arm appears armed, cache survives restart) → Tasks 4-7, 10.

**Placeholder scan:** none — every code/test step shows complete content.

**Type/name consistency:** `DiscoveryEngine.sweep(symbols, window_key, style, max_symbols)`, row keys (`symbol, archetype, label, profile, metrics, eligible_now, fires_now, regime, error`), `good_history(metrics)`, `windows_for(coverage)`, `_apply_window(df, window_key)`, `load_cache`/`save_cache`, `app.state.discovery`, and api.js method names (`getDiscovery`, `discoveryWindows`, `refreshDiscovery`, `armDiscovery`) are used identically across backend tasks, web tasks, and the frontend.
