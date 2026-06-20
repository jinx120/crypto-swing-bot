# Kronos POC Paper Trader — Design Specification

**Date:** 2026-06-20
**Status:** Draft for user review
**Resolved input:** `docs/superpowers/specs/2026-06-20-kronos-poc-paper-trader-DECISIONS.md`
(all design forks settled with the user 2026-06-20 — this spec realizes those decisions; it does not
re-open them).

---

## 1. Overview

A hands-off, autonomous **paper** trader built to one principle:

> **"It does what I don't need to know how to do."**

The user is not a quant and never configures a number. The system owns every parameter — entry
threshold, take-profit, stop-loss, allocation weights — starting from sane defaults, then keeping them
in line via deterministic rules plus an occasional local-LLM advisor. The user's entire interaction is:
**press Start, watch equity and plain-English notes.**

The product is a single strategy — **predict up → buy → bracket out** — wrapped in a self-managing
operational layer. It is a proof of concept: the prediction/decision pipeline must be fully demoable on
free public market data with **no broker connected**.

### What changes vs. today
1. **Data is decoupled from the broker.** Charts and Kronos populate from a selectable public feed
   (Coinbase default), so the dashboard works with no Alpaca key. Alpaca paper is used *only* to place
   orders. This is the real fix for the screenshotted "no fresh closed bar available" failure.
2. **One strategy replaces many.** A single `KronosBracketStrategy` is the only signal source.
   Auto-discovery, the old per-signal strategy editor, managed strategies + reconciler, `paper_probe`,
   and the old per-trade Ollama "brain" are deleted.
3. **The system self-manages.** A deterministic foundation (auto-rebalance + circuit breakers) plus a
   bounded LLM **advisor** that tunes configuration — never trades — keep it hands-off.

---

## 2. Architecture layers

```
            ┌──────────────────────────────────────────────────────┐
   UI       │ Mission Control · Coin Detail · Settings (shrunk)     │
            └───────────────▲──────────────────────▲────────────────┘
                            │ /api                  │ /api
            ┌───────────────┴──────────────────────┴────────────────┐
 Decision   │ Supervisor autonomous loop (15m closed-bar cadence)    │
   core     │   per armed coin:  KronosBracketStrategy.decide()      │
            │   ├─ flat: Kronos forecast → BUY if pred ≥ +0.75%      │
            │   └─ in-position: price vs saved TP/SL → SELL          │
            └───────▲──────────────▲───────────────▲────────────────┘
                    │              │               │
        ┌───────────┴───┐  ┌───────┴──────┐  ┌─────┴───────────────┐
 Self-  │ Rebalance     │  │ RiskManager  │  │ LLM Advisor         │
 mgmt   │ (hard, auto)  │  │ circuit-brk  │  │ (bounded auto-apply,│
        │               │  │              │  │  config tuning only)│
        └───────────────┘  └──────────────┘  └─────────────────────┘
                    ▲                                   │
        ┌───────────┴────────────┐          ┌───────────┴──────────┐
 Data   │ MarketData → data_source│          │ Broker (Alpaca paper)│
 / I/O  │  CcxtProvider (Coinbase │          │  ORDERS ONLY         │
        │  /Kraken/Alpaca public) │          └──────────────────────┘
        └─────────────────────────┘
```

Each box is an independently testable unit with a narrow interface. The decision core depends on the
data layer (read) and the broker (write orders); the self-management layer reads telemetry and writes
*configuration*, never orders.

---

## 3. Data layer — decouple feed from broker

**Problem (current):** `MarketData._provider()` (`src/swingbot/data/market.py:74`) returns
`self.creds.make_data()` — i.e. it is welded to broker credentials. With no Alpaca creds (or a 401'd
key) it returns `None`, so no candles are fetched and the loop reports `"no fresh closed bar available"`
(`supervisor.py:636`).

**Design:**
- Introduce a persisted **`data_source`** setting: `coinbase` (default), `kraken`, or `alpaca`.
- `MarketData` gains a provider factory keyed on `data_source` instead of on broker creds:
  - `coinbase` / `kraken` → `CcxtProvider` (`src/swingbot/data/ccxt_provider.py`) — **public OHLCV, no
    API key required**.
  - `alpaca` → existing Alpaca data provider via creds (only valid when a key is present).
- The supervisor/webmain wires `MarketData` from the `data_source` setting, **not** from broker creds.
  Broker creds remain required only for order placement.
