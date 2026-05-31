# Strategy Presets + Guided Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a preset strategy library and a backtest-driven guided builder (Coin + Risk + Style + AI) that both feed the existing detailed Strategy form.

**Architecture:** Two pure backend modules — `presets.py` (curated archetypes + risk/style→params mapping → candidate profiles) and `strategy_search.py` (runs candidates through the existing `run_backtest` over cached `MarketData` candles, ranks by expectancy). Three new FastAPI endpoints expose them. The Strategy page gains a preset gallery + builder that prefill the existing form; the form stays the single save path.

**Tech Stack:** Python 3.12, FastAPI, pandas, pytest (`.venv/bin/python -m pytest`); React 18 + Vite (no JS test runner — verified via `npm run build` + Playwright).

**Branch:** `feat/strategy-presets-builder` (already created).

**Spec:** `docs/superpowers/specs/2026-05-31-strategy-presets-builder-design.md`

---

## Task 1: Preset archetypes + candidate builder

**Files:**
- Create: `src/swingbot/presets.py`
- Test: `tests/test_presets.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_presets.py
import pytest

from swingbot.presets import ARCHETYPES, archetype_profile, build_candidates
from swingbot.profile import StrategyProfile


def test_archetypes_have_required_fields():
    keys = {a.key for a in ARCHETYPES}
    assert keys == {"conservative", "balanced", "aggressive", "ai_kronos"}
    for a in ARCHETYPES:
        assert a.name and a.description and a.signals


def test_archetype_profile_is_valid_and_overrides_symbol():
    bal = next(a for a in ARCHETYPES if a.key == "balanced")
    p = archetype_profile(bal, symbol="ETH/USD")
    StrategyProfile.from_dict(p)          # must not raise
    assert p["symbol"] == "ETH/USD"
    assert "oversold" in p["signals"] and "vwap" in p["signals"]


def test_build_candidates_non_ai():
    cs = build_candidates("TRX/USD", "balanced", "swing", ai=False)
    assert 1 <= len(cs) <= 6
    for c in cs:
        StrategyProfile.from_dict(c["profile"])
        assert "kronos_forecast" not in c["profile"]["signals"]
        assert c["profile"]["symbol"] == "TRX/USD"
        assert c["profile"]["timeframe"] == "15m"     # swing


def test_build_candidates_ai_includes_kronos():
    cs = build_candidates("TRX/USD", "aggressive", "scalp", ai=True)
    assert 1 <= len(cs) <= 3
    assert all("kronos_forecast" in c["profile"]["signals"] for c in cs)
    assert all(c["profile"]["timeframe"] == "5m" for c in cs)   # scalp


def test_build_candidates_rejects_bad_knobs():
    with pytest.raises(ValueError):
        build_candidates("TRX/USD", "nope", "swing")
    with pytest.raises(ValueError):
        build_candidates("TRX/USD", "balanced", "nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_presets.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.presets'`

- [ ] **Step 3: Write the implementation**

