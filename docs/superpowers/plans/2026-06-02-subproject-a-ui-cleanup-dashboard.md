# Sub-project A — UI Cleanup + Multi-Position Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the hardcoded `TRX/USD` default, let users pick cryptos from a curated Alpaca USD list, simplify the Strategy page, and show all open positions at once as a grid of live charts plus a watchlist row — all Playwright-verified.

**Architecture:** Two small backend additions (`/api/universe` from the Alpaca broker with a static fallback; `/api/watchlist` persisted in the existing `meta` SQLite table via `ProfileStore`), a `default_symbol` portfolio setting, and frontend changes: symbol becomes a `<select>` fed by `/api/universe`, the low-level form collapses behind an Advanced disclosure, and a new `PositionGrid` renders mini charts for open positions + watchlist.

**Tech Stack:** Python 3 / FastAPI / SQLite / pytest (backend); React + Vite + lightweight-charts (frontend); Playwright MCP for verification.

**Spec:** `docs/superpowers/specs/2026-06-02-platform-improvement-roadmap-design.md`

---

## File Structure

| File | Create/Modify | Responsibility |
|------|---------------|----------------|
| `src/swingbot/universe.py` | Create | Static fallback list of Alpaca USD pairs + helper |
| `src/swingbot/broker/alpaca.py` | Modify | `list_usd_pairs()` — live tradable USD pairs |
| `src/swingbot/profiles.py` | Modify | `default_symbol` setting + `get/set_watchlist()` |
| `src/swingbot/web.py` | Modify | `/api/universe`, `/api/watchlist` GET/PUT, settings model |
| `tests/test_universe.py` | Create | Fallback list + ProfileStore watchlist tests |
| `tests/test_web_universe.py` | Create | `/api/universe` + `/api/watchlist` endpoint tests |
| `frontend/src/api.js` | Modify | `universe()`, `watchlist()`, `setWatchlist()` |
| `frontend/src/pages/Strategy.jsx` | Modify | Symbol `<select>`; collapse form behind Advanced |
| `frontend/src/components/PresetGallery.jsx` | Modify | Drop `'TRX/USD'` literal |
| `frontend/src/components/StrategyBuilder.jsx` | Modify | Drop `'TRX/USD'` literal |
| `frontend/src/components/PositionGrid.jsx` | Create | Mini-chart grid: open positions + watchlist row |
| `frontend/src/pages/Dashboard.jsx` | Modify | Render `PositionGrid` at top |
| `docs/DEVLOG.md` | Create | Project devlog; first entry |
| `README.md` | Modify | Symbol-agnostic wording |

---

## Task 1: Backend — fallback universe + ProfileStore watchlist & default_symbol  ✅ DONE (commit, 3 tests pass)

**Files:**
- Create: `src/swingbot/universe.py`
- Modify: `src/swingbot/profiles.py:112-137`
- Test: `tests/test_universe.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_universe.py
from swingbot.universe import fallback_universe
from swingbot.profiles import ProfileStore


def test_fallback_universe_is_usd_pairs():
    u = fallback_universe()
    assert "BTC/USD" in u and "ETH/USD" in u
    assert all(s.endswith("/USD") for s in u)
    assert u == sorted(u)  # stable, sorted


def test_watchlist_roundtrip_and_default_empty(tmp_path):
    s = ProfileStore(str(tmp_path / "p.db"))
    assert s.get_watchlist() == []
    s.set_watchlist(["ETH/USD", "BTC/USD"])
    assert s.get_watchlist() == ["ETH/USD", "BTC/USD"]


def test_default_symbol_setting(tmp_path):
    s = ProfileStore(str(tmp_path / "p.db"))
    assert s.get_portfolio_settings()["default_symbol"] == ""
    s.set_portfolio_settings({"default_symbol": "ETH/USD"})
    assert s.get_portfolio_settings()["default_symbol"] == "ETH/USD"
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_universe.py -v`
Expected: FAIL — `ModuleNotFoundError: swingbot.universe` / `AttributeError: get_watchlist`.

