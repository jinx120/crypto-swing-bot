# Kronos POC Paper Trader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a hands-off autonomous **paper** trader: a selectable public data feed (Coinbase default, decoupled from the broker) drives a single Kronos predict→buy→fixed-bracket strategy, kept in line by deterministic rebalance + risk breakers and a bounded local-LLM config advisor — with a no-numeric-fields UI.

**Architecture:** Reuse the existing battle-tested execution machinery (per-strategy `Orchestrator` with broker-confirmed fills, pending orders, reconcile from phases 3–6; the `PortfolioSupervisor` loop; the `rebalance`/`risk` layers). The "Kronos bracket strategy" is **not** a new standalone class — the existing `KronosForecastSignal` already computes `pct_change/threshold_pct`, so the strategy = that signal (threshold `0.0075`, `entry_threshold 1.0`) + a **profile preset** instantiated per coin + a **new fixed-% bracket** (the one real gap vs. today's ATR bracket). Data is decoupled from the broker by keying `MarketData`'s provider on a persisted `data_source` setting (CcxtProvider for Coinbase/Kraken needs no key). Obsolete subsystems (auto-discovery, managed-strategy reconciler, paper_probe, per-trade Ollama brain) are deleted outright. A new narrow LLM **advisor** tunes *configuration* only (never trades), with strict-JSON validation, clamp-to-band, a tuning journal, and one-click revert.

> **Architecture note (read before Phase B):** The spec's testing section names `KronosBracketStrategy.decide()`. This plan realizes that *behavior* through the existing `KronosForecastSignal` + `Orchestrator` rather than a new class, because (a) the existing signal already implements the exact entry math, (b) the DECISIONS brief says KEEP the Kronos signal/adapter and the supervisor loop, and (c) a parallel `decide()` would have to re-implement the broker-confirmed fill / pending-order / reconcile safety net that phases 3–6 hardened. The tested unit for entry is `KronosForecastSignal.evaluate()`; the tested unit for the bracket is the new `pct_bracket_levels()` + the orchestrator's percent-bracket entry path.

**Tech Stack:** Python 3.12 (`.venv/bin/python`), FastAPI, SQLite, pandas, CCXT, Kronos (cloned to `/kronos` in the image), pytest + ruff; React + Vite + Tailwind v3 + hand-authored shadcn-style primitives, `react-router-dom` v6, `lightweight-charts` v5, Vitest; llama.cpp/Ollama for the advisor; Docker Compose.

## Global Constraints

- **Python interpreter:** `.venv/bin/python` (plain `python`/`pytest` are not on PATH). Ruff: `.venv/bin/ruff`.
- **TDD, every task:** write the failing test → run it red → minimal implementation → run it green → commit.
- **Gate (must stay green):** `.venv/bin/python -m pytest -q` · `.venv/bin/ruff check src/` · `cd frontend && npm run build`. Frontend tests: `cd frontend && npm run test`.
- **Docker rebuild after every code change (standing rule, pre-authorized, do not ask):** `docker compose build swingbot && docker compose up -d swingbot`. The host daemon lacks `runtime: nvidia` unless Task 23 lands — until then start via the `runtime: runc` override.
- **Symbols:** USD quote pairs only (e.g. `BTC/USD`); Alpaca paper is USD-funded. Never `USDT` for trading. (For Coinbase/Kraken data, pass `quote_map={}` so `BTC/USD` is sent verbatim — the CCXT default maps `USD→USDT`, which is wrong for those venues.)
- **No numeric config fields in the UI.** Every parameter is system-owned. The only user control is the risk dial (Cautious/Balanced/Aggressive) + the data-source dropdown.
- **Commit per task**, scoped `git add` to that task's files. The working tree carries unrelated uncommitted FVG/presets/graphify work — **do not touch or stage it**.
- **Branch:** `core-engine` (current). Working on it is user-approved.
- **Do NOT re-open settled design forks** — they live in `docs/superpowers/specs/2026-06-20-kronos-poc-paper-trader-DECISIONS.md`.

---

## Context for a cold code-gen agent

You are implementing this plan verbatim, TDD, task-by-task; tick each `- [ ]` and commit per task. Do not touch files outside each task's File list. Orientation:

- **Data layer:** `src/swingbot/data/market.py` — `MarketData(store, creds)`; `_provider()` currently returns `self.creds.make_data()` (welded to broker creds → `None` with no key → "no fresh closed bar available" at `supervisor.py:636`). `src/swingbot/data/ccxt_provider.py` — `CcxtProvider(exchange_id, quote_map, ...)` with `get_candles(symbol, timeframe, lookback)` and `get_latest_price`; **no `get_candles_multi`** (you add a shim). Public OHLCV needs no API key.
- **Settings:** `src/swingbot/profiles.py` — `ProfileStore` with `get_meta`/`set_meta`, and `get_portfolio_settings`/`set_portfolio_settings` over `_PORTFOLIO_DEFAULTS` (which today still contains `brain_*` keys — removed in Task 13).
- **Decision engine:** `src/swingbot/supervisor.py` `PortfolioSupervisor` runs one `Orchestrator` per armed strategy (`tick_all`, `build`). `src/swingbot/orchestrator.py` `Orchestrator` uses `ConfluenceEngine(build_signals(profile), profile)`; on entry computes `bracket_levels(price, atr, stop_atr_mult, take_profit_atr_mult)` (ATR-based; `src/swingbot/exits.py`). In-position exit reads `pos.stop`/`pos.tp` (`OpenPosition` in `src/swingbot/types.py:162`, which already has `entry_price`/`stop`/`tp`).
- **Signals:** `src/swingbot/confluence.py` `_REGISTRY` maps names→Signal classes; `build_signals(profile)` instantiates from `profile.signals`. `KronosForecastSignal` (`src/swingbot/signals/kronos_forecast.py`) already computes `pct_change = (forecast_close-close)/close`, `score = clamp(pct_change/threshold_pct, 0,1)`; returns the no-forecast fallback when the model is unavailable. `KronosAdapter.forecast(candles) -> DataFrame | None` (`src/swingbot/signals/kronos_adapter.py`).
- **Profile:** `src/swingbot/profile.py` `StrategyProfile` dataclass — `symbol`, `timeframe="15m"`, `signals: dict`, `entry_threshold=0.6`, `stop_atr_mult=1.5`, `take_profit_atr_mult=2.0`, `risk_per_trade`, regimes, etc. `from_dict`/`to_dict` round-trip JSON.
- **Self-management:** `src/swingbot/rebalance.py` (`Rebalancer`, `RebalanceSettings`, `allocated_equity`), `src/swingbot/risk.py` (`RiskManager`), `src/swingbot/portfolio_risk.py` (`PortfolioRiskManager`).
- **Web:** `src/swingbot/web.py` `create_app(...)` mounts the API; `src/swingbot/webmain.py` wires everything (this is where deletions de-wire). Frontend: `frontend/src/` (HashRouter SPA — `#/` Mission Control, `#/coin/:name`, `#/settings`).
- **House rules:** venv `.venv/bin/python`; TDD; ruff clean; don't touch unrelated uncommitted work.

---

## File Structure

**Create:**
- `src/swingbot/advisor/__init__.py`, `digest.py`, `schema.py`, `bands.py`, `journal.py`, `client.py`, `service.py` — the LLM advisor (one responsibility each).
- `tests/test_data_source.py`, `tests/test_pct_bracket.py`, `tests/test_kronos_preset.py`, `tests/test_advisor_digest.py`, `tests/test_advisor_schema.py`, `tests/test_advisor_journal.py`, `tests/test_advisor_service.py`, `tests/test_web_data_source.py`, `tests/test_web_advisor.py`.
- `frontend/src/lib/riskDial.js` (+ test) for the dial→band mapping mirror if needed by the UI.

**Modify:**
- `src/swingbot/data/market.py`, `src/swingbot/data/ccxt_provider.py` (data decoupling).
- `src/swingbot/profiles.py` (data_source + risk_dial settings; drop brain keys).
- `src/swingbot/exits.py`, `src/swingbot/profile.py`, `src/swingbot/orchestrator.py` (fixed-% bracket).
- `src/swingbot/confluence.py` (drop paper_probe from registry), `src/swingbot/supervisor.py` (de-wire managed/probe; advisor schedule hook), `src/swingbot/webmain.py` (re-wire data; delete brain/discovery/managed/probe), `src/swingbot/web.py` (data-source + advisor endpoints; drop discovery/brain endpoints).
- `frontend/src/` Settings + Mission Control + Add-coin dialog.
- `docker-compose.override.yml` (nvidia runtime).

**Delete:** `src/swingbot/decision/` (+ tests), `src/swingbot/discovery.py` + `src/swingbot/strategy_search.py` (+ tests), `src/swingbot/managed_profiles.py` + `src/swingbot/probe_marker.py` + `src/swingbot/signals/paper_probe.py` (+ tests), and the corresponding frontend pages/routes.

---

# Phase A — Data decoupling (ship the demoable core first)

### Task 1: Persist a `data_source` setting

**Files:**
- Modify: `src/swingbot/profiles.py`
- Test: `tests/test_data_source.py`

**Interfaces:**
- Produces: `ProfileStore.get_data_source() -> str` (default `"coinbase"`), `ProfileStore.set_data_source(name: str) -> None` (accepts only `coinbase`/`kraken`/`alpaca`, else `ValueError`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_source.py
import pytest
from swingbot.profiles import ProfileStore


def _store(tmp_path):
    return ProfileStore(str(tmp_path / "swingbot.db"))


def test_data_source_defaults_to_coinbase(tmp_path):
    assert _store(tmp_path).get_data_source() == "coinbase"


def test_data_source_round_trips(tmp_path):
    s = _store(tmp_path)
    s.set_data_source("kraken")
    assert s.get_data_source() == "kraken"


def test_data_source_rejects_unknown(tmp_path):
    with pytest.raises(ValueError):
        _store(tmp_path).set_data_source("binance")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_data_source.py -v`
Expected: FAIL — `AttributeError: 'ProfileStore' object has no attribute 'get_data_source'`.

- [ ] **Step 3: Implement minimal code** — add to `ProfileStore`:

```python
    _DATA_SOURCES = ("coinbase", "kraken", "alpaca")

    def get_data_source(self) -> str:
        return self.get_meta("data_source") or "coinbase"

    def set_data_source(self, name: str) -> None:
        if name not in self._DATA_SOURCES:
            raise ValueError(f"unknown data_source {name!r}")
        self.set_meta("data_source", name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_data_source.py -v` → Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/profiles.py tests/test_data_source.py
git commit -m "feat(data): persist data_source setting (coinbase default)"
```

---

### Task 2: A provider factory keyed on `data_source`

**Files:**
- Modify: `src/swingbot/data/ccxt_provider.py` (add `get_candles_multi` + `get_latest_prices` shims)
- Create: `src/swingbot/data/provider_factory.py`
- Test: `tests/test_data_source.py` (append)

**Interfaces:**
- Consumes: `CcxtProvider`, `creds.make_data()`.
- Produces: `provider_for(data_source: str, creds) -> object | None` — returns a `CcxtProvider(exchange_id=data_source, quote_map={})` for `coinbase`/`kraken`; for `alpaca` returns `creds.make_data()` (or `None` if no creds). `CcxtProvider.get_candles_multi(symbols, timeframe, lookback) -> dict[str, DataFrame]` and `get_latest_prices(symbols) -> dict[str, float]`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_data_source.py`)

```python
from swingbot.data.provider_factory import provider_for
from swingbot.data.ccxt_provider import CcxtProvider


def test_provider_for_coinbase_needs_no_creds():
    prov = provider_for("coinbase", creds=None)
    assert isinstance(prov, CcxtProvider)
    assert prov.exchange_id == "coinbase"
    assert prov.map_symbol("BTC/USD") == "BTC/USD"   # quote_map={} -> verbatim


def test_provider_for_alpaca_uses_creds():
    class FakeCreds:
        def make_data(self):
            return "ALPACA_PROVIDER"
    assert provider_for("alpaca", creds=FakeCreds()) == "ALPACA_PROVIDER"


def test_provider_for_alpaca_without_creds_is_none():
    assert provider_for("alpaca", creds=None) is None


def test_ccxt_get_candles_multi_loops_per_symbol():
    class FakeCcxt(CcxtProvider):
        def get_candles(self, symbol, timeframe, lookback):
            return f"{symbol}:{timeframe}:{lookback}"
    p = FakeCcxt(exchange_id="coinbase", quote_map={})
    out = p.get_candles_multi(["BTC/USD", "ETH/USD"], "15m", 10)
    assert out == {"BTC/USD": "BTC/USD:15m:10", "ETH/USD": "ETH/USD:15m:10"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_data_source.py -v`
Expected: FAIL — `ModuleNotFoundError: swingbot.data.provider_factory`.

- [ ] **Step 3: Implement** — add to `CcxtProvider`:

```python
    def get_candles_multi(self, symbols, timeframe, lookback):
        return {s: self.get_candles(s, timeframe, lookback) for s in symbols}

    def get_latest_prices(self, symbols):
        return {s: self.get_latest_price(s) for s in symbols}
```

Create `src/swingbot/data/provider_factory.py`:

```python
from __future__ import annotations

from swingbot.data.ccxt_provider import CcxtProvider

_CCXT_VENUES = {"coinbase", "kraken"}


def provider_for(data_source: str, creds):
    """Return a market-data provider for the configured data_source.

    coinbase/kraken -> public CcxtProvider (no API key; USD pairs sent verbatim).
    alpaca          -> the broker's data provider via creds (None if unset).
    """
    if data_source in _CCXT_VENUES:
        return CcxtProvider(exchange_id=data_source, quote_map={})
    if data_source == "alpaca":
        return creds.make_data() if creds else None
    raise ValueError(f"unknown data_source {data_source!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_data_source.py -v` → Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/data/ccxt_provider.py src/swingbot/data/provider_factory.py tests/test_data_source.py
git commit -m "feat(data): provider_for() factory + CcxtProvider multi shims"
```

---

### Task 3: `MarketData` builds its provider from `data_source`, not creds

**Files:**
- Modify: `src/swingbot/data/market.py`
- Test: `tests/test_data_source.py` (append), `tests/test_market_provider.py` (UPDATE — see note)

**Interfaces:**
- Consumes: `provider_for`.
- Produces: `MarketData(store, creds, data_source="coinbase", default_lookback=500)`; `_provider()` returns `provider_for(self.data_source, self.creds)`. With `data_source="coinbase"` and `creds=None`, `_provider()` is non-None.

> **Plan amendment (2026-06-21, blocker resolved):** The 3 existing tests in `tests/test_market_provider.py` (`test_provider_delegates_to_make_data`, `test_provider_none_when_unconfigured`, `test_provider_none_when_no_creds`) encode the OLD broker-coupling this task intentionally removes. Update them to make the Alpaca path explicit — pass `data_source="alpaca"` to each `MarketData(...)` so the make_data delegation / None-without-creds behavior is asserted on the alpaca source. The new coinbase-default-with-no-creds case is already covered by this task's `test_marketdata_provider_decoupled_from_broker`. Do NOT preserve the old default behavior — decoupling is the point.

- [ ] **Step 1: Write the failing test** (append)

```python
from swingbot.data.market import MarketData
from swingbot.data.ccxt_provider import CcxtProvider


def test_marketdata_provider_decoupled_from_broker(tmp_path):
    from swingbot.data.store import CandleStore
    store = CandleStore(str(tmp_path / "candles.db"))
    md = MarketData(store, creds=None, data_source="coinbase")
    prov = md._provider()
    assert isinstance(prov, CcxtProvider)        # works with NO broker creds
    assert prov.exchange_id == "coinbase"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_data_source.py::test_marketdata_provider_decoupled_from_broker -v`
Expected: FAIL — `MarketData.__init__()` has no `data_source`, or `_provider()` returns `None`.

- [ ] **Step 3: Implement** — in `src/swingbot/data/market.py`:

```python
    def __init__(self, store: CandleStore, creds, data_source: str = "coinbase",
                 default_lookback: int = 500):
        self.store = store
        self.creds = creds
        self.data_source = data_source
        self.default_lookback = default_lookback

    def _provider(self):
        from swingbot.data.provider_factory import provider_for
        return provider_for(self.data_source, self.creds)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_data_source.py -v` → Expected: PASS (8 passed). Then full gate: `.venv/bin/python -m pytest -q` (existing `MarketData(store, creds)` callers still work — `data_source` defaults).

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/data/market.py tests/test_data_source.py
git commit -m "feat(data): MarketData provider keyed on data_source (broker-decoupled)"
```

---

### Task 4: Wire `data_source` into webmain + a `/api/data-source` endpoint

**Files:**
- Modify: `src/swingbot/webmain.py` (build `MarketData(store, creds, data_source=profiles.get_data_source())`)
- Modify: `src/swingbot/web.py` (add GET/PUT `/api/data-source`; on PUT, persist + rebuild market provider + `controller.reload()`)
- Test: `tests/test_web_data_source.py`

**Interfaces:**
- Consumes: `ProfileStore.get_data_source`/`set_data_source`, `MarketData.data_source`.
- Produces: `GET /api/data-source -> {"data_source": str, "choices": ["coinbase","kraken","alpaca"]}`; `PUT /api/data-source {"data_source": str} -> {"ok": true, "data_source": str}` (X-Token gated like other mutating routes; 400 on unknown value).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web_data_source.py
from fastapi.testclient import TestClient
# Reuse the project's existing app-construction test helper. Mirror the pattern in
# tests/test_web.py (e.g. a make_client()/app fixture) — do NOT invent a new bootstrap.
from tests.helpers import make_client   # adjust import to the repo's actual helper


def test_get_data_source_defaults_coinbase():
    client, _ = make_client()
    r = client.get("/api/data-source")
    assert r.status_code == 200
    body = r.json()
    assert body["data_source"] == "coinbase"
    assert set(body["choices"]) == {"coinbase", "kraken", "alpaca"}


def test_put_data_source_persists(token_headers):
    client, profiles = make_client()
    r = client.put("/api/data-source", json={"data_source": "kraken"}, headers=token_headers)
    assert r.status_code == 200 and r.json()["data_source"] == "kraken"
    assert profiles.get_data_source() == "kraken"


def test_put_data_source_rejects_unknown(token_headers):
    client, _ = make_client()
    r = client.put("/api/data-source", json={"data_source": "binance"}, headers=token_headers)
    assert r.status_code == 400
```

> Implementer note: open `tests/test_web.py` first and copy its exact client/token fixtures; the names above (`make_client`, `token_headers`) are placeholders for whatever that file already provides.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_web_data_source.py -v` → Expected: FAIL (404 — route absent).

- [ ] **Step 3: Implement** — in `webmain.py` change line 34 to:

```python
    market = MarketData(store, creds, data_source=profiles.get_data_source())
```

In `web.py`, add (near the other settings routes; reuse the existing token dependency):

```python
    @app.get("/api/data-source")
    def get_data_source():
        return {"data_source": profiles.get_data_source(),
                "choices": list(ProfileStore._DATA_SOURCES)}

    @app.put("/api/data-source")
    def put_data_source(body: dict, _=Depends(require_token)):
        ds = body.get("data_source", "")
        try:
            profiles.set_data_source(ds)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        market.data_source = ds            # hot-swap the live provider
        controller.reload()                # rebuild orchestrators with the new feed
        return {"ok": True, "data_source": ds}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_web_data_source.py -v` → Expected: PASS. Then `.venv/bin/python -m pytest -q` + `.venv/bin/ruff check src/`.

- [ ] **Step 5: Commit + docker rebuild**

```bash
git add src/swingbot/webmain.py src/swingbot/web.py tests/test_web_data_source.py
git commit -m "feat(data): /api/data-source endpoint + webmain wiring"
docker compose build swingbot && docker compose up -d swingbot
```

---

### Task 5: Settings UI — data-source dropdown

**Files:**
- Modify: `frontend/src/` Settings page (the `#/settings` route component) + `frontend/src/lib/api.js` (add `getDataSource`/`setDataSource`)
- Test: `frontend/src/lib/*.test.js` if a derive/lib function is added; otherwise rely on `npm run build` + the Task 24 smoke.

- [ ] **Step 1:** Add API client methods in `frontend/src/lib/api.js`:

```js
export const getDataSource = () => get("/api/data-source");
export const setDataSource = (data_source) =>
  put("/api/data-source", { data_source });
```

- [ ] **Step 2:** In the Settings page, add a "Data source" `<select>` (Coinbase / Kraken / Alpaca) bound to `getDataSource()`; on change call `setDataSource(value)` and show a saved toast. No numeric fields. Place it above Broker connection.

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run build` → Expected: green.

- [ ] **Step 4: Commit**

```bash
git add frontend/src
git commit -m "feat(ui): data-source dropdown in Settings"
```

---

# Phase B — Fixed-% Kronos bracket

### Task 6: `pct_bracket_levels()` + percent-bracket profile fields

**Files:**
- Modify: `src/swingbot/exits.py`, `src/swingbot/profile.py`
- Test: `tests/test_pct_bracket.py`

**Interfaces:**
- Produces: `pct_bracket_levels(entry_price, tp_pct, sl_pct) -> (stop, tp)` where `tp = entry*(1+tp_pct)`, `stop = entry*(1-sl_pct)`. `StrategyProfile` gains `bracket_mode: str = "atr"` and `tp_pct: float = 0.015`, `sl_pct: float = 0.01`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pct_bracket.py
from swingbot.exits import pct_bracket_levels
from swingbot.profile import StrategyProfile


def test_pct_bracket_levels():
    stop, tp = pct_bracket_levels(100.0, tp_pct=0.015, sl_pct=0.01)
    assert round(tp, 6) == 101.5
    assert round(stop, 6) == 99.0


def test_profile_defaults_atr_mode_with_pct_fields():
    p = StrategyProfile(symbol="BTC/USD")
    assert p.bracket_mode == "atr"
    assert p.tp_pct == 0.015 and p.sl_pct == 0.01


def test_profile_from_dict_round_trips_pct_mode():
    p = StrategyProfile.from_dict({"symbol": "BTC/USD", "bracket_mode": "pct",
                                   "tp_pct": 0.02, "sl_pct": 0.012})
    assert p.bracket_mode == "pct" and p.tp_pct == 0.02 and p.sl_pct == 0.012
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pct_bracket.py -v` → Expected: FAIL (`pct_bracket_levels` missing; `bracket_mode` not a field).

- [ ] **Step 3: Implement** — in `exits.py`:

```python
def pct_bracket_levels(entry_price: float, tp_pct: float, sl_pct: float) -> tuple[float, float]:
    """Return (stop_price, take_profit_price) as fixed percentages off entry (long)."""
    stop = entry_price * (1.0 - sl_pct)
    take_profit = entry_price * (1.0 + tp_pct)
    return stop, take_profit
```

In `profile.py` add the three fields (place beside the ATR bracket fields, keep `from_dict` working — it already passes through unknown-free dict keys via the dataclass):

```python
    bracket_mode: str = "atr"   # "atr" | "pct"
    tp_pct: float = 0.015       # +1.5% take-profit (pct mode)
    sl_pct: float = 0.01        # -1.0% stop-loss (pct mode)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pct_bracket.py -v` → Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/exits.py src/swingbot/profile.py tests/test_pct_bracket.py
git commit -m "feat(strategy): fixed-percentage bracket levels + profile fields"
```

---

### Task 7: Orchestrator uses the percent bracket when `bracket_mode == "pct"`

**Files:**
- Modify: `src/swingbot/orchestrator.py` (entry path ~lines 168–173, and the broker-position adoption path ~line 62)
- Test: `tests/test_pct_bracket.py` (append, orchestrator-level)

**Interfaces:**
- Consumes: `pct_bracket_levels`, `StrategyProfile.bracket_mode/tp_pct/sl_pct`.
- Produces: when `profile.bracket_mode == "pct"`, an entry sets `stop = price*(1-sl_pct)`, `tp = price*(1+tp_pct)` and skips the ATR-positivity gate (ATR may still be computed for sizing fallback, but the bracket is percentage-based).

- [ ] **Step 1: Write the failing test** — add a focused test that drives `Orchestrator` entry with a fake data/broker and a `bracket_mode="pct"` profile, asserting the resulting `PendingOrder.stop/tp` equal the percentage levels. Mirror the existing orchestrator entry tests (find them with `grep -rln "Orchestrator(" tests/`) and copy their fakes — do not invent a new harness.

```python
def test_orchestrator_pct_bracket_sets_levels(orch_pct_entry):
    # orch_pct_entry: an Orchestrator built from a profile with
    #   signals={"kronos_forecast": {...fires...}}, bracket_mode="pct",
    #   tp_pct=0.015, sl_pct=0.01, and a fake provider whose last close == 100.0
    decision = orch_pct_entry.tick(now=NOW)
    pending = orch_pct_entry.state.load_pending_order()
    assert round(pending.tp, 4) == 101.5
    assert round(pending.stop, 4) == 99.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pct_bracket.py -v` → Expected: FAIL (levels still ATR-derived).

- [ ] **Step 3: Implement** — in `orchestrator.py` entry path replace the single bracket computation with a mode switch:

```python
        price = float(df["close"].iloc[-1])
        if self.profile.bracket_mode == "pct":
            stop, tp = pct_bracket_levels(price, self.profile.tp_pct, self.profile.sl_pct)
        else:
            a = float(atr(df, self.profile.atr_period).iloc[-1])
            if not (a > 0):
                return DecisionResult(DecisionCode.ATR_INVALID, "ATR is not positive", {"atr": a})
            stop, tp = bracket_levels(price, a, self.profile.stop_atr_mult,
                                      self.profile.take_profit_atr_mult)
```

Add the import `from swingbot.exits import bracket_levels, pct_bracket_levels`. Apply the same `bracket_mode` switch to the broker-position adoption path (~line 62) so adopted positions also get percentage brackets. (Sizing `risk.size(equity, entry_price, stop_price=stop)` is unchanged — it works off whatever `stop` is.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pct_bracket.py -v` → Expected: PASS. Then `.venv/bin/python -m pytest -q` (ATR-mode strategies unaffected — default `bracket_mode="atr"`).

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/orchestrator.py tests/test_pct_bracket.py
git commit -m "feat(strategy): orchestrator honours pct bracket mode"
```

---

### Task 8: The Kronos-bracket preset + "Add coin" creates it

**Files:**
- Create: `src/swingbot/kronos_preset.py`
- Modify: `src/swingbot/web.py` (the add-coin / create-profile endpoint uses the preset)
- Test: `tests/test_kronos_preset.py`

**Interfaces:**
- Produces: `kronos_bracket_profile(symbol: str) -> dict` — a ready-to-save profile dict implementing the Balanced 15m POC strategy: `signals={"kronos_forecast": {"weight": 1.0, "pred_len": 4, "threshold_pct": 0.0075, "neutral_on_error": False}}`, `entry_threshold=1.0`, `timeframe="15m"`, `bracket_mode="pct"`, `tp_pct=0.015`, `sl_pct=0.01`, `max_concurrent=1`. Adding a coin via the API instantiates this — **no numeric inputs from the user**.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_kronos_preset.py
from swingbot.kronos_preset import kronos_bracket_profile
from swingbot.profile import StrategyProfile


def test_preset_is_a_valid_kronos_pct_strategy():
    d = kronos_bracket_profile("ETH/USD")
    p = StrategyProfile.from_dict(d)          # must validate
    assert p.symbol == "ETH/USD"
    assert p.timeframe == "15m"
    assert p.bracket_mode == "pct" and p.tp_pct == 0.015 and p.sl_pct == 0.01
    assert "kronos_forecast" in p.signals
    sig = p.signals["kronos_forecast"]
    assert sig["threshold_pct"] == 0.0075 and sig["neutral_on_error"] is False
    assert p.entry_threshold == 1.0           # score>=1 iff pct_change>=0.75%


def test_entry_threshold_fires_at_075pct():
    # With weight 1.0 and threshold_pct 0.0075, score = clamp(pct/0.0075,0,1);
    # so the confluence passes (score>=entry_threshold=1.0) exactly at pct>=0.75%.
    d = kronos_bracket_profile("BTC/USD")
    assert d["entry_threshold"] == 1.0
    assert d["signals"]["kronos_forecast"]["weight"] == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_kronos_preset.py -v` → Expected: FAIL (module missing).

- [ ] **Step 3: Implement** — `src/swingbot/kronos_preset.py`:

```python
from __future__ import annotations


def kronos_bracket_profile(symbol: str) -> dict:
    """System-owned 'Balanced 15m' Kronos predict->buy->fixed-bracket strategy.

    Fires a market BUY when Kronos predicts >= +0.75% over ~1h (pred_len 4 @ 15m),
    then exits on a fixed +1.5% TP / -1.0% SL. No user-tunable numbers.
    """
    return {
        "symbol": symbol,
        "timeframe": "15m",
        "signals": {
            "kronos_forecast": {
                "weight": 1.0,
                "pred_len": 4,
                "threshold_pct": 0.0075,
                "neutral_on_error": False,
            }
        },
        "entry_threshold": 1.0,
        "bracket_mode": "pct",
        "tp_pct": 0.015,
        "sl_pct": 0.01,
        "max_concurrent": 1,
    }
```

In `web.py`, point the add-coin/create-profile route at this preset: given a `symbol`, save `kronos_bracket_profile(symbol)` under a derived strategy name and arm it (reuse the existing `profiles.save`/`profiles.arm`; find the current add-coin handler via `grep -n "def .*coin\|profiles.save\|arm(" src/swingbot/web.py`).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_kronos_preset.py -v` → Expected: PASS. Then `.venv/bin/python -m pytest -q`.

- [ ] **Step 5: Commit + docker rebuild**

```bash
git add src/swingbot/kronos_preset.py src/swingbot/web.py tests/test_kronos_preset.py
git commit -m "feat(strategy): Kronos-bracket preset; Add coin instantiates it"
docker compose build swingbot && docker compose up -d swingbot
```

---

### Task 9: Surface "Kronos unavailable" truthfully

**Files:**
- Modify: `src/swingbot/orchestrator.py` (when the confluence's kronos signal reports `no_forecast`, emit a distinct decision detail)
- Test: `tests/test_pct_bracket.py` (append) or `tests/test_kronos_preset.py`

**Interfaces:**
- Produces: when the Kronos signal returns `{"error": "no_forecast"}` and the score stays below threshold, the `DecisionResult` carries `details={"kronos": "unavailable"}` (the existing `SIGNAL_BELOW_THRESHOLD` code is fine; the detail makes the UI/journal able to show "Kronos unavailable" rather than a generic below-threshold message).

- [ ] **Step 1: Write the failing test** — drive an orchestrator whose Kronos adapter returns `None` (forecast failure) and assert the decision detail flags kronos unavailable and that **no entry** occurs (HOLD). Reuse the Task 7 fakes.

```python
def test_kronos_unavailable_holds_and_flags(orch_kronos_down):
    decision = orch_kronos_down.tick(now=NOW)
    assert orch_kronos_down.state.load_pending_order() is None      # HOLD, no buy
    assert decision.details.get("kronos") == "unavailable"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pct_bracket.py::test_kronos_unavailable_holds_and_flags -v` → Expected: FAIL (no such detail).

- [ ] **Step 3: Implement** — after `conf = self.engine.evaluate(ctx)` and the `not conf.passed` branch, detect the kronos error from `conf.signals` and enrich the detail:

```python
        if not conf.passed:
            details = {"score": conf.score, "threshold": conf.threshold}
            kr = conf.signals.get("kronos_forecast")
            if kr is not None and kr.details.get("error") == "no_forecast":
                details["kronos"] = "unavailable"
            return DecisionResult(DecisionCode.SIGNAL_BELOW_THRESHOLD,
                                  "confluence score below entry threshold", details)
```

(`SignalResult` exposes `.details`; confirm the attribute name in `types.py` and match it.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pct_bracket.py -v` → Expected: PASS. Then `.venv/bin/python -m pytest -q`.

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/orchestrator.py tests/test_pct_bracket.py
git commit -m "feat(strategy): surface 'Kronos unavailable' in decision detail"
```

---

# Phase C — Remove obsolete subsystems

> These tasks are deletions + de-wiring. The deliverable is a **green gate** (`pytest -q`, `ruff check src/`, `npm run build`) with the subsystem and all its references gone. For each: delete the module(s) and their tests, remove imports/wiring, run the gate, fix fallout, commit. No new feature tests.

### Task 10: Remove `paper_probe`

**Files:** Delete `src/swingbot/signals/paper_probe.py`, `src/swingbot/probe_marker.py`, and their tests (`grep -rln "paper_probe\|probe_marker\|ProbeMarker\|probe_should_fire" tests/`).

- [ ] **Step 1:** Remove `"paper_probe": PaperProbeSignal` and its import from `src/swingbot/confluence.py:9,21`.
- [ ] **Step 2:** In `supervisor.py` remove probe wiring: the `probe_marker` ctor param (`__init__` ~126), `_probe_suppressed` (367), `probe_should_fire` import (27), and the `PROBE_COMPLETE` branch in `tick_all` (452–457). Keep `DecisionCode.PROBE_COMPLETE` only if other code references it; otherwise drop it from `types.py`.
- [ ] **Step 3:** In `webmain.py` remove `ProbeMarkerStore` import (38), `probe_marker`/`enable_probe` (40–41), and the `probe_marker=`/probe args to `PortfolioSupervisor(...)` (49–53).
- [ ] **Step 4:** Delete the modules + tests. Run gate: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src/`. Expected: green (probe tests gone; no dangling imports).
- [ ] **Step 5: Commit**

```bash
git rm src/swingbot/signals/paper_probe.py src/swingbot/probe_marker.py <probe tests>
git add src/swingbot/confluence.py src/swingbot/supervisor.py src/swingbot/webmain.py src/swingbot/types.py
git commit -m "chore: remove paper_probe subsystem"
docker compose build swingbot && docker compose up -d swingbot
```

### Task 11: Remove managed strategies + reconciler

**Files:** Delete `src/swingbot/managed_profiles.py` + tests (`grep -rln "managed_profiles\|reconcile_managed\|managed_meta\|note_managed" src/ tests/`).

- [ ] **Step 1:** In `supervisor.py` remove `managed_meta` import (22), `note_managed_decision` (360) and its call site in `tick_all` (472), the `reconcile` ctor param + its call in `build()` (256–257). Where `tick_all` called `note_managed_decision`, drop the line (the decision is already recorded via telemetry).
- [ ] **Step 2:** In `webmain.py` remove the `reconcile_managed_profiles` import (37), `_reconcile_managed` (44–47), `backup_dir` if now unused, and the `reconcile=_reconcile_managed` arg (53).
- [ ] **Step 3:** Remove any `kind`/`label`/managed surfacing that depended on `managed_meta` in `status()`/`/api/strategies` (search `grep -n "managed\|kind\|label" src/swingbot/supervisor.py src/swingbot/web.py`); leave generic strategy listing intact.
- [ ] **Step 4:** Delete module + tests. Run gate. Fix fallout. Expected: green.
- [ ] **Step 5: Commit** (`git rm` + `git add` the de-wired files) `-m "chore: remove managed-strategy reconciler"` then docker rebuild.

### Task 12: Remove auto-discovery

**Files:** Delete `src/swingbot/discovery.py`, `src/swingbot/strategy_search.py` + tests (`grep -rln "discovery\|strategy_search\|DiscoveryEngine\|good_history" src/ tests/`).

- [ ] **Step 1:** In `webmain.py` remove `DiscoveryEngine` import (13), `discovery = DiscoveryEngine(market)` (55), the `_df_from_market`/`metrics_dict`/`good_history`/`run_backtest`/`presets`/`StrategyProfile` discovery-only imports (61–65), `_backtest_ok` (72–82), and `discovery=`/`discovery_cache_path=` args to `create_app` (102–106).
- [ ] **Step 2:** In `web.py` remove the discovery APIRouter/endpoints (`grep -n "discovery" src/swingbot/web.py`) and the `discovery`/`discovery_cache_path` params of `create_app`.
- [ ] **Step 3:** Delete the Discover frontend page + its route + its `api.js` methods (`grep -rln "iscover" frontend/src`).
- [ ] **Step 4:** Delete modules + tests. Run gate + `cd frontend && npm run build`. Expected: green.
- [ ] **Step 5: Commit** `-m "chore: remove auto-discovery subsystem"` then docker rebuild.

### Task 13: Remove the per-trade Ollama brain

**Files:** Delete `src/swingbot/decision/` (whole package) + tests (`grep -rln "decision\.\|DecisionBrain\|brain" src/ tests/` — be careful to keep `DecisionResult`/`DecisionCode` from `types.py`, which are unrelated).

- [ ] **Step 1:** In `webmain.py` remove the brain block: imports (57–59, 61–65 if not already gone with discovery), `_ollama_factory` (67–70), `notifier`/`brain` construction (84–91), `brain=`/`brain.get_discovery` (107–108). Keep `DiscordNotifier` only if used elsewhere; otherwise remove.
- [ ] **Step 2:** In `web.py` remove brain endpoints + the `brain` param of `create_app` (`grep -n "brain" src/swingbot/web.py`).
- [ ] **Step 3:** In `profiles.py` remove the `brain_*` keys from `_PORTFOLIO_DEFAULTS` (129–135) and `get_discord_webhook`/`set_discord_webhook` if the notifier is gone.
- [ ] **Step 4:** Delete the Brain frontend page + route + `api.js` methods (`grep -rln "rain" frontend/src`).
- [ ] **Step 5:** Delete package + tests. Run full gate + `npm run build`. Expected: green.
- [ ] **Step 6: Commit** `-m "chore: remove per-trade Ollama decision brain"` then docker rebuild.

---

# Phase D — Deterministic self-management defaults

### Task 14: Default to hard auto-rebalance with equal-weight auto-derive

**Files:**
- Modify: `src/swingbot/supervisor.py` (`_run_rebalance` / build) and/or `src/swingbot/rebalance.py`
- Test: `tests/test_rebalance*.py` (append) — find with `grep -rln "Rebalancer\|allocated_equity" tests/`

**Interfaces:**
- Produces: when rebalance is enabled but `rebalance_targets` is empty, the effective targets are **equal-weight across armed strategies** (auto-derived), so the user never sets a weight. Default `RebalanceSettings(enabled=True, mode="hard")` for the POC (was `enabled=False`).

- [ ] **Step 1: Write the failing test**

```python
def test_equal_weight_when_no_targets():
    from swingbot.rebalance import equal_weight_targets
    assert equal_weight_targets(["a", "b", "c", "d"]) == {
        "a": 0.25, "b": 0.25, "c": 0.25, "d": 0.25}
    assert equal_weight_targets([]) == {}
```

- [ ] **Step 2: Run** → FAIL (`equal_weight_targets` missing).
- [ ] **Step 3: Implement** in `rebalance.py`:

```python
def equal_weight_targets(names: list[str]) -> dict[str, float]:
    if not names:
        return {}
    w = 1.0 / len(names)
    return {n: w for n in names}
```

In `supervisor._run_rebalance`, when `self._rebalance_targets` is empty use `equal_weight_targets(sorted(self._strategies))` for the `targets=` arg. Set the POC default in `ProfileStore.get_rebalance_settings()` (or where defaults originate) to `enabled=True, mode="hard"`.

- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q` → PASS (existing rebalance tests still green; the change only affects the empty-targets path).
- [ ] **Step 5: Commit** `-m "feat(rebalance): equal-weight auto-derive; hard auto default"` then docker rebuild.

---

# Phase E — LLM advisor (bounded auto-apply, config tuning only)

### Task 15: Performance-digest builder

**Files:** Create `src/swingbot/advisor/__init__.py`, `src/swingbot/advisor/digest.py`; Test `tests/test_advisor_digest.py`.

**Interfaces:**
- Produces: `build_digest(strategies: dict[str, dict]) -> dict` where each input value has keys `trades, wins, losses, avg_win, avg_loss, drawdown, params, weight, equity_curve` and the output is a compact per-coin summary including `win_rate` (= wins/trades, 0 if no trades). Pure function; no I/O.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_advisor_digest.py
from swingbot.advisor.digest import build_digest


def test_digest_computes_win_rate_and_passes_params():
    raw = {"BTC/USD": {"trades": 10, "wins": 6, "losses": 4, "avg_win": 1.5,
                       "avg_loss": -1.0, "drawdown": -0.03,
                       "params": {"threshold_pct": 0.0075, "tp_pct": 0.015, "sl_pct": 0.01},
                       "weight": 0.5, "equity_curve": [100, 101, 99, 103]}}
    d = build_digest(raw)
    assert d["BTC/USD"]["win_rate"] == 0.6
    assert d["BTC/USD"]["params"]["tp_pct"] == 0.015
    assert d["BTC/USD"]["drawdown"] == -0.03


def test_digest_zero_trades_is_safe():
    d = build_digest({"ETH/USD": {"trades": 0, "wins": 0, "losses": 0, "avg_win": 0,
                                  "avg_loss": 0, "drawdown": 0, "params": {}, "weight": 0,
                                  "equity_curve": []}})
    assert d["ETH/USD"]["win_rate"] == 0.0
```

- [ ] **Step 2: Run** → FAIL (module missing).
- [ ] **Step 3: Implement** `digest.py`:

```python
from __future__ import annotations


def build_digest(strategies: dict[str, dict]) -> dict:
    out: dict[str, dict] = {}
    for sym, s in strategies.items():
        trades = int(s.get("trades", 0))
        wins = int(s.get("wins", 0))
        out[sym] = {
            "trades": trades,
            "win_rate": (wins / trades) if trades else 0.0,
            "avg_win": float(s.get("avg_win", 0.0)),
            "avg_loss": float(s.get("avg_loss", 0.0)),
            "drawdown": float(s.get("drawdown", 0.0)),
            "params": dict(s.get("params", {})),
            "weight": float(s.get("weight", 0.0)),
            "equity_curve": list(s.get("equity_curve", []))[-50:],
        }
    return out
```

- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `-m "feat(advisor): performance digest builder"`.

---

### Task 16: Proposal schema + clamp-to-band validation

**Files:** Create `src/swingbot/advisor/bands.py`, `src/swingbot/advisor/schema.py`; Test `tests/test_advisor_schema.py`.

**Interfaces:**
- Produces: `BANDS: dict[str, dict[str, tuple[float, float]]]` keyed by risk dial (`cautious`/`balanced`/`aggressive`) → param → `(lo, hi)` for `threshold_pct`, `tp_pct`, `sl_pct`, `weight`. `validate_proposal(raw: dict, dial: str) -> tuple[dict, list[str]]` returns `(applied_changes, dropped_reasons)`: well-formed per-coin numeric nudges clamped into the dial's band are kept; non-numeric/unknown params/unparseable entries are dropped with a logged reason; `enable`/`disable` booleans pass through.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_advisor_schema.py
from swingbot.advisor.schema import validate_proposal


def test_in_band_change_is_kept():
    raw = {"BTC/USD": {"tp_pct": 0.02, "rationale": "winners run"}}
    applied, dropped = validate_proposal(raw, dial="balanced")
    assert applied["BTC/USD"]["tp_pct"] == 0.02
    assert not dropped


def test_out_of_band_is_clamped():
    raw = {"BTC/USD": {"tp_pct": 0.99}}     # absurd
    applied, dropped = validate_proposal(raw, dial="balanced")
    assert applied["BTC/USD"]["tp_pct"] <= 0.05      # clamped to band hi
    assert any("clamped" in d for d in dropped)


def test_unknown_param_dropped():
    raw = {"BTC/USD": {"leverage": 10}}
    applied, dropped = validate_proposal(raw, dial="balanced")
    assert "BTC/USD" not in applied or "leverage" not in applied.get("BTC/USD", {})
    assert any("leverage" in d for d in dropped)


def test_unparseable_dropped_not_raised():
    applied, dropped = validate_proposal({"BTC/USD": "not-a-dict"}, dial="balanced")
    assert applied == {} and dropped
```

- [ ] **Step 2: Run** → FAIL (modules missing).
- [ ] **Step 3: Implement** `bands.py`:

```python
from __future__ import annotations

_TUNABLE = ("threshold_pct", "tp_pct", "sl_pct", "weight")

BANDS = {
    "cautious":   {"threshold_pct": (0.005, 0.015), "tp_pct": (0.008, 0.025),
                   "sl_pct": (0.005, 0.012), "weight": (0.0, 1.0)},
    "balanced":   {"threshold_pct": (0.004, 0.020), "tp_pct": (0.008, 0.050),
                   "sl_pct": (0.005, 0.020), "weight": (0.0, 1.0)},
    "aggressive": {"threshold_pct": (0.003, 0.030), "tp_pct": (0.010, 0.080),
                   "sl_pct": (0.008, 0.030), "weight": (0.0, 1.0)},
}
```

`schema.py`:

```python
from __future__ import annotations

from swingbot.advisor.bands import BANDS, _TUNABLE


def validate_proposal(raw: dict, dial: str) -> tuple[dict, list[str]]:
    band = BANDS.get(dial, BANDS["balanced"])
    applied: dict[str, dict] = {}
    dropped: list[str] = []
    for sym, changes in (raw or {}).items():
        if not isinstance(changes, dict):
            dropped.append(f"{sym}: not an object")
            continue
        kept: dict = {}
        for key, val in changes.items():
            if key in ("rationale",):
                kept[key] = str(val)
                continue
            if key in ("enable", "disable") and isinstance(val, bool):
                kept[key] = val
                continue
            if key not in _TUNABLE:
                dropped.append(f"{sym}.{key}: unknown param")
                continue
            try:
                num = float(val)
            except (TypeError, ValueError):
                dropped.append(f"{sym}.{key}: not numeric")
                continue
            lo, hi = band[key]
            clamped = max(lo, min(hi, num))
            if clamped != num:
                dropped.append(f"{sym}.{key}: clamped {num}->{clamped}")
            kept[key] = clamped
        if any(k in _TUNABLE or k in ("enable", "disable") for k in kept):
            applied[sym] = kept
    return applied, dropped
```

- [ ] **Step 4: Run** → PASS (4 passed). **Step 5: Commit** `-m "feat(advisor): proposal schema + clamp-to-band validation"`.

---

### Task 17: Tuning journal with revert

**Files:** Create `src/swingbot/advisor/journal.py`; Test `tests/test_advisor_journal.py`.

**Interfaces:**
- Produces: `TuningJournal(db_path)` with `record(entries: list[dict]) -> str` (one batch id; each entry `{symbol, param, before, after, rationale, ts}`), `list_entries() -> list[dict]`, `revert(batch_id) -> list[dict]` (returns the inverse changes `{symbol, param, value=before}` and marks the batch reverted), `revert_all() -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_advisor_journal.py
from swingbot.advisor.journal import TuningJournal


def test_record_and_list(tmp_path):
    j = TuningJournal(str(tmp_path / "tuning.db"))
    bid = j.record([{"symbol": "BTC/USD", "param": "tp_pct", "before": 0.015,
                     "after": 0.02, "rationale": "winners run"}])
    rows = j.list_entries()
    assert len(rows) == 1 and rows[0]["batch_id"] == bid
    assert rows[0]["after"] == 0.02


def test_revert_returns_inverse(tmp_path):
    j = TuningJournal(str(tmp_path / "tuning.db"))
    bid = j.record([{"symbol": "BTC/USD", "param": "tp_pct", "before": 0.015,
                     "after": 0.02, "rationale": "x"}])
    inverse = j.revert(bid)
    assert inverse == [{"symbol": "BTC/USD", "param": "tp_pct", "value": 0.015}]
    assert j.list_entries()[0]["reverted"] is True
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** a small SQLite-backed `TuningJournal` (mirror `ProbeMarkerStore`/`RuntimeStateStore` style: `check_same_thread=False` + `RLock`; columns `batch_id, symbol, param, before, after, rationale, ts, reverted`). `revert` selects non-reverted rows for the batch, flips `reverted=1`, returns `[{symbol, param, value: before}]`. `revert_all` does the same across all non-reverted rows.
- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `-m "feat(advisor): tuning journal with one-click revert"`.

---

### Task 18: Advisor model client (on-demand load/unload)

**Files:** Create `src/swingbot/advisor/client.py`; Test `tests/test_advisor_service.py` (client part).

**Interfaces:**
- Produces: `AdvisorClient(model, url=None)` with `review(digest: dict) -> dict` — builds the prompt from the digest, calls the local model (llama.cpp/Ollama HTTP), parses the JSON object out of the reply, returns the raw proposal dict (validation happens in Task 16). Network/parse failure → returns `{}` (never raises). Reuse the deleted brain's Ollama HTTP plumbing **only if clean**; otherwise a minimal `requests.post` to `/api/generate`. The model is loaded by the server on demand and not held resident by this process.

- [ ] **Step 1: Write the failing test** (inject a fake transport so no real model is needed):

```python
def test_advisor_client_parses_json(monkeypatch):
    from swingbot.advisor.client import AdvisorClient
    c = AdvisorClient(model="gemma-4-e2b-it-qat-q4")
    c._raw_reply = lambda prompt: 'noise {"BTC/USD": {"tp_pct": 0.02}} trailing'
    assert c.review({"BTC/USD": {"win_rate": 0.6}}) == {"BTC/USD": {"tp_pct": 0.02}}


def test_advisor_client_bad_reply_returns_empty():
    from swingbot.advisor.client import AdvisorClient
    c = AdvisorClient(model="x")
    c._raw_reply = lambda prompt: "the model rambled with no json"
    assert c.review({}) == {}
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** `client.py` with `_raw_reply(prompt)` doing the HTTP call (overridable in tests), `review()` building the prompt + extracting the first balanced `{...}` block via a brace-matching scan and `json.loads`, returning `{}` on any failure.
- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `-m "feat(advisor): on-demand local-LLM client"`.

---

### Task 19: Advisor service — bounded auto-apply, scheduled

**Files:** Create `src/swingbot/advisor/service.py`; Modify `src/swingbot/supervisor.py` (schedule hook); Test `tests/test_advisor_service.py`.

**Interfaces:**
- Produces: `AdvisorService(client, journal, profiles, get_digest, get_dial)` with `run_review() -> dict` — calls `client.review(get_digest())`, `validate_proposal(raw, get_dial())`, applies in-band numeric changes to the live `StrategyProfile`s via `profiles.save(...)`, records the batch in the journal, and returns `{"applied": ..., "dropped": ..., "batch_id": ...}`. **Never** touches order placement. The supervisor calls `run_review()` on a cadence (every N cycles / hours) guarded so it never blocks `tick_all`.

- [ ] **Step 1: Write the failing test** — drive `AdvisorService.run_review()` with a fake client returning a proposal, assert: in-band change is saved to the profile, the journal has a batch, out-of-band is dropped, and **no broker method is ever called** (assert with a broker spy that fails if any submit_* is hit).

```python
def test_run_review_applies_in_band_and_journals(tmp_path, fake_profiles, spy_broker):
    from swingbot.advisor.service import AdvisorService
    from swingbot.advisor.journal import TuningJournal
    svc = AdvisorService(
        client=FakeClient({"BTC/USD": {"tp_pct": 0.02, "rationale": "r"}}),
        journal=TuningJournal(str(tmp_path / "t.db")),
        profiles=fake_profiles, get_digest=lambda: {"BTC/USD": {}},
        get_dial=lambda: "balanced")
    out = svc.run_review()
    assert out["applied"]["BTC/USD"]["tp_pct"] == 0.02
    assert fake_profiles.get("btc")["tp_pct"] == 0.02   # persisted to live profile
    assert spy_broker.calls == []                        # advisor never trades
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** `service.py` composing Tasks 15–17; wire a guarded periodic `run_review()` call into the supervisor loop (e.g. every K ticks, in a try/except that records but never raises into `tick_all`). Gate the cadence behind a setting so tests can call `run_review()` directly.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_advisor_service.py -q` → PASS. Then full `pytest -q`.
- [ ] **Step 5: Commit** `-m "feat(advisor): bounded auto-apply service + scheduled review"` then docker rebuild.

---

### Task 20: Risk dial setting + `/api/advisor/*` endpoints

**Files:** Modify `src/swingbot/profiles.py` (risk_dial get/set, default `balanced`), `src/swingbot/web.py` (endpoints); Test `tests/test_web_advisor.py`.

**Interfaces:**
- Produces: `ProfileStore.get_risk_dial() -> str` (default `"balanced"`), `set_risk_dial(name)` (accepts `cautious`/`balanced`/`aggressive`). Endpoints: `GET /api/advisor/notes` (recent journal entries + rationales), `GET /api/advisor/journal`, `POST /api/advisor/revert {"batch_id"}` and `POST /api/advisor/revert-all` (token-gated; reverting also re-saves the reverted param values back onto the profiles), `GET/PUT /api/risk-dial`.

- [ ] **Step 1: Write the failing test** — `tests/test_web_advisor.py`: GET notes returns the journal list; risk-dial GET defaults `balanced`, PUT persists, PUT unknown → 400; revert returns ok and the inverse is applied. (Reuse `tests/test_web.py` fixtures.)
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** the `ProfileStore` dial methods (same shape as `data_source`) and the endpoints (reuse `require_token`).
- [ ] **Step 4: Run** → PASS, then full gate. **Step 5: Commit** `-m "feat(advisor): risk dial + advisor API"` then docker rebuild.

---

### Task 21: UI — advisor notes feed, tuning journal/revert, risk dial

**Files:** Modify `frontend/src/` Mission Control (notes feed) + Settings (risk dial select + tuning journal with revert buttons) + `frontend/src/lib/api.js`.

- [ ] **Step 1:** Add `api.js` methods: `getAdvisorNotes`, `getAdvisorJournal`, `revertTuning(batchId)`, `revertAllTuning`, `getRiskDial`, `setRiskDial`.
- [ ] **Step 2:** Mission Control: add an "Advisor notes" panel that polls `getAdvisorNotes()` and renders the plain-English rationales (read-only feed).
- [ ] **Step 3:** Settings: add the risk-dial `<select>` (Cautious/Balanced/Aggressive, default Balanced) and a "Tuning journal" list with per-batch **Revert** + a **Revert all** button. No numeric fields.
- [ ] **Step 4: Verify** `cd frontend && npm run build` (+ `npm run test` if a lib function added). **Step 5: Commit** `-m "feat(ui): advisor notes, tuning journal, risk dial"`.

---

# Phase F — Infra + final verification

### Task 22: Settings shrink — remove orphaned numeric controls

**Files:** Modify `frontend/src/` Settings page.

- [ ] **Step 1:** Remove any remaining numeric strategy-config inputs left by deleted subsystems (brain settings, discovery, managed-strategy editors, manual rebalance weight entry). The Rebalance panel stays but with **no manual weight entry** (weights auto-derive). Confirm Settings = Broker connection · Data source · Risk dial · Rebalance (read-only weights) · Tuning journal.
- [ ] **Step 2: Verify** `cd frontend && npm run build`. **Step 3: Commit** `-m "feat(ui): shrink Settings to no-numeric-fields"`.

### Task 23: Enable the nvidia Docker runtime

**Files:** Modify `docker-compose.override.yml` (currently `runtime: runc`).

- [ ] **Step 1:** Replace the `runtime: runc` override for `swingbot` with `runtime: nvidia` + GPU device reservation:

```yaml
services:
  swingbot:
    runtime: nvidia
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

- [ ] **Step 2:** `docker compose build swingbot && docker compose up -d swingbot`; verify the container starts and `nvidia-smi` is visible inside (`docker compose exec swingbot nvidia-smi`). If the host daemon still lacks the nvidia runtime, document it and keep `runc` (Kronos then HOLDs on CPU, surfaced truthfully) — do not block the rest of the plan.
- [ ] **Step 3: Commit** `-m "infra: enable nvidia docker runtime for Kronos GPU"`.

### Task 24: Full gate + live smoke

- [ ] **Step 1:** Run the complete gate: `.venv/bin/python -m pytest -q` (all green), `.venv/bin/ruff check src/` (clean), `cd frontend && npm run build` (green), `cd frontend && npm run test` (green).
- [ ] **Step 2:** `docker compose build swingbot && docker compose up -d swingbot`.
- [ ] **Step 3: Live smoke (the POC acceptance):** with **no broker connected**, confirm via the UI / API that (a) `GET /api/data-source` → coinbase, (b) a coin's chart **populates** from Coinbase data (no "no fresh closed bar" error), (c) Mission Control renders equity/per-coin state + advisor notes feed, (d) deleted routes 404 (`/api/discovery`, brain, agent). Capture a screenshot to `docs/kronos-poc-smoke.png`.
- [ ] **Step 4:** Update `docs/ROADMAP_STATUS.md` (mark the Kronos POC implemented + live; record the gate numbers + commit range). **Step 5: Commit** `-m "docs: Kronos POC paper trader complete + live-verified"`.

---

## Self-Review (completed by plan author)

**Spec coverage:** §3 data decoupling → Tasks 1–5; §4 Kronos bracket strategy → Tasks 6–9 (entry math reused from `KronosForecastSignal`, fixed-% bracket new); §5 deterministic foundation → Task 14 (+ existing `RiskManager` breakers, unchanged); §6 LLM advisor → Tasks 15–21; §7 UI → Tasks 5, 21, 22; §8 removals → Tasks 10–13; §9 infra → Task 23; §11 testing/gate → every task + Task 24. **All spec sections map to tasks.**

**Placeholder scan:** Test fixtures in web/orchestrator tasks reference the repo's existing helpers (`make_client`, `token_headers`, orchestrator fakes) — flagged inline as "copy from the existing test file," not invented, because the exact fixture names live in the current test suite and must be matched, not guessed.

**Type consistency:** `data_source` (str, coinbase default) consistent across Tasks 1–5; `bracket_mode`/`tp_pct`/`sl_pct` consistent Tasks 6–8; `validate_proposal(raw, dial) -> (applied, dropped)` consistent Tasks 16/19/20; `TuningJournal.record/list_entries/revert` consistent Tasks 17/19/20; risk dial values `cautious|balanced|aggressive` consistent Tasks 16/20/21.