```python
# src/swingbot/presets.py
from __future__ import annotations

from dataclasses import dataclass, field

from swingbot.profile import StrategyProfile

# risk knob -> sizing / exit / breaker params
RISK = {
    "conservative": dict(risk_per_trade=0.005, stop_atr_mult=1.2, take_profit_atr_mult=2.4,
                         entry_threshold=0.45, daily_loss_limit_pct=0.03, max_consecutive_losses=3),
    "balanced":     dict(risk_per_trade=0.01,  stop_atr_mult=1.5, take_profit_atr_mult=2.0,
                         entry_threshold=0.35, daily_loss_limit_pct=0.05, max_consecutive_losses=4),
    "aggressive":   dict(risk_per_trade=0.02,  stop_atr_mult=2.0, take_profit_atr_mult=3.0,
                         entry_threshold=0.30, daily_loss_limit_pct=0.08, max_consecutive_losses=5),
}

# style knob -> timeframe / horizon / window params
STYLE = {
    "scalp":    dict(timeframe="5m",  max_hold_bars=24, regime_ma_period=50,  vwap_window=48, rs_lookback=48, cooldown_minutes=30),
    "swing":    dict(timeframe="15m", max_hold_bars=32, regime_ma_period=50,  vwap_window=96, rs_lookback=96, cooldown_minutes=60),
    "position": dict(timeframe="1h",  max_hold_bars=24, regime_ma_period=100, vwap_window=96, rs_lookback=96, cooldown_minutes=240),
}


@dataclass
class Archetype:
    key: str
    name: str
    description: str
    signals: list[str]
    risk: str = "balanced"          # implied risk for the preset gallery
    needs_ai: bool = False


ARCHETYPES: list[Archetype] = [
    Archetype("conservative", "Conservative",
              "RSI dip buys gated by a trend filter. Tight risk, picky entries.",
              ["oversold"], risk="conservative"),
    Archetype("balanced", "Balanced",
              "RSI dip + VWAP discount. A steady all-rounder.",
              ["oversold", "vwap"], risk="balanced"),
    Archetype("aggressive", "Aggressive",
              "RSI + VWAP + relative strength. Looser threshold, wider targets.",
              ["oversold", "vwap", "relative_strength"], risk="aggressive"),
    Archetype("ai_kronos", "AI-Kronos",
              "Balanced plus the Kronos AI forecast signal.",
              ["oversold", "vwap", "kronos_forecast"], risk="balanced", needs_ai=True),
]


def _profile_for(arch: Archetype, symbol: str, risk: str, style: str) -> dict:
    r = RISK[risk]
    s = STYLE[style]
    signals: dict = {}
    if "oversold" in arch.signals:
        signals["oversold"] = {"weight": 0.5, "oversold_level": 45, "period": 14}
    if "vwap" in arch.signals:
        signals["vwap"] = {"weight": 0.3, "window": s["vwap_window"], "max_dist": 0.03}
    if "relative_strength" in arch.signals:
        signals["relative_strength"] = {"weight": 0.2, "band": 0.02, "lookback": s["rs_lookback"]}
    if "kronos_forecast" in arch.signals:
        signals["kronos_forecast"] = {"weight": 0.25, "pred_len": 4, "threshold_pct": 0.02}
    return {
        "symbol": symbol, "benchmark_symbol": "BTC/USD", "timeframe": s["timeframe"],
        "entry_threshold": r["entry_threshold"], "regime_ma_period": s["regime_ma_period"],
        "atr_period": 14, "stop_atr_mult": r["stop_atr_mult"],
        "take_profit_atr_mult": r["take_profit_atr_mult"], "max_hold_bars": s["max_hold_bars"],
        "risk_per_trade": r["risk_per_trade"], "max_position_frac": 0.25,
        "daily_loss_limit_pct": r["daily_loss_limit_pct"],
        "max_consecutive_losses": r["max_consecutive_losses"],
        "cooldown_minutes": s["cooldown_minutes"], "signals": signals,
    }


def archetype_profile(arch: Archetype, symbol: str = "BTC/USD", style: str = "swing") -> dict:
    """A concrete profile for an archetype (for the preset gallery)."""
    return _profile_for(arch, symbol, arch.risk, style)


def build_candidates(symbol: str, risk: str, style: str, ai: bool = False,
                     max_candidates: int = 6, max_ai: int = 3) -> list[dict]:
    """Bounded set of {label, profile} candidates for the backtest search."""
    if risk not in RISK:
        raise ValueError(f"unknown risk {risk!r}; choose from {sorted(RISK)}")
    if style not in STYLE:
        raise ValueError(f"unknown style {style!r}; choose from {sorted(STYLE)}")

    out: list[dict] = []
    if ai:
        arch = next(a for a in ARCHETYPES if a.needs_ai)
        base = _profile_for(arch, symbol, risk, style)
        out.append({"label": "AI-Kronos", "profile": base})
        stricter = dict(base)
        stricter["entry_threshold"] = round(base["entry_threshold"] + 0.1, 3)
        out.append({"label": "AI-Kronos (stricter)", "profile": stricter})
        longer = dict(base)
        sig = dict(base["signals"])
        kf = dict(sig["kronos_forecast"]); kf["pred_len"] = 8
        sig["kronos_forecast"] = kf; longer["signals"] = sig
        out.append({"label": "AI-Kronos (longer horizon)", "profile": longer})
        return out[:max_ai]

    for arch in ARCHETYPES:
        if arch.needs_ai:
            continue
        out.append({"label": arch.name, "profile": _profile_for(arch, symbol, risk, style)})
    bal = next(a for a in ARCHETYPES if a.key == "balanced")
    strict = dict(_profile_for(bal, symbol, risk, style))
    strict["entry_threshold"] = round(strict["entry_threshold"] + 0.1, 3)
    out.append({"label": "Balanced (stricter)", "profile": strict})
    return out[:max_candidates]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_presets.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/presets.py tests/test_presets.py
git commit -m "feat: strategy preset archetypes + candidate builder"
```