- [x] **Step 3: Create `src/swingbot/universe.py`**

```python
"""Curated fallback list of Alpaca-tradable crypto USD pairs.

Used when live broker asset listing is unavailable (no creds / network error).
"""
from __future__ import annotations

_FALLBACK = [
    "AAVE/USD", "AVAX/USD", "BCH/USD", "BTC/USD", "DOGE/USD", "DOT/USD",
    "ETH/USD", "LINK/USD", "LTC/USD", "SHIB/USD", "SOL/USD", "SUSHI/USD",
    "UNI/USD", "XRP/USD", "YFI/USD",
]


def fallback_universe() -> list[str]:
    return sorted(_FALLBACK)
```

- [x] **Step 4: Add watchlist + default_symbol to `ProfileStore`**

In `src/swingbot/profiles.py`, add `"default_symbol": ""` to `_PORTFOLIO_DEFAULTS` (so it becomes a settable, validated key):

```python
    _PORTFOLIO_DEFAULTS = {
        "max_concurrent": 5,
        "max_total_deployed_frac": 0.80,
        "portfolio_daily_loss_limit_pct": 0.08,
        "default_symbol": "",
    }
```

Then append these two methods to the class (after `set_portfolio_settings`):

```python
    def get_watchlist(self) -> list[str]:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key='watchlist'").fetchone()
        return json.loads(row[0]) if row else []

    def set_watchlist(self, symbols: list[str]) -> None:
        clean = [s for s in dict.fromkeys(symbols) if isinstance(s, str) and s]
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('watchlist', ?)",
            (json.dumps(clean),))
        self._conn.commit()
```

- [x] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_universe.py -v`
Expected: PASS (3 tests).

- [x] **Step 6: Commit**

```bash
git add src/swingbot/universe.py src/swingbot/profiles.py tests/test_universe.py
git commit -m "feat(universe): fallback USD-pair list + ProfileStore watchlist & default_symbol"
```

---

## Task 2: Backend — broker `list_usd_pairs()`  ✅ DONE (4 tests pass)

**Files:**
- Modify: `src/swingbot/broker/alpaca.py:13-21`
- Test: `tests/test_universe.py` (extend)

- [x] **Step 1: Write the failing test** (append to `tests/test_universe.py`)

```python
def test_list_usd_pairs_filters_tradable_usd(monkeypatch):
    from swingbot.broker.alpaca import AlpacaBroker

    class _Asset:
        def __init__(self, symbol, tradable):
            self.symbol, self.tradable = symbol, tradable

    class _FakeClient:
        def get_all_assets(self, req):
            return [_Asset("BTC/USD", True), _Asset("ETH/USD", True),
                    _Asset("LUNA/USD", False), _Asset("BTC/USDT", True)]

    b = AlpacaBroker.__new__(AlpacaBroker)   # bypass __init__/network
    b._client = _FakeClient()
    assert b.list_usd_pairs() == ["BTC/USD", "ETH/USD"]
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_universe.py::test_list_usd_pairs_filters_tradable_usd -v`
Expected: FAIL — `AttributeError: 'AlpacaBroker' object has no attribute 'list_usd_pairs'`.

- [x] **Step 3: Implement `list_usd_pairs`**

In `src/swingbot/broker/alpaca.py`, extend imports and add the method to `AlpacaBroker`:

```python
from alpaca.trading.enums import AssetClass, AssetStatus, OrderSide, TimeInForce
from alpaca.trading.requests import GetAssetsRequest, MarketOrderRequest
```

```python
    def list_usd_pairs(self) -> list[str]:
        """Tradable crypto */USD pairs, sorted. Network call — cache at call site."""
        req = GetAssetsRequest(asset_class=AssetClass.CRYPTO, status=AssetStatus.ACTIVE)
        assets = self._client.get_all_assets(req)
        return sorted(
            a.symbol for a in assets
            if getattr(a, "tradable", False) and a.symbol.endswith("/USD"))
