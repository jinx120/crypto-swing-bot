# Tunable Gates, Researched Strategies, Live Data & Faster UI — Design

**Date:** 2026-06-24
**Status:** Approved (design); ready for implementation plan.

## Problem

The live bot is a clean Kronos-only paper trader (4 coins: BTC/ETH/SOL/XRP). It is
**healthy and evaluating every 15m bar**, but it has taken **no trades** because every
decision dies at `REGIME_BLOCKED` — the 4h 200-SMA trend filter classifies all four coins
as DOWNTREND and `allowed_regimes=(UPTREND, NEUTRAL)` vetoes the entry, even though the
Kronos forecast score passes its threshold (e.g. XRP 1.0, SOL 0.82, BTC 0.75 vs 0.05).

None of the entry **gates** (regime, score-threshold, per-signal) are visible or adjustable
from the UI. There is no way to tune strategy parameters without editing code + reseeding the
DB + rebuilding the container. The page shows a ~10s blank on reload, and market data only
refreshes every 10–30s.

## Goals

1. Make every entry **gate** visible and toggleable per coin, and explain/expose the regime gate.
2. Make strategy **parameters tunable live** from the UI (write ProfileStore → hot-reload, **no
   container rebuild** for param changes).
3. Re-introduce the researched TA signals **two ways** ("Both"): (a) as toggleable gates/
   contributors on existing strategies, and (b) as **standalone strategies** you can arm — clearly
   labelled negative-edge/demo per our own backtest.
4. Make market data feel **live** via a dedicated cheap last-price feed (~3s).
5. Kill the **slow initial load** (cached state + skeletons + non-blocking panels).

## Non-goals

- No claim that the researched standalone strategies are profitable — the backtest says they
  aren't at 15m. They ship behind a "demo / backtested negative-edge" badge.
- No new strategy *engine* — gates reuse the existing `ConfluenceEngine` + orchestrator pipeline.
- No streaming/websockets for live price — short-interval polling of a cached REST last-trade.
- No change to candle ingest cadence (still once per closed bar) — that's where 429s bite.

---

## Component 1 — Live profile tuning (backend)

**New endpoint:** `PUT /api/strategies/{name}/profile`

- Body: a partial patch of profile fields (any subset of the `StrategyProfile` dataclass).
- Handler: `cur = profiles.get(name)`; reject 404 if missing; `merged = {**cur, **patch}`;
  validate via `StrategyProfile.from_dict(merged)` (raises → 400 with reason); `profiles.save(name, merged)`;
  `controller.reload()`; return the saved profile. Mirrors the existing
  `PUT /api/portfolio/settings` / `set_rebalance_settings` → `controller.reload()` pattern.
- **Whitelist** the patchable keys server-side (no arbitrary keys): `entry_threshold`,
  `allowed_regimes`, `regime_ma_period`, `signals`, `stop_atr_mult`, `take_profit_atr_mult`,
  `tp_pct`, `sl_pct`, `bracket_mode`, `max_hold_bars`, `risk_per_trade`, `max_position_frac`,
  `daily_loss_limit_pct`, `max_consecutive_losses`, `max_concurrent`, `cooldown_minutes`.
- This is the **only** mechanism needed for tuning AND for the regime toggle (regime off =
  `allowed_regimes` includes all three).

**Regime toggle semantics.** "Regime gate OFF" = `allowed_regimes = ["uptrend","neutral","downtrend"]`
(permits any regime). "ON" = the default `["uptrend","neutral"]`. The frontend renders this as a single
switch; the value stored is the regime tuple. No new field required.

## Component 2 — Gate layer (toggleable per-signal vetoes)

Today signals are **soft**: `ConfluenceEngine` sums `score * weight` per signal and compares to
`entry_threshold`. We add an **optional hard-gate** behavior per signal without disturbing the soft path.

**Config shape.** Each entry in `profile.signals[name]` may carry two reserved keys in addition to
the signal's constructor kwargs:
- `gate: bool` (default false) — if true, this signal acts as a hard veto.
- `min_score: float` (default 0.0) — the raw signal score it must meet/exceed to permit entry.