---

## Task 2: Backtest search over candidates

**Files:**
- Create: `src/swingbot/strategy_search.py`
- Test: `tests/test_strategy_search.py`

Note: `run_backtest(df, profile, benchmark_df=None)` returns `(list[Trade], Metrics)` and needs a DataFrame with columns `ts, open, high, low, close, volume` (`ts` = UTC datetime). `MarketData.get(symbol, timeframe, limit)` returns dicts `{time, open, high, low, close, volume}` with `time` = epoch seconds.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_strategy_search.py
from types import SimpleNamespace

import swingbot.strategy_search as ss
from swingbot.strategy_search import backtest_profile, metrics_dict, search


def _bars(n=200, start=100.0):
    out, p, t0 = [], start, 1_700_000_000
    for i in range(n):
        p *= 1.001 if i % 3 else 0.999
        out.append({"time": t0 + i * 900, "open": p, "high": p * 1.01,
                    "low": p * 0.99, "close": p * 1.002, "volume": 1000 + i})
    return out


class FakeMarket:
    def __init__(self, bars):
        self._bars = bars
    def get(self, symbol, timeframe, limit=500, max_age=None):
        return self._bars[-limit:]


def test_metrics_dict_uses_getattr_defaults():
    m = SimpleNamespace(n_trades=3, win_rate=0.5, expectancy=0.4)
    d = metrics_dict(m)
    assert d["n_trades"] == 3 and d["expectancy"] == 0.4
    assert d["profit_factor"] is None     # absent -> None, never raises


def test_backtest_profile_runs_end_to_end():
    market = FakeMarket(_bars(250))
    profile = {"symbol": "TRX/USD", "timeframe": "15m",
               "signals": {"oversold": {"weight": 1.0, "oversold_level": 45, "period": 14}}}
    m = backtest_profile(market, profile)
    assert m.n_trades >= 0     # valid Metrics regardless of trade count


def test_search_ranks_by_expectancy_and_flags_recommended(monkeypatch):
    market = FakeMarket(_bars(250))

    def fake_bt(_market, profile, lookback=1000):
        # expectancy keyed off entry_threshold so order is deterministic
        et = profile["entry_threshold"]
        return SimpleNamespace(n_trades=10, win_rate=0.5, expectancy=1.0 - et)

    monkeypatch.setattr(ss, "backtest_profile", fake_bt)
    res = search(market, "TRX/USD", "balanced", "swing", ai=False)
    metrics_rows = [r for r in res["results"] if r["metrics"]]
    exps = [r["metrics"]["expectancy"] for r in metrics_rows]
    assert exps == sorted(exps, reverse=True)              # ranked desc
    assert res["results"][0]["recommended"] is True
    assert sum(1 for r in res["results"] if r["recommended"]) == 1