```

(Keep the existing `OrderSide, TimeInForce` / `MarketOrderRequest` imports working — the lines above replace the two existing import lines.)

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_universe.py -v`
Expected: PASS (4 tests).

- [x] **Step 5: Commit**

```bash
git add src/swingbot/broker/alpaca.py tests/test_universe.py
git commit -m "feat(broker): list_usd_pairs() — tradable Alpaca USD crypto pairs"
```

---

## Task 3: Backend — `/api/universe` + `/api/watchlist` endpoints

**Files:**
- Modify: `src/swingbot/web.py` (models near line 41; routes near line 136)
- Test: `tests/test_web_universe.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web_universe.py
from fastapi.testclient import TestClient
from swingbot.web import create_app
from swingbot.profiles import ProfileStore


class FakeController:
    def status(self): return {"portfolio": {"mode": "paper"}, "strategies": []}
    def reload(self): pass


def _client(tmp_path, token="t"):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    app = create_app(controller=FakeController(), profiles=profiles,
                     creds=None, token=token)
    return TestClient(app), profiles


def test_universe_falls_back_without_creds(tmp_path):
    c, _ = _client(tmp_path)
    body = c.get("/api/universe").json()
    assert "BTC/USD" in body["symbols"]
    assert all(s.endswith("/USD") for s in body["symbols"])


def test_watchlist_get_put_roundtrip_and_token(tmp_path):
    c, _ = _client(tmp_path)
    assert c.get("/api/watchlist").json()["symbols"] == []
    assert c.put("/api/watchlist", json={"symbols": ["ETH/USD"]}).status_code == 401
    h = {"X-Token": "t"}
    r = c.put("/api/watchlist", json={"symbols": ["ETH/USD", "BTC/USD"]}, headers=h)
    assert r.status_code == 200
    assert c.get("/api/watchlist").json()["symbols"] == ["ETH/USD", "BTC/USD"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_web_universe.py -v`
Expected: FAIL — 404 on `/api/universe`.

- [ ] **Step 3: Add the settings model field + routes**

In `src/swingbot/web.py`, add `default_symbol` to `PortfolioSettingsBody`:

```python
class PortfolioSettingsBody(BaseModel):
    max_concurrent: int | None = None
    max_total_deployed_frac: float | None = None
    portfolio_daily_loss_limit_pct: float | None = None
    default_symbol: str | None = None
```

Add a watchlist body model alongside the others:

```python
class WatchlistBody(BaseModel):
    symbols: list[str]
```

Add the import near the top (with the other `swingbot` imports):

```python
from swingbot.universe import fallback_universe
from swingbot.broker.alpaca import AlpacaBroker
```

Add these routes inside `create_app` (e.g. right after the portfolio-settings routes, ~line 149):

```python
    # ---- universe / watchlist ----
    _universe_cache: dict = {}

    @app.get("/api/universe")
    def universe():
        if _universe_cache.get("symbols"):
            return {"symbols": _universe_cache["symbols"]}
        symbols = fallback_universe()
        try:
            if creds is not None and creds.get() is not None:
                cr = creds.get()
                broker = AlpacaBroker(cr["key_id"], cr["secret_key"], paper=True)
                live = broker.list_usd_pairs()
                if live:
                    symbols = live
                    _universe_cache["symbols"] = live
        except Exception:
            pass  # fall back to static list
        return {"symbols": symbols}

    @app.get("/api/watchlist")
    def get_watchlist():
        return {"symbols": profiles.get_watchlist()}

    @app.put("/api/watchlist")
    def put_watchlist(body: WatchlistBody, _=Depends(require_token)):
        profiles.set_watchlist(body.symbols)
        return {"symbols": profiles.get_watchlist()}
```

