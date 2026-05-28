# Crypto Swing-Trading Bot — Design Spec

**Date:** 2026-05-28
**Status:** Approved (design phase). No code yet — this document is the handoff for implementation planning.
**Author context:** Personal, experimental project. Not production. Solo developer, limited live-trading experience (mostly manual TradingView + Pine Script, light paper trading, basic TP/SL usage).

---

## 1. Purpose & Scope

Automate the kind of short-hold, buy-low / sell-higher swing trades the author currently does manually. The system watches a market, decides when conditions line up for an entry, opens a position with a protective stop and a profit target, and manages the exit — all without a human clicking buttons.

**In scope (v1):**
- Long-only spot trading on Alpaca crypto.
- One focused instrument to start (TRX/USD if Alpaca supports it; otherwise a similar high-volatility, low-price coin on Alpaca).
- Entry decision from a configurable blend of signals: Fair Value Gap (FVG), an oversold indicator, VWAP, and **Relative Strength** (vs BTC / total crypto market) — combined by a confluence score, then **gated by a trend-regime filter**.
- Hard stop-loss + take-profit + max-hold time on every trade.
- Fixed-fractional-risk position sizing.
- Account-level safety circuit breakers.
- Three run modes — backtest, paper, live — sharing one strategy engine.
- A config-gated graduation path from idea → paper → real money.
- A **Valhalla-styled React monitoring dashboard** (with a full control surface) over a FastAPI/websocket layer — see §11.

**Explicitly out of scope (v1), but the architecture leaves seams for them:**
- Shorting (Alpaca crypto cannot short — see §3).
- Leverage / margin / futures / perps.
- High-frequency trading (seconds of latency is acceptable).
- Long-term holding (holds are minutes to ~a day).
- Reinforcement-learning position sizing (future).
- LLM-based signal interpretation (future).
- Multi-asset portfolios and stocks (future — the broker/data abstraction makes this mostly a config swap; VWAP becomes session-anchored for stocks).

---

## 2. Guiding Principles

1. **Simple and understandable beats clever and sophisticated.** Every component should be explainable in a sentence.
2. **The broker is the source of truth for positions.** The bot persists its own state but always reconciles against the broker on startup.
3. **Never trade on bad data.** Stale or missing candles → skip the tick, don't guess.
4. **The same strategy code runs in backtest, paper, and live.** Only the data source and broker change underneath. This is what makes verification trustworthy.
5. **Risk control is not optional.** Every position has a hard stop and a time cap, no exceptions.

---

## 3. Key Constraint Decisions & Reasoning

### 3.1 Direction & venue — Long-only on Alpaca, broker abstracted
**Decision:** Build long-only on Alpaca now. Put order execution behind a clean broker interface so a shorting-capable venue can be swapped in later without touching strategy code.

**Why:** Alpaca crypto is **spot-only** — no margin, no leverage, no short selling. "Take short positions" is simply not possible there; it would require a different venue (a perps/futures exchange such as Binance/Bybit/Kraken Futures), which contradicts the stated goal of using Alpaca. Abstracting the broker keeps v1 simple while leaving the door open.

### 3.2 The btfdbot reference does not transfer wholesale to crypto
The btfdbot strategies (Super Oversold, Williams %R, 52-week low, Mega Dump, etc.) are all "buy oversold, sell the bounce" — and they work on **high-quality dividend stocks** precisely because those have a fundamental floor (a real business) that pulls price back up. **TRX has no such floor.** On crypto, "buy the dip" and "catch a falling knife" are indistinguishable at the moment of entry.

**Implication baked into this design:** the *exit and risk control* matter more than the entry. We cannot import btfdbot's win-rate claims and assume they hold on TRX. btfdbot's own mechanics, confirmed from their site: **independent simple triggers** (not a scoring model, "no fancy AI") with **trailing-stop exits**.