def test_search_captures_candidate_errors(monkeypatch):
    market = FakeMarket(_bars(250))

    def boom(_market, profile, lookback=1000):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(ss, "backtest_profile", boom)
    res = search(market, "TRX/USD", "balanced", "swing", ai=False)
    assert all(r["metrics"] is None and r["error"] == "kaboom" for r in res["results"])
    assert all(r["recommended"] is False for r in res["results"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_strategy_search.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.strategy_search'`

- [ ] **Step 3: Write the implementation**

```python
# src/swingbot/strategy_search.py
from __future__ import annotations

import pandas as pd

from swingbot.backtest import run_backtest
from swingbot.presets import build_candidates
from swingbot.profile import StrategyProfile

_CANON = ["ts", "open", "high", "low", "close", "volume"]


class InsufficientData(Exception):
    pass


def _df_from_market(market, symbol: str, timeframe: str, lookback: int) -> pd.DataFrame:
    bars = market.get(symbol, timeframe, lookback)
    if len(bars) < 30:
        raise InsufficientData(
            f"only {len(bars)} bars for {symbol} {timeframe}; need >=30 to backtest")
    df = pd.DataFrame(bars).rename(columns={"time": "ts"})
    df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df[_CANON].sort_values("ts").reset_index(drop=True)


def metrics_dict(m) -> dict:
    """Serialize a Metrics object defensively (unknown fields -> None)."""
    keys = ["n_trades", "win_rate", "expectancy", "profit_factor",
            "max_drawdown", "avg_win", "avg_loss", "total_return"]
    return {k: getattr(m, k, None) for k in keys}


def backtest_profile(market, profile_dict: dict, lookback: int = 1000):
    """Run one profile through the real backtest over cached candles. Returns Metrics."""
    profile = StrategyProfile.from_dict(profile_dict)
    df = _df_from_market(market, profile.symbol, profile.timeframe, lookback)
    bench = None
    if "relative_strength" in profile.signals:
        bench = _df_from_market(market, profile.benchmark_symbol, profile.timeframe, lookback)
    _trades, metrics = run_backtest(df, profile, benchmark_df=bench)
    return metrics


def search(market, symbol: str, risk: str, style: str, ai: bool = False,
           lookback: int = 1000) -> dict:
    """Backtest a bounded candidate set and rank by expectancy."""
    candidates = build_candidates(symbol, risk, style, ai)
    rows = []
    for c in candidates:
        try:
            m = backtest_profile(market, c["profile"], lookback)
            rows.append({"label": c["label"], "profile": c["profile"], "metrics": m, "error": None})
        except Exception as e:  # one bad candidate never aborts the search
            rows.append({"label": c["label"], "profile": c["profile"], "metrics": None, "error": str(e)})

    ok = [r for r in rows if r["metrics"] is not None]
    ok.sort(key=lambda r: (r["metrics"].expectancy, r["metrics"].win_rate, r["metrics"].n_trades),
            reverse=True)
    bad = [r for r in rows if r["metrics"] is None]

    out = []
    for i, r in enumerate(ok + bad):
        out.append({
            "label": r["label"], "profile": r["profile"],
            "metrics": metrics_dict(r["metrics"]) if r["metrics"] is not None else None,
            "error": r["error"], "recommended": r["metrics"] is not None and i == 0,
        })
    return {"symbol": symbol, "risk": risk, "style": style, "ai": ai, "results": out}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_strategy_search.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/strategy_search.py tests/test_strategy_search.py
git commit -m "feat: backtest-driven candidate search + ranking"
```

---

## Task 3: Web endpoints (presets / backtest / build)

**Files:**
- Modify: `src/swingbot/web.py`
- Test: `tests/test_web_strategy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web_strategy.py
from types import SimpleNamespace

from fastapi.testclient import TestClient

from swingbot.web import create_app


def _bars(n=250, start=100.0):
    out, p, t0 = [], start, 1_700_000_000
    for i in range(n):
        p *= 1.001 if i % 3 else 0.999
        out.append({"time": t0 + i * 900, "open": p, "high": p * 1.01,
                    "low": p * 0.99, "close": p * 1.002, "volume": 1000 + i})
    return out


class FakeMarket:
    def get(self, symbol, timeframe, limit=500, max_age=None):
        return _bars()[-limit:]


class _Ctl:
    def status(self): return {}
    def journal(self): return []
    def metrics(self): return {}
    def halt(self): pass
    def reset(self): pass
    def pause(self): pass
    def resume(self): pass
    def flatten(self): pass
    def set_mode(self, m): return (True, "")
    def start(self): pass
    def stop(self): pass


def _client():
    app = create_app(_Ctl(), profiles=None, creds=None, token="t",
                     store=None, market=FakeMarket())
    return TestClient(app)


def test_presets_lists_archetypes():
    r = _client().get("/api/presets")
    assert r.status_code == 200
    keys = {p["key"] for p in r.json()}
    assert keys == {"conservative", "balanced", "aggressive", "ai_kronos"}
    assert all("profile" in p for p in r.json())


def test_build_requires_token():
    c = _client()
    body = {"symbol": "TRX/USD", "risk": "balanced", "style": "swing", "ai": False}
    assert c.post("/api/strategy/build", json=body).status_code == 401


def test_build_returns_ranked_results():
    c = _client()
    body = {"symbol": "TRX/USD", "risk": "balanced", "style": "swing", "ai": False}
    r = c.post("/api/strategy/build", json=body, headers={"X-Token": "t"})
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "TRX/USD" and len(data["results"]) >= 1
    assert sum(1 for x in data["results"] if x["recommended"]) <= 1


def test_backtest_single_profile():
    c = _client()
    profile = {"symbol": "TRX/USD", "timeframe": "15m",
               "signals": {"oversold": {"weight": 1.0, "oversold_level": 45, "period": 14}}}
    r = c.post("/api/strategy/backtest", json={"profile": profile}, headers={"X-Token": "t"})
    assert r.status_code == 200
    assert "n_trades" in r.json()["metrics"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_web_strategy.py -q`
Expected: FAIL with 404 on `/api/presets` (route not defined)

- [ ] **Step 3: Add imports near the top of `src/swingbot/web.py`** (after the existing `from swingbot.data.market import timeframe_seconds` line)

```python
from dataclasses import asdict

from swingbot import presets as presets_mod
from swingbot.strategy_search import backtest_profile, search as run_strategy_search
```

- [ ] **Step 4: Add request models** next to the existing `ModeBody` class in `src/swingbot/web.py`

```python
class BuildBody(BaseModel):
    symbol: str
    risk: str = "balanced"
    style: str = "swing"
    ai: bool = False


class BacktestBody(BaseModel):
    profile: dict
```

- [ ] **Step 5: Add the endpoints** inside `create_app`, immediately after the `/api/candles` endpoint block

```python
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
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_web_strategy.py -q`
Expected: PASS (4 passed)

- [ ] **Step 7: Run the full backend suite to confirm no regressions**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all prior tests + the new ones; ~155 passed, 4 skipped)

- [ ] **Step 8: Commit**

```bash
git add src/swingbot/web.py tests/test_web_strategy.py
git commit -m "feat: /api/presets, /api/strategy/build, /api/strategy/backtest endpoints"
```

---

## Task 4: Frontend API methods

**Files:**
- Modify: `frontend/src/api.js`

- [ ] **Step 1: Add three methods** inside the `api` object, after the `candles:` method (before the closing `}`)

```javascript
  presets: () => req('GET', '/api/presets'),
  buildStrategy: (body) => req('POST', '/api/strategy/build', body),
  backtestProfile: (profile) => req('POST', '/api/strategy/backtest', { profile }),
```

- [ ] **Step 2: Verify the bundle still builds**

Run: `cd frontend && npm run build`
Expected: `built in …` with no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.js
git commit -m "feat: frontend api methods for presets/build/backtest"
```

---

## Task 5: Preset gallery component

**Files:**
- Create: `frontend/src/components/PresetGallery.jsx`

- [ ] **Step 1: Write the component**

```jsx
// frontend/src/components/PresetGallery.jsx
import { useEffect, useState } from 'react'
import { api } from '../api.js'
import Hint from './Hint.jsx'

const fmt = (x) => (x == null ? '—' : (+x).toFixed(2))
const pct = (x) => (x == null ? '—' : `${(+x * 100).toFixed(0)}%`)

export default function PresetGallery({ symbol, onUse }) {
  const [presets, setPresets] = useState([])
  const [coin, setCoin] = useState(symbol || 'TRX/USD')
  const [results, setResults] = useState({})
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => { api.presets().then(setPresets).catch(e => setErr(e.message)) }, [])

  const use = (p) => onUse({ ...p.profile, symbol: coin }, p.key)
  const test = async (p) => {
    setBusy(p.key); setErr('')
    try {
      const r = await api.backtestProfile({ ...p.profile, symbol: coin })
      setResults(s => ({ ...s, [p.key]: r.metrics }))
    } catch (e) { setResults(s => ({ ...s, [p.key]: { error: e.message } })) }
    finally { setBusy('') }
  }

  return (
    <div className="panel full">
      <h3>Preset strategies
        <Hint text="Ready-made strategies. Pick a coin, then Use to load one into the form below, or Backtest to see how it would have done on recent data." />
        <input className="coin-pick" value={coin} onChange={e => setCoin(e.target.value)} aria-label="coin" />
      </h3>
      {err && <div className="err">{err}</div>}
      <div className="preset-grid">
        {presets.map(p => (
          <div className="preset-card" key={p.key}>
            <div className="preset-name">{p.name}</div>
            <div className="preset-desc">{p.description}</div>
            <div className="preset-sig">{p.signals.join(' · ')}</div>
            {results[p.key] && (
              <div className="preset-metrics">
                {results[p.key].error
                  ? <span className="err">{results[p.key].error}</span>
                  : <>exp {fmt(results[p.key].expectancy)} · win {pct(results[p.key].win_rate)} · {results[p.key].n_trades} trades</>}
              </div>
            )}
            <div className="preset-actions">
              <button className="act" onClick={() => use(p)}>Use for {coin}</button>
              <button className="act" disabled={busy === p.key} onClick={() => test(p)}>
                {busy === p.key ? '…' : 'Backtest'}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify the bundle builds**

Run: `cd frontend && npm run build`
Expected: builds with no errors (component not yet imported anywhere — that's fine)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/PresetGallery.jsx
git commit -m "feat: preset gallery component"
```

---

## Task 6: Guided builder component

**Files:**
- Create: `frontend/src/components/StrategyBuilder.jsx`

- [ ] **Step 1: Write the component**

```jsx
// frontend/src/components/StrategyBuilder.jsx
import { useState } from 'react'
import { api } from '../api.js'
import Hint from './Hint.jsx'

const RISKS = ['conservative', 'balanced', 'aggressive']
const STYLES = ['scalp', 'swing', 'position']
const fmt = (x) => (x == null ? '—' : (+x).toFixed(2))
const pct = (x) => (x == null ? '—' : `${(+x * 100).toFixed(0)}%`)

export default function StrategyBuilder({ symbol, onUse }) {
  const [coin, setCoin] = useState(symbol || 'TRX/USD')
  const [risk, setRisk] = useState('balanced')
  const [style, setStyle] = useState('swing')
  const [ai, setAi] = useState(false)
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState('')

  const build = async () => {
    setBusy(true); setErr(''); setRes(null)
    try { setRes(await api.buildStrategy({ symbol: coin, risk, style, ai })) }
    catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="panel full">
      <h3>Guided builder
        <Hint text="Pick a coin and your preferences; the server backtests several candidate strategies on recent data and recommends the best. Use a row to load it into the form below." />
      </h3>
      <div className="builder-row">
        <label>Coin<input value={coin} onChange={e => setCoin(e.target.value)} /></label>
        <label>Risk<select value={risk} onChange={e => setRisk(e.target.value)}>
          {RISKS.map(r => <option key={r} value={r}>{r}</option>)}</select></label>
        <label>Style<select value={style} onChange={e => setStyle(e.target.value)}>
          {STYLES.map(s => <option key={s} value={s}>{s}</option>)}</select></label>
        <label className="builder-ai">
          <input type="checkbox" checked={ai} onChange={e => setAi(e.target.checked)} /> Use AI (Kronos)
        </label>
        <button className="act" disabled={busy} onClick={build}>{busy ? 'Searching…' : 'Build & backtest'}</button>
      </div>
      {ai && <p style={{ color: 'var(--muted)', marginTop: 0 }}>AI search is slower — runs fewer candidates.</p>}
      {err && <div className="err">{err}</div>}
      {res && (
        <table>
          <thead><tr><th></th><th>Strategy</th><th>Expectancy</th><th>Win%</th><th>Trades</th><th></th></tr></thead>
          <tbody>
            {res.results.map((r, i) => (
              <tr key={i} className={r.recommended ? 'rec' : ''}>
                <td>{r.recommended ? '★' : ''}</td>
                <td>{r.label}</td>
                <td>{r.error ? <span className="err">{r.error}</span> : fmt(r.metrics.expectancy)}</td>
                <td>{r.error ? '—' : pct(r.metrics.win_rate)}</td>
                <td>{r.error ? '—' : r.metrics.n_trades}</td>
                <td>{!r.error && <button className="act" onClick={() => onUse(r.profile)}>Use this</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify the bundle builds**

Run: `cd frontend && npm run build`
Expected: builds with no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/StrategyBuilder.jsx
git commit -m "feat: guided strategy builder component"
```

---

## Task 7: Wire the 3 tiers into the Strategy page + styles

**Files:**
- Modify: `frontend/src/pages/Strategy.jsx`
- Modify: `frontend/src/theme.css`

- [ ] **Step 1: Add imports** at the top of `frontend/src/pages/Strategy.jsx` (after the existing `import Hint ...` line)

```javascript
import PresetGallery from '../components/PresetGallery.jsx'
import StrategyBuilder from '../components/StrategyBuilder.jsx'
```

- [ ] **Step 2: Add an `applyProfile` handler** inside the `Strategy()` component, right after the `save` function definition

```javascript
  const applyProfile = (profile, name) => {
    setErr('')
    setF(parseProfile(name || f.name || 'built', profile))
    setMsg('loaded into form below — review, name it, then Save')
  }
```

- [ ] **Step 3: Render the two new panels** at the top of the returned `<div className="wrap">`, immediately after the opening tag and before the existing `<div className="panel">` (Profiles)

```jsx
      <PresetGallery symbol={f.symbol} onUse={applyProfile} />
      <StrategyBuilder symbol={f.symbol} onUse={applyProfile} />
```

- [ ] **Step 4: Append styles** to the end of `frontend/src/theme.css`

```css
/* ── Strategy presets + builder ── */
.coin-pick{margin-left:auto;width:130px;text-transform:none;letter-spacing:0;font-size:13px}
.preset-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
.preset-card{background:var(--surface-2);border:1px solid var(--glass-border);border-radius:12px;
  padding:12px 13px;display:flex;flex-direction:column;gap:6px}
.preset-card:hover{border-color:var(--glass-border-strong)}
.preset-name{font-weight:700;color:#fff}
.preset-desc{color:var(--muted);font-size:12px;line-height:1.4;flex:1}
.preset-sig{color:var(--accent);font-size:11px;font-variant-numeric:tabular-nums}
.preset-metrics{font-size:12px;color:var(--text);font-variant-numeric:tabular-nums;
  border-top:1px solid var(--glass-border);padding-top:6px}
.preset-actions{display:flex;gap:6px;margin-top:2px}
.preset-actions .act{margin:0;padding:6px 10px;font-size:12px}
.builder-row{display:flex;flex-wrap:wrap;align-items:flex-end;gap:12px}
.builder-row label{display:flex;flex-direction:column;gap:4px;color:var(--muted);font-size:12px;margin:0}
.builder-row input,.builder-row select{width:150px}
.builder-ai{flex-direction:row !important;align-items:center;gap:8px;color:var(--text);font-size:13px}
.builder-ai input{width:auto}
.builder-row .act{margin:0}
tr.rec{background:rgba(108,123,242,0.12)}
tr.rec td{font-weight:600}
```

- [ ] **Step 5: Build and verify**

Run: `cd frontend && npm run build`
Expected: builds with no errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Strategy.jsx frontend/src/theme.css
git commit -m "feat: wire preset gallery + builder into Strategy page (3 tiers)"
```

---

## Task 8: Deploy + end-to-end verification

**Files:** none (build + verify)

- [ ] **Step 1: Rebuild and redeploy the container**

Run: `docker compose build swingbot && docker compose up -d swingbot`
Expected: image built, container recreated/started

- [ ] **Step 2: Smoke-test the new endpoints**

Run:
```bash
curl -s http://localhost:8000/api/presets | python3 -m json.tool | head -20
```
Expected: a JSON array of 4 archetypes, each with `key`, `name`, `description`, `signals`, `profile`.

- [ ] **Step 3: Verify build requires a token (write protection)**

Run:
```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/strategy/build \
  -H 'Content-Type: application/json' -d '{"symbol":"TRX/USD"}'
```
Expected: `401`

- [ ] **Step 4: Visual check (Playwright)**

Navigate to `http://localhost:8000/`, click the **Strategy** tab, screenshot. Confirm: the Preset gallery cards render, the Guided builder row (Coin/Risk/Style/AI + Build) renders, and the existing detailed form is still below. Confirm no JS console errors other than the known `favicon.ico` 404.

(If credentials are not set, `Build & backtest` and preset `Backtest` will return a 400 "set Alpaca credentials in Settings first" / insufficient-data message — that is expected; the UI surfaces it. Loading a preset/candidate into the form via `Use` works without credentials.)

- [ ] **Step 5: Update the knowledge graph**

Run: `graphify update .`
Expected: graph rebuilt with the new modules.

- [ ] **Step 6: Final commit (if any uncommitted verification artifacts)**

```bash
git add -A
git commit -m "chore: rebuild graph after strategy presets/builder" || echo "nothing to commit"
```

---

## Self-Review

**Spec coverage:**
- §4.1 presets.py (archetypes, risk/style maps, build_candidates) → Task 1 ✓
- §4.2 strategy_search.py (backtest_profile, search, ranking, error capture) → Task 2 ✓
- §4.3 endpoints (/api/presets, /api/strategy/backtest, /api/strategy/build, token, 400 on no creds) → Task 3 ✓
- §5 frontend (api.js, PresetGallery, StrategyBuilder, 3-tier wiring, form prefill via parseProfile) → Tasks 4–7 ✓
- §6 error handling (no creds 400, insufficient data, Kronos failure as error row, per-candidate isolation) → Tasks 2–3 (search captures errors; `_require_market_ready`) ✓
- §7 testing (presets combos, search ranking + error, web endpoints) → Tasks 1–3 ✓
- §8 scope (sync, curated set, templates not seeded) → respected ✓
- §9 future directions → documentation only, no tasks (correct) ✓

**Placeholder scan:** No TBD/TODO; every code step contains complete code; every command has expected output. ✓

**Type consistency:** `build_candidates`→`{label, profile}` consumed identically in Task 2 `search`; `metrics_dict` keys (`expectancy`, `win_rate`, `n_trades`, …) match frontend reads (`r.metrics.expectancy`, `.win_rate`, `.n_trades`) in Tasks 5–6; `archetype_profile(arch, symbol, style)` signature matches the `/api/presets` call in Task 3; `applyProfile(profile, name)` matches `onUse` usage (gallery passes `(profile, key)`, builder passes `(profile)`) in Tasks 5–7; `parseProfile(name, p)` already exists in Strategy.jsx. ✓

**Note for implementer:** `metrics_dict`/the backtest endpoint use `getattr(m, …, None)`, so unknown `Metrics` field names degrade to `null` (rendered as `—`) rather than erroring — no need to look up the exact `Metrics` dataclass fields, but `expectancy`, `win_rate`, `n_trades` are known to exist (used elsewhere in the codebase).
