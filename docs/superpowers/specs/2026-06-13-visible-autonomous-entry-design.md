# Design — Visible Autonomous Entry (Rebuild Sub-project 1)

**Date:** 2026-06-13
**Status:** Draft for review
**Supersedes framing of:** prior A→E roadmap "all green" status (see Context)

---

## 1. Context & problem

The prior roadmap (`docs/ROADMAP_STATUS.md`) declares sub-projects A→E "DONE, green, 6/6
usage sessions pass, 0 drift." The live product, however, has **never executed a single paper
trade**, the dashboard shows `0.000` everywhere and stale/random charts, and "nothing moves by
itself." Both statements are true at once — and that contradiction is the core disease: the
health checks (D self-test, E usage agent) measure *"pytest passes, routes load, npm builds,"*
not *"the bot actually traded."* A green light that does not correlate with the product working
is worse than no light.

**Root cause (evidence, captured 2026-06-13 from the live container):**

```
GET /api/state → "portfolio": { "mode": "paper", "running": false }
                 every strategy: "running": false, "snapshot": {}
```

The `PortfolioSupervisor` heartbeat loop (`supervisor.start()` → background thread calling
`tick_all()` every `poll_seconds`) is **only triggered by a manual `POST /api/control/start`**.
Nothing starts it on app boot. Because the project's standing policy rebuilds/restarts the
container on every change, the bot is left **idle after every restart**. No ticks → no signal
evaluation → no entries → empty snapshots → dashboard renders zeros. This single wiring gap
explains the entire reported symptom set.

Secondary findings:
- 5 armed strategies are duplicates/noise (`aggressive`, `conservative`, `conservative/ai`,
  `ai_kronos`, `ict_fvg`) — not a clean canvas.
- `ai_kronos` is on `BTC/USDT`, which silently never fills on Alpaca paper (must be `*/USD`).
- The entry path (`Orchestrator._maybe_enter`) has ~8 silent `return` gates; a blocked entry
  leaves no trace, so "nothing correlates."

## 2. Goal & non-goals

**Goal.** After a container rebuild, with **zero human input**, the bot starts ticking on its
own and a paper position visibly opens on a chart, accompanied by a plain-language reason. The
operator can read a single reliability score that observes whether the documented purpose
(the autonomous loop completing) is actually happening.

**Non-goals (explicitly deferred):**
- No error-budget *enforcement*, no graceful degradation, no agent work-routing. The score is
  **read-only / observe-only** for now; integration is re-calibrated with the user later.
- No self-improvement agent build-out (Playwright issue-hunting). Deferred to a later
  sub-project. (When built, it *detects and documents* issues — it never writes/applies code.)
- No strategy-*creation* UI. Strategies are fixed, version-controlled definitions.
- No reinforcement learning, no Kronos, no LLM "brain" in the entry path.
- No real-money / live-eligible trading. Paper only.
- Not chasing alpha — the demo strategy is proof-of-life, not a profitable system.

## 3. The Contract (lightweight, observe-only)

The full SRE Contract is intentionally collapsed to its minimum viable form:

- **Primary SLI:** *the autonomous loop completes.* A cycle = one `tick_all()` pass.
- **Per-stage health.** Each tick is scored across the five stages, each independently:
  1. **ingest** (fresh candles + price available, not stale)
  2. **reconcile** (broker/state sync ok)
  3. **manage** (open-position management ran without error)
  4. **decide** (signal evaluation ran; reaching a clean "no trade" on fresh data = success)
  5. **persist** (state saved)
  A stage that throws, times out, or runs on stale/missing data = a failure **for that stage**.
  A clean cycle that decides "no entry" on fresh data is a **success**, not a failure.
- **Error budget = a number.** Per-stage success ratio over a rolling window (default: last
  200 cycles), plus an overall score. Surfaced in the dashboard summary and `/api/health`.
  **No enforcement.** It exists only to answer "is the documented purpose actually applicable?"

## 4. Design

Five focused units. Each reuses existing code where possible.

### 4.1 Auto-start on boot
- Add a FastAPI **lifespan/startup hook** in `webmain.py`/`web.py` that, on app start, calls
  `controller.start()` when (a) mode is `paper` and (b) ≥1 strategy is armed.
- Persist a **desired-running flag** (e.g. `running_desired` in the profiles/portfolio store)
  set true by `control/start` and false by `control/stop`/`halt`. On boot the hook honors the
  persisted desire so a restart **resumes autonomously** instead of going idle.
- Idempotent: `start()` already no-ops when `_running`.

### 4.2 Clean the slate → 2 rigid strategies
- Disarm/remove the existing 5 noise strategies.
- Define exactly two fixed strategy profiles, version-controlled (seeded on boot if absent):
  - `btc_trend` — symbol `BTC/USD`, timeframe `15m`
  - `eth_trend` — symbol `ETH/USD`, timeframe `15m`