**Two defenses against the falling-knife problem** (added after reviewing the Valhalla multi-factor scanner, §4.4–4.5): a **trend-regime gate** (only buy dips when the market environment supports a bounce) and a **relative-strength signal** (favor coins that are strong vs their peers, not the ones bleeding hardest). Both directly attack "this dip is actually a collapse."

---

## 4. Strategy Logic

### 4.1 Entry — Confluence score engine (general mechanism)
**Decision:** Combine FVG + oversold + VWAP via a **weighted confluence score**: each signal emits a normalized value, the engine computes `sum(signal_value × weight)` and enters when the total `≥ entry_threshold`.

**Why this over the alternatives:** The weighted score is the *general form*. Other combination styles are special cases configured, not coded:
- One high weight + low threshold → that signal fires alone = **btfdbot-style independent trigger**.
- All weights required → **hard gate (AND)**.
- One triggers, others negative-only → **filter model**.

So a single simple mechanism (add numbers, compare to threshold) yields every combination style as configuration, supports **per-asset variation** (crypto and a future stock profile can weight signals differently), is **independently testable** per signal, and is the clean seam for RL to later learn the weights/threshold.

**Signal categories (organizational, inspired by Valhalla's composite score):** signals are grouped into categories for clarity and tuning — *Technical* (oversold, VWAP, FVG), *Relative* (relative strength), and later *Volume* (RVOL) and *Flow* (on-chain/exchange netflows). Weights are per-signal; the categories are a conceptual grouping that keeps the profile readable and makes it obvious which kinds of evidence a profile relies on. **The regime gate (§4.4) is deliberately NOT a confluence contributor** — it is a hard precondition, so a strong oversold reading can never override a hostile market regime.

### 4.2 The three signals
- **OversoldSignal** — RSI or Williams %R below a threshold. Fully mathematical, trivial to backtest. (Williams %R < −90 echoes btfdbot; RSI is the common default.)
- **VWAPSignal** — distance of price below VWAP. *Crypto adjustment:* no trading sessions, so no natural VWAP reset; use a **rolling-window VWAP (trailing 24h)** as the default anchor (alternative: fixed daily UTC reset). *Caveat:* Alpaca reports single-venue volume (thin vs Binance/Coinbase), so crypto VWAP can be noisy — acceptable for v1; could later pull aggregate volume. For a future stock profile, VWAP is session-anchored and rock-solid.
- **RelativeStrengthSignal** — measures the traded coin's strength against a **benchmark** (BTC/USD by default; total-crypto-market index later) over a lookback window: e.g. the coin's return minus the benchmark's return, or a ratio-line slope. Outputs a normalized score that is high when the coin is *outperforming* its peers. Rationale (from Valhalla's RS factor): in a no-floor market, you want to buy dips in coins that are *relatively strong*, not the ones bleeding hardest. Requires the Market Data Provider to also fetch the benchmark series.
- **FVGSignal** — Fair Value Gap detection. **Interface defined in v1, implementation added after the pipeline works.** FVG is hard to automate objectively (gap size, timeframe, filled vs unfilled, validity window are all fuzzy parameters); it's introduced as a confirmation contributor, not the thing the whole v1 hinges on.

Each signal: input candles → output normalized score in [0, 1] + metadata (for the trade journal). Pure functions, unit-testable in isolation.

### 4.3 Strategy Profile (the per-asset config object)
One profile per traded instrument, declaring:
- instrument + broker adapter + data adapter
- candle timeframe
- enabled signals, their weights, and their parameters
- entry threshold
- exit parameters (ATR multipliers, take-profit rule, max-hold)
- sizing risk %
- instrument-specific limits (position cap, cooldown, etc.)

This object *is* the "make it variable per asset" requirement. A profile can be configured to behave like a single independent trigger when btfdbot-style simplicity is wanted. The profile also declares the **regime policy** (§4.4) and the **relative-strength benchmark** (§4.5).