- Symbol mapping: keep USD quote pairs (e.g. `BTC/USD`) — CcxtProvider already maps per exchange;
  Coinbase/Kraken serve `BTC/USD`-style pairs. (Memory: Alpaca paper is USD-funded; never `USDT`.)

**Result:** charts + Kronos populate with **no broker connected**. The "buy low / sell high" pipeline is
fully demoable on Coinbase data alone.

---

## 4. Trading logic — `KronosBracketStrategy`

One strategy, one position per coin, **15m closed-bar** cadence. `decide(ctx)` returns a decision the
supervisor executes; it is the only signal source.

**Flat → maybe enter:**
1. Run `KronosAdapter.forecast(candles)` (`src/swingbot/signals/kronos_adapter.py:106`, returns a
   forecast frame or `None`).
2. Compute predicted move over the next ~1h (`pred_len ≈ 4` bars) vs. current close.
3. If predicted move **≥ +0.75%** → **market BUY**. Size from the rebalance allocation (equal-weight
   default); if rebalance is off, an equal-split fraction of equity across armed coins.
4. On a confirmed entry, persist the bracket onto the position: `entry_price`, `tp = entry × 1.015`
   (**+1.5%**), `stop = entry × 0.99` (**−1.0%**). **These fields already exist on `OpenPosition`**
   (`src/swingbot/types.py:162` has `entry_price`, `tp`, `stop`) — populate them from the bracket; no
   schema change needed beyond ensuring they are written/read on the Kronos path.

**In position → maybe exit (pure software bracket):**
- Each cycle, compare **latest price** to the saved levels:
  - `price ≥ tp` → **market SELL** (close).
  - `price ≤ stop` → **market SELL** (close).
- **Kronos is NOT consulted to exit.** Exits are "sell when price reads a saved price" — deterministic.
- SELL only ever closes a position; one position per coin.

**Kronos unavailable → HOLD.** If `forecast()` returns `None` (model load fail, timeout, no GPU path),
**stay flat** — never silently fall back to another signal. Surface a clear **"Kronos unavailable"**
status in the UI and decision journal.

**Defaults, not fields:** +0.75% / +1.5% / −1.0% ship as the **Balanced** profile and are auto-managed
thereafter (see §6). They are never user-edited inputs.

---

## 5. Deterministic self-management foundation (always on)

This layer alone delivers hands-off; the LLM (§6) is additive.

- **Auto-rebalance:** keep the existing portfolio rebalance layer (`src/swingbot/rebalance.py`), run in
  **hard** mode on interval/drift. It trims/reallocates by itself, respecting the existing volatility,
  correlation, and fee guards. Weights **auto-derive** (equal-weight across active coins to start).
- **Circuit breakers:** the existing `RiskManager` (`src/swingbot/risk.py`) enforces drawdown /
  daily-loss limits — auto-halt or scale down when breached. No user action required.

---

## 6. LLM advisor — bounded auto-apply (config tuning only)

A NEW, narrow **operational tuner** — explicitly *not* the deleted per-trade brain.

- **Model:** a tiny **quantized** local model — target `gemma-4-e2b-it-qat-q4` (QAT-Q4 build in
  `~/models`) or a small Llama via llama.cpp/Ollama. **Loaded on demand** for a review pass and unloaded
  after — never resident, never competes with Kronos for VRAM. On a tight card it may run on **CPU**
  (it is off the hot path and infrequent).
- **When:** on a schedule (every few hours and/or after N closed trades). **Never per-bar.**
- **Input:** a compact performance digest — per coin: trades, win rate, avg win/loss, current drawdown,
  current params (threshold/TP/SL), current allocation weight, recent equity curve.
- **Output:** a **strict JSON** proposal that nudges, per coin: entry threshold / TP / SL / allocation
  weight / enable-disable — **each clamped to hard safe bands** — plus a one-line plain-English
  rationale per change. Validate against a schema; out-of-band or unparseable values are **clamped or
  dropped, and logged**.
- **Apply (bounded auto-apply):** valid in-range changes apply **automatically**, each written to a
  **tuning journal** (before/after + rationale) and **one-click reversible** (revert one / revert all).
- **Hard boundary:** the advisor **never** sees or makes a per-bar buy/sell/stop decision. Those stay
  100% Kronos forecast + the deterministic bracket + the risk circuit breakers. The advisor only tunes
  *configuration*.
- **Guardrail bands** are set by the single risk dial (§7): Cautious / Balanced / Aggressive widen or
  narrow the bands the advisor may move within.
- **Reuse:** reuse the deleted brain's Ollama-client plumbing only if it is clean; otherwise build
  fresh under a new module (e.g. `swingbot/advisor/`).