- No creation menu surfaces these; they are declared in code/seed data.

### 4.3 A demonstrably-firing strategy (keep engine, loosen gates)
- Add one minimal signal `ma_cross` (`signals/ma_cross.py`): fast/slow moving-average cross
  (EMA 9 over EMA 21; add a one-line `ema()` to `indicators.py`). Emits a positive score when
  fast crosses above slow, else 0. Implements the existing `Signal` interface.
- Configure both profiles permissively so entries reliably fire on ~5-day 15m history:
  - `signals = ["ma_cross"]`, weight 1.0, `entry_threshold` low enough that a cross passes.
  - `allowed_regimes` includes `UPTREND` and `NEUTRAL` (not just UPTREND).
  - ATR bracket for stop/take-profit (reuse `bracket_levels`); standard risk sizing.
- The entry runs through the **real** `Orchestrator._maybe_enter` path — proving the actual
  engine works, not a bypass.

### 4.4 Per-tick telemetry ("fail loudly")
- `Orchestrator.tick()` records, per strategy per cycle: timestamp, per-stage outcome
  (ok/fail + reason), and the **entry decision + the exact gate that stopped it** (paused /
  existing position / risk gate / regime / confluence-below-threshold / atr / sizing /
  portfolio gate / **ENTERED**).
- Persisted to a small rolling store (reuse `StateStore`/journal or a new lightweight table)
  and exposed via `/api/health` and per-strategy in `/api/state` snapshots.
- This both fixes "nothing correlates" and is the data source for §3's score.

### 4.5 Clean-canvas dashboard + read-only score
- Strip the dashboard to:
  - **Portfolio summary**: mode, running, equity, open positions, overall reliability score.
  - **Per-strategy card**: name, symbol, running, last tick time, last decision + reason,
    open position (entry/stop/tp/qty), realized+unrealized P&L.
  - **One price chart** per strategy with entry/exit markers.
  - **Reliability tile**: the per-stage + overall score (observe-only, no controls).
- Remove the strategy-creation menu and the random/0.000 panels.

## 5. Components & boundaries

| Unit | Files (reuse / new) | Depends on |
|---|---|---|
| Auto-start | `web.py`, `webmain.py`, `profiles.py` (new `running_desired`) | supervisor lifecycle |
| Clean slate | seed data / `profiles.py`, `presets.py` | profile store |
| ma_cross strategy | **new** `signals/ma_cross.py`, `indicators.py` (`ema`), profile seeds | confluence, regime |
| Telemetry | `orchestrator.py`, `supervisor.py`, `state.py`, `web.py` (`/api/health`) | StateStore |
| Dashboard | `frontend/src/*` | `/api/state`, `/api/health`, `/api/candles` |

## 6. Data flow

`boot → lifespan hook reads running_desired → controller.start() → supervisor thread loops:
tick_all() → per strategy Orchestrator.tick() [ingest → reconcile → manage → decide(_maybe_enter)
→ persist], each stage emits a telemetry record → snapshot + health store updated →
frontend polls /api/state + /api/health → cards, chart markers, score render.`

## 7. Error handling / fail-loudly

- Every stage is wrapped so an exception is **recorded as that stage's failure with the message**
  (not swallowed silently), and the loop continues to the next strategy/cycle.
- A blocked entry always records *which* gate blocked it. There is no longer a silent path to
  "did nothing."
- Stale data (candles older than one timeframe interval) marks `ingest` as failed for that cycle.

## 8. Testing & success criteria

**Deterministic (unit/integration):**
- `ma_cross` emits a positive score exactly when fast crosses above slow (synthetic series).
- Fed a synthetic candle series containing an up-cross, `Orchestrator._maybe_enter` **places a
  market buy** and persists an `OpenPosition` (proves the loosened gates actually allow entry).
- Telemetry records the correct blocking gate for each silent-return condition.
- Auto-start hook calls `controller.start()` when `running_desired` is true and ≥1 armed paper
  strategy; no-ops otherwise.
- Score computes the correct per-stage ratio over a known sequence of cycle records.

**Live acceptance (must observe, not assume):**
- After `docker compose build && up -d` with no manual action, within one poll interval
  `GET /api/state` shows `"running": true` and non-empty snapshots.
- Within a bounded number of cycles on real BTC/USD + ETH/USD 15m data (or a seeded candle
  injection for the smoke test), **a paper position opens** and is visible on the dashboard
  chart with a reason.
- `/api/health` returns a populated per-stage + overall score.

**Regression gate:** existing `pytest -q` suite stays green; `frontend && npm run build` passes.

## 9. Open items deferred to later sub-projects
- SRE error-budget enforcement + per-component degradation + agent work-routing.
- Self-improvement detector/reporter agent (Playwright + codebase → documented findings only).
- Simple format for the operator to add further rigid strategies to the clean canvas.