### 4.4 Regime gate (hard precondition, inspired by Valhalla's STAGE column)
**Decision:** Before the confluence score is even considered, a **RegimeFilter** classifies the market environment and can **veto** all entries. It is a gate, not a weighted signal — no entry score can override a hostile regime.

**How:** Classify trend regime from price versus a long moving average on a higher timeframe (e.g. price vs the 200-period MA on 1h or 4h candles): **uptrend** (price above, rising), **neutral**, **downtrend** (price below, falling). Optionally also gate on the benchmark's regime (don't buy alts when BTC is in free-fall). The profile's regime policy declares which regimes permit entries (default: uptrend and neutral; block downtrend).

**Why:** This is the strongest single defense against the falling-knife problem. Mean-reversion "buy the dip" has positive expectancy in an uptrend/range and *negative* expectancy in a sustained downtrend — the same oversold reading means opposite things in those two worlds. Gating on regime removes the entries that hurt most. Stan Weinstein's stage analysis (Valhalla's "STAGE 2") is the equity version of this same idea.

### 4.5 Relative strength usage
The RelativeStrengthSignal (§4.2) is wired as a confluence contributor by default, but a profile may also set a **minimum RS gate** (refuse entry if the coin is materially underperforming its benchmark) for a stricter posture. Benchmark defaults to BTC/USD; configurable per profile.

---

## 5. Exits & Risk Control

### 5.1 Non-negotiables on every position
1. **Hard stop-loss submitted with the entry** (not mental). On a no-floor asset this is the only thing bounding the loss.
2. **Max-hold time cap.** Holds are minutes-to-a-day; if the expected move hasn't happened in the window, the thesis was wrong — force exit. Brokers don't enforce this natively, so the Position Manager does.

### 5.2 Profit capture — ATR bracket + time cap
**Decision:** Stop = `entry − k×ATR`, take-profit = `entry + m×ATR`, plus the time cap.

**Why:** ATR-based levels scale with current volatility, so the same settings behave sensibly in calm and violent markets (unlike fixed-percent brackets). Deterministic and easy to backtest (unlike a trailing stop, which choppy crypto pullbacks trigger prematurely). A VWAP-reversion target is a viable future variant for pure mean-reversion but complicates fixed reward:risk math, so it's not the v1 default.

### 5.3 Position sizing — Fixed fractional risk
**Decision:** `size = (account_equity × risk_per_trade%) / stop_distance`, where `stop_distance = k×ATR`.

**Why:** The dollar loss if stopped out is **constant** regardless of volatility — wide stop → smaller position, tight stop → larger. The account bleeds at a controlled, predictable rate. It composes directly with the ATR stop and is the clean RL seam (RL adjusts only `risk_per_trade%`). Rejected alternatives: fixed-fraction-of-equity and fixed-dollar both let real risk swing with stop distance; Kelly needs an accurate edge estimate the author won't have early and blows up on overestimates.

### 5.4 Account-level circuit breakers (all four enabled)
1. **Daily-loss kill switch** — halt all new entries after the account drops a configured % in a day OR after N consecutive losses; requires manual reset. **On trip: stop new entries but keep managing open positions** (their stops/TPs/time-caps stay active). Rationale: panic-dumping into a spike-down often realizes the worst price. (Flatten-everything is available as a future config flag.)
2. **Max position-size cap** — clamp the sizing formula so no single trade exceeds a configured fraction of equity (default 25%); protects against a tiny ATR stop producing an enormous position.
3. **Max concurrent positions / one-per-instrument** — bounds total exposure and prevents stacking entries on the same coin.
4. **Re-entry cooldown after a stop-out** — wait a configured period before re-entering an instrument that just stopped out; stops the bot repeatedly buying the same falling knife.

These live in the **Risk Manager / Gatekeeper**, the gate between "signal fired" and "order sent."

---

## 6. Architecture

### 6.1 Run model — Always-on loop under a supervisor
**Decision:** One long-lived Python process loops: fetch data → evaluate signals → manage open positions → sleep ~60s → repeat, run under a supervisor (systemd or equivalent) that auto-restarts on crash. State persisted to disk; broker reconciled on startup.