**Critical:** `build_signals` does `cls(**params)`, and signal constructors do **not** accept `gate`/
`min_score`. So `build_signals` MUST strip the reserved keys before constructing:
```python
RESERVED = {"gate", "min_score"}
cls(**{k: v for k, v in params.items() if k not in RESERVED})
```
The reserved keys are read from the profile (not the signal instance) when evaluating gates.

**Evaluation.** In the orchestrator entry path, after the existing regime check and **before** the
confluence-threshold check, evaluate gates: for each signal with `gate=true`, if its raw
`SignalResult.score < min_score`, return `DecisionResult(DecisionCode.GATE_BLOCKED, "<signal> gate not
satisfied", {"signal": name, "score": s, "min_score": m})`. The raw per-signal scores already exist on
`ConfluenceResult.signals[name].score` (computed each cycle), so no extra computation.

**New decision code:** `DecisionCode.GATE_BLOCKED` (additive; update the decision-code contract test).

This lets a user, e.g., add `ema_trend` as a gate on `kronos-btc-usd` so Kronos entries only fire when
EMA trend also agrees — the "confirmation gate" use case — with `gate` toggled from the UI.

## Component 3 — Researched strategies ("Both")

**(a) As gates/contributors.** All six signals (`oversold`, `vwap`, `relative_strength`, `fvg`,
`kronos_forecast`, `ema_trend`) are already in the confluence `_REGISTRY`. The tuning UI can add any of
them to any profile's `signals` map with a `weight` (soft contributor) and/or `gate`/`min_score`
(hard gate). No new signal code.

**(b) As standalone strategies.** Add preset builders to the existing `swingbot/presets.py` (alongside
`kronos_bracket_profile`) for the researched profiles, returning the same profile dict shape:
- `vwap_pullback_profile(symbol)` — `vwap`+`oversold`+`ema_trend`, ATR brackets 1.2/2.0.
- `ema_trend_profile(symbol)` — `ema_trend`, ATR brackets 1.5/3.0.
- `fvg_retrace_profile(symbol)` — `fvg`+`ema_trend`.
- `eth_rel_strength_profile(symbol)` — `relative_strength`+`ema_trend`+`vwap`, benchmark BTC/USD.

Each preset sets `kind="researched"` and a `label`. `/api/strategies` already surfaces `kind`/`label`
per strategy (added in Phase 5), so the frontend reuses that — no new meta plumbing. Arming reuses the
existing `profiles.save` + `arm` + `controller.reload()` path. The frontend Add-strategy dialog lists
these with a **⚠️ "backtested negative-edge — demo only"** badge.

## Component 4 — Frontend: Gates & Parameters panel

On **Coin Detail** (`#/coin/:name`), add a "Gates & Parameters" panel (collapsible). It reads the full
profile from a new `GET /api/strategies/{name}/profile` (the `/api/state` snapshot only carries the
live `signals`/`threshold`, not the editable fields like brackets/sizing/breakers).

- **Toggles:** Regime gate (on/off), and one toggle per signal currently in the profile (gate on/off).
- **Sliders/inputs:** `entry_threshold`, per-signal `weight`/`min_score`, TP/SL (atr mult or pct per
  `bracket_mode`), `max_hold_bars`, `risk_per_trade`, `max_position_frac`, breakers.
- **Add-signal** control: pick from the six registry signals to add as a contributor/gate.
- **Save** → `PUT /api/strategies/{name}/profile` → optimistic update + refetch. A small "saved, live —
  no rebuild" confirmation. Each control shows its current live value.

On **Mission Control**, the Add-coin / Add-strategy dialog gains the researched-preset option (badged).

Reuse existing shadcn-style primitives (Radix Dialog/Switch) and the `usePolling`/`api.js` patterns.

## Component 5 — Live-price feed

**New endpoint:** `GET /api/price?symbols=BTC/USD,ETH/USD,…` → `{ "BTC/USD": {"price": 60810.2, "ts":
"…"}, … }`.

- Backend wraps the existing `MarketProvider.get_latest_prices(symbols)` (ccxt `fetch_ticker["last"]`,
  **1 REST call per symbol**) behind a **2s TTL cache** keyed by symbol (so multiple clients / a 3s poll
  collapse to ≤1 upstream call per symbol per ~2s). On upstream error, serve last cached value + a stale
  flag; never 500.