---

## 7. UI / UX (consequence of the guiding principle)

**No numeric config fields anywhere.** Defaults ship as the Balanced profile.

- **Mission Control (`#/`):** total equity, today's P&L, per-coin state (flat / in-position with
  entry · TP · SL shown read-only), live price from the data feed, a feed of the advisor's
  **plain-English notes**, and **Start/Stop**. Nothing to configure.
- **Coin Detail (`#/coin/:name`):** chart (from the data feed), position with bracket levels, live
  stats, recent trades, decision journal (incl. "Kronos unavailable" when degraded). The existing
  EMA-vs-Kronos backtest panel is retained (it is why the `ema_trend` indicator stays).
- **Settings (`#/settings`) shrinks to:** Broker connection (existing) · **Data source dropdown**
  (Coinbase/Kraken/Alpaca) · **risk dial** (Cautious / Balanced / Aggressive, defaults Balanced, can be
  ignored) · Rebalance panel (kept, but **no manual weight entry**). The **advisor tuning journal**
  (with revert) lives here or on Mission Control as a notes feed.

---

## 8. Removals (delete outright — do not port)

Per the standing "remove obsolete subsystems entirely" rule:

- **Auto-discovery / "eligible now":** `src/swingbot/strategy_search.py` + the Discover UI + its API.
- **Old per-signal strategy editor / managed strategies + reconciler** (`btc_trend`/`eth_trend` seeding).
- **`paper_probe`:** `src/swingbot/signals/paper_probe.py` + `ProbeMarkerStore` + probe wiring.
- **Old per-trade Ollama brain:** `src/swingbot/decision/` package + the Brain page + its API.
- Any orphaned routes/endpoints/tests for the above.

**KEEP:** `signals/kronos_adapter.py`, `signals/kronos_forecast.py`, `signals/ema_trend.py` (backtest),
`rebalance.py`, `risk.py`, the supervisor autonomous loop, and the broker connection manager.

---

## 9. Compute / infra

- **Enable the nvidia Docker runtime** for the host **RTX 3050**: replace the untracked
  `docker-compose.override.yml` `runtime: runc` with `runtime: nvidia` / device reservations so
  Kronos-small runs sub-second. (Dockerfile already clones Kronos to `/kronos`, PYTHONPATH set.)
- **Design to the 4 GB M2000 floor:** Kronos-small (~25M params) + a Q4 2B-class advisor loaded only
  during a review pass fits in 4 GB. Runs on the M2000 floor *and* the 3050.
- Standing rule: every code change → `docker compose build swingbot && docker compose up -d swingbot`.

---

## 10. Risks

- **Alpaca paper crypto BUY fill bug (known, broker-side):** paper BUYs can stall in `pending_new` for
  hours; SELLs fill instantly (memory `alpaca-paper-crypto-buy-fill-bug`). The bot already handles this
  truthfully (no fabricated fill). The Coinbase/Kraken feed + the prediction/decision logic are
  unaffected and fully demoable — only the Alpaca *fill* is at the mercy of this bug.
- **GPU/runtime:** if the nvidia runtime is not enabled, Kronos has no GPU path → forecast may be slow
  or unavailable → the strategy HOLDs (truthfully surfaced), it does not trade on a degraded model.
- **Advisor drift:** mitigated by hard clamp bands + tuning journal + one-click revert; the advisor can
  never move a parameter outside its risk-dial band and never places a trade.

---

## 11. Testing / gate

- `KronosBracketStrategy.decide()` with a fake forecaster: buy-trigger (≥ +0.75%), TP-hit, SL-hit,
  hold (< threshold), and **Kronos-fail → HOLD**.
- **Provider selection:** `data_source` → correct provider; Coinbase works with **no creds**; charts
  populate with no broker.
- **Advisor:** JSON-schema validation; out-of-band clamp/reject; tuning-journal write + revert
  (one / all).
- **Rebalance/risk:** existing coverage stays green; equal-weight auto-derive verified.
- **Full gate green:** `.venv/bin/python -m pytest -q`, `ruff check src/`, `cd frontend && npm run
  build`; then `docker compose build swingbot && docker compose up -d swingbot` + a live smoke that the
  dashboard charts populate from Coinbase with no broker connected.

---

## 12. Out of scope (this POC)

- Live (real-money) trading.
- Multiple concurrent strategies or user-authored strategies.
- Any user-facing numeric parameter entry.
- Advisor making per-bar trade decisions.