**Why:** Crypto is 24/7, so the system must be continuously alive. This is the simplest model that satisfies that, and "seconds of latency is fine" rules out the complexity of a websocket event-driven design. Cron/stateless was rejected for coarser reaction time and trickier cross-run state.

### 6.2 Components (each: one job, clear interface, testable in isolation)

| # | Component | Responsibility | Key interface |
|---|-----------|----------------|---------------|
| 1 | **Market Data Provider** | Supply OHLCV candles + latest price for the traded symbol **and the benchmark** (e.g. BTC/USD) | `get_candles(symbol, timeframe, lookback)`, `get_latest_price(symbol)` — adapters: Alpaca (live/paper), Historical replay (backtest) |
| 2 | **Signal modules** | Each: candles → normalized score [0–1] + metadata | `OversoldSignal`, `VWAPSignal`, `RelativeStrengthSignal`, `FVGSignal` (later) |
| 2b | **Regime Filter** | Classify trend regime; veto entries in disallowed regimes (hard gate, runs before confluence) | `regime(candles_htf, benchmark) -> {uptrend\|neutral\|downtrend}`; `permits_entry(profile) -> bool` |
| 3 | **Confluence Engine** | Weighted-sum signals vs entry threshold → EntrySignal or none | `evaluate(candles, profile) -> EntrySignal?` |
| 4 | **Strategy Profile** | Per-instrument config (see §4.3) | data object loaded from config |
| 5 | **Risk Manager / Gatekeeper** | Enforce 4 circuit breakers, compute fixed-fractional size | `approve(entry_signal, account, state) -> SizedOrder \| Rejection(reason)` |
| 6 | **Broker Executor** | Submit/cancel orders, read positions/account | `submit_bracket_order(...)`, `get_positions()`, `get_account()` — adapters: Alpaca live, Alpaca paper, Simulated (backtest, with fees+slippage) |
| 7 | **Position Manager** | Track open positions, **enforce time-cap exits**, reconcile with broker on startup | `manage(now, positions)` |
| 8 | **Orchestrator / Main Loop** | Per tick, per active profile: data → engine → gatekeeper → executor → position manager; check time-caps; mode wires the adapters | `run()` |
| 9 | **State Store** | Persist open positions, kill-switch status, daily PnL, cooldown timers (SQLite) | `load()`, `save()` |
| 10 | **Trade Journal & Metrics** | Log every signal (with score breakdown), decision, fill, exit reason; compute metrics | `record(event)`, `summary()` |
| 11 | **Graduation Gate** | Compare metrics to config thresholds; block live until met | `can_arm_live() -> bool + reasons` |
| 12 | **Notifier (optional)** | Discord/SMS on entries, exits, kill-switch trips (reuse `algo-research-agent` infra) | `notify(event)` |

### 6.3 Data flow
```
candles (traded symbol + benchmark)
  → REGIME FILTER (hard gate: hostile regime → stop here, no entry)
  → signal modules (oversold, VWAP, relative strength, [FVG]) each → score
  → confluence engine (weighted sum vs threshold)
  → entry signal
  → risk gatekeeper (4 circuit breakers + fixed-fractional sizing)
  → broker executor (bracket order: entry + stop + take-profit)
  → position manager (persist state; enforce time-cap; monitor exits)
  → exit (stop / take-profit / time-cap)
  → trade journal → metrics → graduation gate
```

### 6.4 Three modes, one engine
- **Backtest** — Historical data adapter + Simulated broker (fees + slippage modeled). Fast replay of the real strategy.
- **Paper** — Alpaca data + Alpaca paper broker. Real-time, fake money; surfaces latency, fees, partial fills, weird ticks.
- **Live** — Alpaca data + Alpaca live broker. Real money.

Mode selection only swaps the data and broker adapters wired into the Orchestrator. Strategy, gatekeeper, sizing, exits, and journaling are identical across modes.