> NOTE: confirm `creds.get()` returns a dict with `key_id`/`secret_key`. If its shape differs, adapt the two lines that read `cr[...]`. The `except Exception` guarantees the endpoint still returns the fallback regardless.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_web_universe.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run full backend suite (no regressions)**

Run: `.venv/bin/python -m pytest -q`
Expected: previous count + 6 new, all green (no failures).

- [ ] **Step 6: Commit**

```bash
git add src/swingbot/web.py tests/test_web_universe.py
git commit -m "feat(web): /api/universe (live+fallback) and /api/watchlist endpoints"
```

---

## Task 4: Frontend — API client methods

**Files:**
- Modify: `frontend/src/api.js:53-54`

- [ ] **Step 1: Add methods to the `api` object** (after `setPortfolioSettings`)

```javascript
  universe: () => req('GET', '/api/universe'),
  watchlist: () => req('GET', '/api/watchlist'),
  setWatchlist: (symbols) => req('PUT', '/api/watchlist', { symbols }),
```

- [ ] **Step 2: Verify the frontend builds**

Run: `cd frontend && npm run build`
Expected: build succeeds, no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.js
git commit -m "feat(ui): api client methods for universe + watchlist"
```

---

## Task 5: Frontend — symbol-agnostic Strategy page + Advanced disclosure

**Files:**
- Modify: `frontend/src/pages/Strategy.jsx`
- Modify: `frontend/src/components/PresetGallery.jsx:10`
- Modify: `frontend/src/components/StrategyBuilder.jsx:11`

- [ ] **Step 1: Drop the `TRX/USD` literals in the two components**

In `frontend/src/components/PresetGallery.jsx` line 10 and `frontend/src/components/StrategyBuilder.jsx` line 11, change:

```javascript
  const [coin, setCoin] = useState(symbol || 'TRX/USD')
```
to:
```javascript
  const [coin, setCoin] = useState(symbol || '')