- **Rate-limit math:** 4 coins × 1 call / 2s = ~2 calls/s against Coinbase, whose public REST allows
  ~10 req/s. Well within budget, and independent of the per-bar candle ingest (where 429s actually occur).
  Answers the user's question: more-frequent live price is **not** too many API calls done this way.
- **Frontend:** a `useLivePrice` poller at **3s** feeds CoinCard prices + the detail header. Candle/chart
  refresh cadence is unchanged.

## Component 6 — Faster initial load

Root cause: Mission Control / Coin Detail render nothing until the first `/api/state` fetch returns, with
no skeleton and no cached state; heavier panels (chart, backtest) block perceived load.

- **Cache last good `/api/state`** in `localStorage`; hydrate state from it on mount so the page paints
  instantly, then revalidate (stale-while-revalidate). Add the same SWR behavior to `usePolling`
  (return last data while refetching; expose `loading` only when there is no cached data).
- **Skeletons:** status strip, coin cards, and journal render skeleton placeholders when no data yet.
- **Non-blocking panels:** the chart and EMA-vs-Kronos backtest panels render their shell immediately and
  fill asynchronously; they never gate the rest of the page.

---

## Decision pipeline (final order)

`BROKER_POSITION_EXISTS → PAUSED/HALTED → RISK_BLOCKED → REGIME_BLOCKED → **GATE_BLOCKED (new)** →
SIGNAL_BELOW_THRESHOLD → ATR_INVALID → SIZE_ZERO → PORTFOLIO_BLOCKED → ORDER_SUBMITTED`.

## Immediate action (this session)

Per user: explain the regime gate (done in the panel + spec) and **flip it off now** so the bot trades.
Implementation: `PUT /api/strategies/{name}/profile` with `allowed_regimes=["uptrend","neutral","downtrend"]`
for the 4 armed kronos strategies once the endpoint ships (or a one-off ProfileStore reseed + restart if we
unblock before the endpoint lands). Expect a BUY within 1–2 bars (scores already pass).

## Success criteria (verifiable)

1. Regime gate off (live) → a non-IDLE `ORDER_SUBMITTED`/`ENTERED` appears in `/api/decisions` within 1–2 bars.
2. `PUT /api/strategies/{name}/profile` changes a param → reflected in `/api/state` snapshot **without a
   container rebuild** (test + live curl).
3. A `gate=true` signal whose raw score `< min_score` → `GATE_BLOCKED` in the feed (unit test).
4. `GET /api/price` returns cached last-trade for N coins with ≤1 upstream call/symbol per ~2s; sub-second
   response (curl latency + cache test).
5. Mission Control paints cached content immediately on reload — no 10s blank (localStorage hydration +
   skeleton; Playwright check).
6. Gate green: `.venv/bin/python -m pytest -q`, `.venv/bin/ruff check src/`, `cd frontend && npm run build`,
   `npm run test`.

## Testing

- Backend unit: profile-patch endpoint (merge/validate/reload/404/whitelist); `build_signals` strips
  reserved keys; orchestrator `GATE_BLOCKED` path; decision-code contract incl. new code; price endpoint
  cache + stale fallback; researched preset builders produce valid profiles.
- Frontend: `usePolling` SWR (returns cached while refetching); `derive`/live-price helpers; vitest green.
- Live verify (per standing Docker rebuild rule): tuning round-trips without rebuild; regime-off → trade;
  live price updates ~3s; reload paints instantly.

## Sequencing (for the plan)

1. **Tuning backend + regime unblock** — `PUT /api/strategies/{name}/profile`, whitelist, reload; flip
   regime off live. (Delivers the unblock + criterion 1–2.)
2. **Gate layer** — reserved-key strip, `GATE_BLOCKED`, orchestrator wiring, contract test. (Criterion 3.)
3. **Frontend Gates & Parameters panel** + researched-preset Add dialog (badged). (Component 3b + 4.)
4. **Live-price feed** — endpoint + cache + `useLivePrice`. (Criterion 4.)
5. **Faster load** — SWR `usePolling` + localStorage hydration + skeletons + non-blocking panels. (Criterion 5.)

Each step is independently shippable/live-verifiable; the bot keeps trading throughout.