---

## 7. Verification & Measurement

### 7.1 Metrics (logged per trade, summarized)
**Expectancy per trade** (the headline number), win rate, average win vs average loss, profit factor, max drawdown, number of trades. Plus a full **trade journal**: every signal with its score breakdown, the decision, fill price, and exit reason — so any anomaly can be reconstructed.

### 7.2 Traps designed against (these are how you fool yourself)
- **Lookahead bias** — the strategy must never read a candle before it has closed. Backtests on the still-forming bar produce gorgeous fake results.
- **Cost realism** — fees and slippage go *into* the backtest. At short hold times, "profitable before costs, losing after costs" is the common outcome.
- **Overfitting** — tuning parameters until the backtest is perfect memorizes the past. Defenses: out-of-sample testing the tuning never saw, and requiring paper results to roughly match backtest before trusting it.

### 7.3 Graduation gate — disciplined, thresholds in config
**Decision:** Enforce the sequence **backtest → paper → live**, with explicit, configurable graduation criteria (e.g. ≥ N paper trades, positive expectancy after fees, max drawdown under a limit, paper roughly matching backtest). The system **refuses to arm live mode** until the criteria are met.

**Why:** Protects the author from their own optimism — the most common way personal trading bots lose money is going live on a backtest that was curve-fit.

---

## 8. Configuration — Recommended starting defaults (all tunable)

| Parameter | Default | Notes |
|-----------|---------|-------|
| Candle timeframe | 15m | Fits minutes-to-a-day holds |
| Loop interval | 60s | "Seconds of latency is fine" |
| `risk_per_trade` | 1% of equity | Fixed-fractional sizing |
| ATR period | 14 | |
| Stop multiple `k` | 1.5 × ATR | |
| Take-profit multiple `m` | 2.0 × ATR | ~1.33 reward:risk |
| `max_hold` | 8 hours | Time-cap exit |
| Kill switch | −5% day OR 4 consecutive losses | Manual reset; stop-new-entries behavior |
| Max position cap | ≤ 25% equity | |
| Max concurrent | 1 | Single focused coin to start |
| Cooldown after stop-out | 60 min | |
| Regime MA | 200-period on 4h candles | Trend classification for the gate |
| Regime policy | allow uptrend + neutral; block downtrend | Per-profile |
| RS benchmark | BTC/USD | Per-profile; total-market index later |
| RS lookback | 24h | Window for relative-strength comparison |
| RS minimum gate | off (signal-only) by default | Optional stricter posture |
| Backtest costs | Alpaca crypto fee/side + slippage buffer | Must be modeled |

These are starting points to be calibrated during backtest/paper, not claims of optimality.

---

## 9. Error Handling

- **API failures** — retry with exponential backoff.
- **Stale/missing data** — skip the tick; never trade on bad data.
- **Startup** — reconcile bot state against the broker; the broker is the source of truth for open positions.
- **Order rejected by broker** — log and surface; do not blindly re-submit.
- **Process crash** — supervisor restarts; state restored from disk + broker reconciliation.

---

## 10. Future Seams (designed for, not built in v1)

- **RL position sizing** — replaces the fixed `risk_per_trade%` logic inside the Risk Manager; the gatekeeper interface is unchanged.
- **LLM signal interpretation** — just another Signal module emitting a normalized score into the confluence engine; could reuse the Ollama setup from `algo-research-agent`.
- **Shorting** — a new Broker Executor adapter behind the existing interface (plus a venue that supports it).
- **Stocks / multi-asset** — additional Strategy Profiles + data/broker adapters; VWAP switches to session-anchored. The equity-only Valhalla factors (EPS%, SALES%, FWD%, sector) become relevant here.
- **More signal modules (Valhalla-inspired, deferred)** — RVOL (relative-volume confirmation), support-level proximity (merge with FVG/key-levels), and FLOW (crypto analog of institutional/dark-pool flow: exchange netflows, whale on-chain activity, large trades). Each is just another Signal module emitting a normalized score — drops into the confluence engine without touching the rest.
- **Notifications** — reuse Discord/SMS infrastructure from the sibling `algo-research-agent` project.