```

- [ ] **Step 2: Make `Strategy.jsx` symbol-agnostic with a universe `<select>`**

In `frontend/src/pages/Strategy.jsx`:

(a) Change `BLANK` so it carries no coin default:
```javascript
const BLANK = {
  name: 'new', symbol: '', timeframe: '15m', benchmark_symbol: 'BTC/USD',
```
(rest of `BLANK` unchanged — `benchmark_symbol` stays `BTC/USD` as a neutral market benchmark, not a traded default).

(b) Load the universe and resolve a default symbol. Add state + effect inside the `Strategy` component, just after the existing `const set = ...` line:
```javascript
  const [universe, setUniverse] = useState([])
  useEffect(() => {
    api.universe().then(r => {
      setUniverse(r.symbols)
      setF(prev => prev.symbol ? prev : { ...prev, symbol: r.symbols[0] || '' })
    }).catch(() => {})
  }, [])
```

(c) Replace the free-text symbol `<Txt>` (the block at lines ~159-160, `label="Symbol (e.g. TRX/USD)"`) with a dropdown:
```javascript
        <div style={{ marginBottom: 8 }}>
          <label>Symbol<Hint text="The Alpaca crypto pair to trade. Picked from pairs Alpaca supports for spot USD trading." /></label>
          <select value={f.symbol} onChange={e => set('symbol')(e.target.value)}>
            {!f.symbol && <option value="">— pick a crypto —</option>}
            {universe.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
```

- [ ] **Step 3: Collapse the low-level form behind an Advanced disclosure**

Wrap the entire `<div className="panel"><h3>Strategy form</h3> … </div>` block (lines ~153-244) in a `<details>` so the default view leads with the preset/builder flow. Replace the opening `<div className="panel">` of that block with:
```javascript
      <details className="panel">
        <summary style={{ cursor: 'pointer', fontWeight: 600 }}>Advanced — hand-tune a profile</summary>
```
and its matching closing `</div>` (the one immediately before the component's final `</div>`) with `</details>`. The symbol `<select>` and `name` field stay inside, so advanced users still edit them; the straightforward path is now: pick crypto in PresetGallery/Builder → Use → Save.

- [ ] **Step 4: Verify the build + no remaining literal**

Run: `cd frontend && npm run build`
Expected: build succeeds.
Run: `grep -rn "TRX/USD" frontend/src`
Expected: **no matches**.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Strategy.jsx frontend/src/components/PresetGallery.jsx frontend/src/components/StrategyBuilder.jsx
git commit -m "feat(ui): symbol-agnostic Strategy page (universe picker) + Advanced disclosure"
```

---

## Task 6: Frontend — PositionGrid (open positions + watchlist) on the dashboard

**Files:**
- Create: `frontend/src/components/PositionGrid.jsx`
- Modify: `frontend/src/pages/Dashboard.jsx`

- [ ] **Step 1: Create `PositionGrid.jsx`**

```javascript
import { useEffect, useState } from 'react'
import { api } from '../api.js'
import ChartPanel from './ChartPanel.jsx'

// Grid of mini charts: one tile per open position, then a watchlist row.
export default function PositionGrid({ strategies = [] }){
  const [watchlist, setWatchlist] = useState([])
  useEffect(() => { api.watchlist().then(r => setWatchlist(r.symbols)).catch(() => {}) }, [])

  const open = strategies.filter(s => s.position)
  const heldSymbols = new Set(open.map(s => s.symbol))
  const watchOnly = watchlist.filter(sym => !heldSymbols.has(sym))

  return (
    <div className="wrap">
      <div className="panel full">
        <h3>Open positions {open.length > 0 && <span className="chip">{open.length}</span>}</h3>
        {open.length === 0 && <div className="muted">No open positions. Arm a strategy on the Strategy tab.</div>}
        <div className="position-grid">
          {open.map(s => (
            <div className="pg-tile" key={s.symbol || s.name}>
              <div className="pg-head">{s.symbol}</div>
              <ChartPanel symbol={s.symbol} mini position={s.position} />
            </div>
          ))}
        </div>
      </div>

      {watchOnly.length > 0 && (
        <div className="panel full">
          <h3>Watchlist</h3>
          <div className="position-grid">
            {watchOnly.map(sym => (
              <div className="pg-tile" key={sym}>
                <div className="pg-head">{sym}</div>
                <ChartPanel symbol={sym} mini />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Add minimal grid styles**

Append to `frontend/src/theme.css`:
```css
.position-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
.pg-tile { border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 6px; }
.pg-head { font-weight: 600; padding: 2px 4px 6px; }
```

- [ ] **Step 3: Render `PositionGrid` at the top of the dashboard**

In `frontend/src/pages/Dashboard.jsx`, import it and render above the strategy cards:
```javascript
import PositionGrid from '../components/PositionGrid.jsx'
```
Inside the returned `<div className="wrap">`, add as the first child (before the `strategies.length === 0` block):
```javascript
      <PositionGrid strategies={strategies} />
```

- [ ] **Step 4: Verify the build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/PositionGrid.jsx frontend/src/pages/Dashboard.jsx frontend/src/theme.css
git commit -m "feat(ui): PositionGrid — all open positions + watchlist as mini charts on dashboard"
```

---

## Task 7: Devlog

**Files:**
- Create: `docs/DEVLOG.md`

- [ ] **Step 1: Create the devlog with the first entry**

```markdown
# Devlog

Running log of platform improvements. Newest first.

## 2026-06-02 — Sub-project A: UI cleanup + multi-position dashboard
- Removed the hardcoded `TRX/USD` default; symbol is now picked from a curated
  Alpaca USD list (`GET /api/universe`, live with static fallback).
- Added a persisted watchlist (`GET/PUT /api/watchlist`) and a `default_symbol` setting.
- Strategy page: low-level form collapsed behind an "Advanced" disclosure; the
  default flow is pick-crypto → preset → backtest → arm.
- Dashboard: new `PositionGrid` shows every open position as a mini chart, plus a
  watchlist row.
- Roadmap: B (auto-discovery) → C (Ollama brain) → D (self-test gate) still to come.
```

- [ ] **Step 2: Commit**

```bash
git add docs/DEVLOG.md
git commit -m "docs(devlog): start devlog; Sub-project A entry"
```

---

## Task 8: README wording

**Files:**
- Modify: `README.md:3`

- [ ] **Step 1: Make the target-asset wording symbol-agnostic**

Change the line referencing `Target asset TRX/USD` to:
```markdown
A personal, **long-only crypto swing-trading bot** for [Alpaca](https://alpaca.markets/) (spot — Alpaca crypto can't short). Trade any Alpaca USD pair (BTC/USD, ETH/USD, …), chosen from the in-app crypto picker; holds range from minutes to about a day. Design motto: *simple beats clever*.
```

- [ ] **Step 2: Confirm no stray literals remain in shipped code/docs**

Run: `grep -rn "TRX/USD" README.md frontend/src src/swingbot`
Expected: **no matches** (plan docs under `docs/superpowers/plans/` may still contain historical references — that's fine).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(readme): symbol-agnostic target-asset wording"
```

---

## Task 9: Playwright verification + knowledge graph

This task runs the app and verifies the UI with the Playwright MCP. Do NOT mark Sub-project A complete until every check below passes (per superpowers:verification-before-completion).

- [ ] **Step 1: Build the frontend and (re)start the app**

```bash
cd frontend && npm run build && cd ..
docker compose build swingbot && docker compose up -d swingbot
docker compose logs swingbot | grep -i token   # grab the access token
```
Expected: container healthy on http://localhost:8000; token printed.

- [ ] **Step 2: Drive the UI with Playwright MCP**

Using the `mcp__plugin_playwright_playwright__*` tools:
1. `browser_navigate` → `http://localhost:8000` (paste the token in TokenGate).
2. `browser_snapshot` of the Dashboard → confirm an **"Open positions"** panel renders (empty-state text if flat) and a **position-grid** container exists.
3. `browser_console_messages` → confirm **no error-level messages**.
4. Click the **Strategy** tab; `browser_snapshot` → confirm the **Symbol** control is a `<select>` whose options come from `/api/universe` (e.g. `BTC/USD`), and the hand-tune form is inside a collapsed **Advanced** `<details>`.
5. `browser_network_requests` → confirm `GET /api/universe` and `GET /api/watchlist` return 200.

- [ ] **Step 3: Record verification evidence**

Capture `browser_take_screenshot` of the dashboard grid and the Strategy page. Note pass/fail of each Step-2 check in the PR / handoff.
Expected: all five checks pass; zero console errors.

- [ ] **Step 4: Update the knowledge graph + final commit**

```bash
graphify update .
git add graphify-out
git commit -m "chore(graph): update after Sub-project A UI cleanup + dashboard"
```

---

## Self-Review (author check — completed)

- **Spec coverage:** crypto picker (Task 1-5), drop TRX/USD (Tasks 5,8), straightforward Strategy page (Task 5), all-positions-at-once grid + watchlist (Task 6), Playwright verify (Task 9), devlog (Task 7), universe fallback + watchlist persistence (Tasks 1-3). All A-scope spec items mapped.
- **Out of scope (correctly deferred):** discovery (B), Ollama (C), self-test scheduler (D).
- **Type consistency:** endpoints return `{"symbols": [...]}` consistently; `api.universe()/watchlist()/setWatchlist()` match the routes; `list_usd_pairs()` name used identically in broker + web + tests; `get_watchlist/set_watchlist` consistent across profiles + web.
- **Placeholders:** none — every code step contains full code; every run step has an expected result.
