# Kronos POC Paper Trader — Design Decisions Brief

> **Purpose:** This is the *resolved input* to the spec. A fresh session should load
> `superpowers:brainstorming` → `superpowers:writing-plans` and write the full design doc to
> `docs/superpowers/specs/2026-06-20-kronos-poc-paper-trader-design.md` **from these decisions** —
> do NOT re-ask the user the forks below; they are settled. Confirm understanding, write the spec,
> self-review, ask the user to review the written spec, then proceed to the implementation plan.

**Date settled:** 2026-06-20. **Brainstorm completed with the user this session** (4 forks resolved
via AskUserQuestion + 1 free-text answer that reframed the product).

---

## Guiding principle (overrides ambiguity)

**"It does what I don't need to know how to do."** The user is *not* a quant and does **not** want to
configure numbers — no thresholds, no TP/SL, no rebalance weights, ever. Every number is owned by the
system: sane defaults at start, then deterministic rules + the LLM advisor manage them. The user's
entire interaction is: press **Start**, watch equity + plain-English notes. Design every UI/UX choice
to that principle. When in doubt, hide the number and let the system own it.

---

## Resolved forks

1. **Data source — "Both, selectable."** Decouple candle data from the broker. A `data_source`
   setting selects the live feed: **Coinbase (default)**, Kraken, or Alpaca — via the existing
   `swingbot/data/ccxt_provider.py::CcxtProvider` (no API key needed for public OHLCV). `MarketData`
   (`swingbot/data/market.py`) currently hard-wires Alpaca in `_provider()`; make it return the
   configured provider. **Charts + Kronos must populate with NO broker connected.** Alpaca paper is
   used **only** to place orders. This is the real fix for the "no fresh closed bar available" the
   user screenshotted (root cause was candles welded to the 401'd Alpaca key — see supervisor.py:636).

2. **Scope — "Middle ground."** Single Kronos-bracket strategy is the only strategy. **KEEP** the
   portfolio **rebalance layer** (`swingbot/rebalance`). **DELETE:** auto-discovery / "eligible now"
   (`strategy_search` + Discover UI), the old per-signal strategy editor, managed strategies
   (`btc_trend`/`eth_trend` + reconciler), `paper_probe` (+ ProbeMarkerStore), and the old per-trade
   Ollama **brain** (`decision/` package + Brain page). **KEEP:** Kronos signal/adapter, EMA
   indicator (still used by the autodash EMA-vs-Kronos backtest), rebalance layer, the supervisor
   autonomous loop, the broker connection manager.

3. **Trading profile default — "Balanced 15m."** Per closed **15m** bar, per armed coin:
   - **Flat →** run Kronos forecast; if predicted move over the next ~1h (`pred_len`≈4 bars) is
     **≥ +0.75%** above current close → **market BUY**. Size from the rebalance allocation (equal-weight
     default); if rebalance off, equal-split fraction.
   - On entry, save `entry`, `tp = entry × 1.015` (**+1.5%**), `sl = entry × 0.99` (**−1.0%**) onto the
     position (extend OpenPosition / PositionStore).
   - **In position →** each loop cycle compare **latest price** to saved levels: `price ≥ tp` → market
     SELL; `price ≤ sl` → market SELL. **Kronos is NOT consulted to exit** — pure software bracket
     ("sell when price reads a saved price"). One position per coin; SELL only ever closes.
   - **Kronos fails / unavailable → HOLD** (stay flat). Never fall back to another signal silently;
     surface a clear "Kronos unavailable" status.
   - These numbers are **defaults**, auto-managed thereafter — **not** user-edited fields.

4. **Self-management — "LLM advisor, bounded auto-apply"** (chosen) on top of the deterministic
   foundation. Two layers:
   - **Deterministic foundation (always on):** auto-rebalance on interval/drift in **hard** mode
     (the rebalance layer already trims/reallocates by itself); drawdown / daily-loss **circuit
     breakers** (`RiskManager` already exists) that auto-halt or scale down. This alone delivers
     hands-off; the LLM is additive.
   - **LLM advisor (bounded auto-apply):** see job outline below.

---

## LLM advisor — job outline & contract

- **Model:** a tiny **quantized** local model — target `gemma-4-e2b-it-qat-q4` (the QAT-Q4 build
  already in `~/models`, llama.cpp/LocalAI gallery) or a small Llama via llama.cpp/Ollama. Must
  **co-load with Kronos on a 4 GB GPU** (the user named a Quadro **M2000** as the hardware *floor*;
  design to it). **Loaded on demand** for a review pass and unloaded after — never resident, never
  fights Kronos for VRAM; on a tight card it may run on **CPU** (it's off the hot path, infrequent).
- **When:** on a schedule (e.g. every few hours and/or after N closed trades). **Never per-bar.**
- **Input:** a compact performance digest — per coin: trades, win rate, avg win/loss, current
  drawdown, current params (threshold/TP/SL), current allocation weight, recent equity curve.
- **Job / output:** a **strict JSON** proposal that nudges, per coin, entry threshold / TP / SL /
  allocation weight / enable-disable — **each clamped to hard safe bands** — plus a one-line
  plain-English rationale per change. Validate against a schema; out-of-band or unparseable values are
  clamped or dropped + logged.
- **Apply — bounded auto-apply:** valid in-range changes apply **automatically**, each logged to a
  **tuning journal** (before/after + rationale), **one-click reversible** (revert one / revert all).
- **Hard boundary:** the advisor **never** sees or makes a per-bar buy/sell/stop decision. Those stay
  100% Kronos forecast + the deterministic bracket + the risk circuit breakers. The advisor only tunes
  *configuration*, never executes trades.
- **Relation to the deleted brain:** this is a NEW, narrow *operational tuner* — NOT the old per-trade
  decision brain (which stays deleted). Reuse the old `decision/` Ollama-client plumbing only if it's
  clean; otherwise build fresh.

---

## UI (consequences of the guiding principle)

- **No numeric config fields anywhere.** Defaults ship as the Balanced profile.
- The **only** optional high-level control is a single **risk dial: Cautious / Balanced / Aggressive**,
  which just sets the **guardrail bands** the advisor operates within. Defaults to Balanced; user can
  ignore it.
- **Rebalance weights auto-derive** (equal-weight across active coins to start; advisor tunes). User
  never sets a weight.
- **Settings** shrinks to: Broker connection (existing) · **Data source dropdown** · risk dial ·
  Rebalance panel (kept, but no manual weight entry required).
- **Mission Control:** total equity, today's P&L, per-coin state (flat / in-position with
  entry·TP·SL), live price from the data feed, a feed of the advisor's **plain-English notes**, and
  Start/Stop. Nothing to configure.

---

## Compute / infra

- **Enable the nvidia Docker runtime** for the host **RTX 3050** (replace the untracked
  `docker-compose.override.yml` `runtime: runc` with `runtime: nvidia` / device reservations) so
  Kronos-small runs sub-second. Dockerfile already clones Kronos to `/kronos` (PYTHONPATH set).
- **Design to the 4 GB M2000 floor:** Kronos-small (~25M params, tiny) + a Q4 2B-class advisor loaded
  only during a review pass fits in 4 GB. Runs on the M2000 floor *and* the 3050.

---

## Known risk (carry into spec "Risks" section)

Alpaca **paper** crypto **BUY** orders have a documented broker-side bug: they stall in `pending_new`
for hours (the user's own memory `alpaca-paper-crypto-buy-fill-bug` notes this; SELLs fill instantly).
The bot handles it truthfully (no fabricated fill), but a live "buy low" entry may sit unfilled on
Alpaca paper. The Coinbase/Kraken data feed + the prediction/decision logic are unaffected and fully
demoable — only the Alpaca *fill* is at the mercy of that bug.

---

## Testing / gate (carry into spec)

- Unit-test `KronosBracketStrategy.decide()` with a fake forecaster: buy-trigger, TP-hit, SL-hit,
  hold, Kronos-fail-hold.
- Provider-selection test (data_source → correct provider; Coinbase works with no creds).
- Advisor: JSON-schema validation + out-of-band clamp/reject tests; tuning-journal + revert tests.
- Keep the full gate green: `.venv/bin/python -m pytest -q`, `ruff check src/`, `cd frontend && npm run build`.
- Standing rule: every code change → `docker compose build swingbot && docker compose up -d swingbot`.

---

## Target spec path

`docs/superpowers/specs/2026-06-20-kronos-poc-paper-trader-design.md`