---

## 11. Front End — Monitoring Dashboard & Control API

A Valhalla-styled single-page app to **monitor and control** the bot.

### 11.1 Stack
- **React 18 + Vite + plain CSS**, matching `algo-research-agent` conventions. Dark navy Valhalla aesthetic: top nav, colored status banner, score chips, dense data tables, green/red numerics.
- **Backend API: FastAPI on `:8000`**, with the existing dev-proxy pattern (`/api` REST + `/ws` websocket).
- **Live updates pushed over websocket** so the UI feels live like Valhalla; REST for initial load and control actions.
- The API is a **thin read/control surface over existing components** (State Store, Trade Journal/Metrics, Position Manager, Risk Manager) — it holds no trading logic of its own.

### 11.2 Layout
- **Top nav** — name, **MODE indicator** (BACKTEST / PAPER / **LIVE shown in unmistakable red**), connection status, last-updated.
- **Status banner** — bot RUNNING/HALTED, current regime, day P&L, HALT button.
- **Signal panel (centerpiece)** — per-signal `value × weight = contribution`, total score vs entry threshold, regime-gate verdict. The "why" behind every decision.
- **Position panel** — entry / now / size / stop / TP, unrealized P&L, time-in-trade vs max-hold; or "Flat — waiting for signal".
- **Risk panel** — equity, risk/trade, kill-switch state, concurrent count, cooldown timers.
- **Journal table** — dense Valhalla-style table: time, side, entry, exit, P&L, exit reason, score-at-entry, regime.
- **Metrics panel** — expectancy, win rate, profit factor, max drawdown, trade count.
- **Settings view** — view/edit strategy-profile params.

### 11.3 Control surface (full) + mandatory guardrails
Controls: HALT (trip kill-switch) & reset, pause/resume new entries, switch mode (paper/live), edit profile params, manual close/flatten.

Because the UI can move real money, these guardrails are **required**, not optional:
- **Localhost-only binding by default + a shared-secret token on every write endpoint.** Never bind to `0.0.0.0` / expose to the internet without real authentication.
- **Server-side enforcement, never UI-hidden.** The graduation gate blocks switching to LIVE *on the server*; the client cannot bypass it. All control validation lives server-side.
- **Explicit confirmation** for financial/destructive actions (go-LIVE, flatten, param edits) — typed/confirm dialog.
- **Unmistakable LIVE indicator** so real-money actions aren't taken thinking it's paper.
- **Audit log** — every control action (what/when) recorded alongside the trade journal.
- Read endpoints (state, journal, metrics) are safe locally; **write endpoints require token + confirmation**.

### 11.4 API sketch
- `GET /api/state` → mode, status, regime, live signal breakdown, position, risk, account
- `GET /api/journal`, `GET /api/metrics`
- `GET /api/profile`, `PUT /api/profile` *(write, guarded)*
- `POST /api/control/{halt|resume|mode|flatten}` *(write, guarded, audited)*
- `WS /ws` → pushes state snapshots + events (entries, exits, kill-switch trips)

---

## 12. Tech Notes (non-binding, for the planner)

- **Backend:** Python; `alpaca-py` SDK; `pandas`/`numpy` (indicators via `pandas-ta`/`ta` or hand-rolled); SQLite for state; **FastAPI + uvicorn** for the API/websocket; systemd for supervision. Keep dependencies minimal.
- **Frontend:** React 18 + Vite + plain CSS (mirror `algo-research-agent/frontend` structure: `components/`, `pages/`, `hooks/`; dev proxy `/api`→`:8000`, `/ws`→ws).
- Project lives in `crypto-swing-bot/` (separate from `algo-research-agent`, may borrow its notification layer later).
