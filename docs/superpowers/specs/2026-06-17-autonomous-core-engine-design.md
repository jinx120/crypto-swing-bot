# Autonomous Core Engine — Design Spec

**Date:** 2026-06-17
**Status:** Approved (brainstorm), pending spec review → implementation plan
**Sub-project:** 1 of the redesign (engine first, UI later)
**Supersedes:** the v1 roadmap (`A→E` phasing, supervisor, self-test gate, usage agent). Old specs in
this directory are reference only.

---

## 1. Purpose

Rebuild crypto-swing-bot around a **bulletproof, fully autonomous trade-execution core** that
decides and acts on its own, on **paper BTC/USD**, and **shows results good or bad with zero user
input** — surfaced through a durable journal and an on-demand report. No UI, no self-improvement,
no health-check machinery in this sub-project.

This is a deliberate retreat to the thing that was originally intended but strayed from: a small,
verifiable engine. The UI is a *separate later sub-project* that only **reads** the journal and can
never affect engine correctness.

### Root-cause framing (why we are here)
The signal/ML brain (Kronos + long-only confluence) and the low-level plumbing (Alpaca broker
adapter, order lifecycle, client-side exits, risk scaffolding) were **sound**. What rotted the
platform was the **self-improvement / drift / usage-agent / selftest "health check" machinery and
the glass UI** layered on top. Those are cut.

---

## 2. Scope

### In scope
- One instrument: **BTC/USD** (Alpaca paper, USD-funded — never USDT).
- **5-minute bars**, decide every 5 minutes. ~5 days of live history (~1440 bars) is sufficient
  Kronos context; the deep-history archive is **not a dependency** for this sub-project.
- Long-only / spot only (Alpaca crypto cannot short).
- One position at a time.
- Headless engine in the Docker `swingbot` container; auto-resumes desired run-state on restart.
- Durable SQLite journal + an on-demand `report`.

### Out of scope (cut or deferred)
- ❌ Self-improvement / drift detection / usage-agent
- ❌ Selftest "health check" auto-machinery
- ❌ React/glass UI (separate later sub-project, read-only over the journal)
- ❌ Multi-asset supervisor / configurable watchlist (generalize to N **after** single-instrument is proven)
- ❌ Deep-history archive ingestion (only needed if we later move to longer timeframes)

---

## 3. Architecture — one headless tick loop over reusable modules

Orchestration approach **A (chosen):** a single synchronous tick loop runs the full pipeline every
5 minutes, top to bottom, with every stage wrapped so no stage failure kills the loop. This is the
opposite of v1's event-driven sprawl. (Rejected: B event-driven/async — overkill for 5-min single
instrument; C reuse v1 supervisor — keeps the architecture we strayed into.)

```
every 5 min  ──►  TICK:
  1. Data       fetch/append 5-min BTC/USD candles → rolling window (SQLite)
  2. Reconcile  pull broker truth → fix state drift (positions / open orders)
  3. Exits      if position open: ATR-bracket + max-hold check → maybe EXIT
  4. Decide     if flat: Kronos forecast + long-only confluence/trend gate → ENTER_LONG | HOLD
  5. Risk       if ENTER: fixed-fractional size + gates → vetoed-reason | order intent
  6. Execute    place order, track lifecycle (pending_new), reconcile fill
  7. Journal    write every decision / order / fill / exit / P&L with a reason string
```

### Module map (each isolated, single-purpose, independently testable)

| Module | Responsibility | Origin |
|---|---|---|
| `data/` | Backfill ~5d + append 5-min candles; `get_window(n)` over SQLite candle store | reuse v1 |
| `decision/` | **Pure function** `decide(window, position) -> Decision(action, confidence, reason)`. Kronos forecast + long-only confluence + hard trend-regime gate (anti falling-knife) | reuse Kronos + signals, rewrap as pure fn |
| `risk/` | Size (~1% fixed-fractional) + gates: daily-loss kill switch, max-position cap, one-at-a-time, re-entry cooldown → order intent or vetoed reason | reuse v1 |
| `broker/` | Alpaca paper adapter; full order lifecycle incl. `pending_new`; USD pair only | reuse v1 |
| `execution/` | Order intent → place → track lifecycle → reconcile fill; **client-side exit manager** (ATR bracket + max-hold cap) | reuse v1 |
| `state/` | SQLite: current position, open orders, `running_desired` (auto-resume on restart) | reuse v1 |
| `engine/` | The tick loop + scheduler; failure-tolerant orchestrator that never dies | **new, small** |
| `journal/` | Append-only ledger of all engine activity + `report` (positions, open/closed P&L, win/loss, history) | **new** |

### Key design decisions
- **`decision/` is a pure function** of `(candle_window, current_position)` — no I/O, no side
  effects. This is the single most important decision: it makes Kronos deterministically testable
  against fixtures and is almost certainly where v1 tangled. All randomness/model state is passed in.
- **One code path for backtest and live.** The same `decide → risk → exit` logic runs in a backtest
  harness over historical bars and in the live loop. (v1 durable lesson: divergence here is fatal.)
- **Exits are client-side.** Alpaca crypto has no broker brackets; the exit manager enforces ATR
  stop/TP + max-hold cap on the open position every tick.

---

## 4. Error handling — the bulletproof contract

The loop is a supervisor that **never dies**.

- Every stage is wrapped. A stage failure is **journaled with its reason** and the tick is
  **skipped**, not fatal. The next tick runs normally.
- **Reconcile and the daily-loss kill switch run before any new entry**, every tick.
- **Truthfulness over optimism** (v1's hardest-won lesson): never report success on a partial
  failure. Order placement, fills, and exits report their true post-conditions; an order that is
  still `pending_new` is reported as such, not as filled. State that cannot be read is reported as
  unknown, not as a default.
- **Auto-resume:** `running_desired` persists; on container restart the engine resumes the loop
  only if desire was true (no silent opt-in).

---

## 5. Results surface — journal + report (no UI)

- **Journal (SQLite, append-only):** one row per material event — tick decision (incl. HOLD with
  reason), order placed, fill, exit, realized/unrealized P&L, kill-switch trips, errors. Every row
  carries a human-readable `reason`.
- **`report` (CLI command + plain endpoint):** current position, open P&L, closed-trade history,
  win/loss count, cumulative P&L. Read-only. This is the entire "show results good or bad" surface.
- The future UI is a thin read-only renderer of these same queries.

---

## 6. Testing strategy

- `decision/` & `risk/`: pure unit tests over fixture candle windows / equity states.
- `execution/`: against a **fake broker** that reproduces the `pending_new` stall and partial fills.
- `engine/`: integration test — fake broker + fake data → one full tick → assert exact journal rows.
- `journal/`: schema + `report` output tests over a seeded ledger.
- **Backtest harness**: runs the shared `decide→risk→exit` path over historical bars; used to
  validate engine behavior before any live run.
- Live acceptance (Claude-only, see §7): rebuilt container trades a real paper tick, journal +
  report reflect it, auto-resume verified.

---

## 7. Collaboration model — Claude (clawd) + Codex (VM)

Two agents build this in parallel. The module boundaries are the work boundaries.

### The asymmetry that drives the split
- **Claude has the live environment**: the working tree, Docker `swingbot`, real Alpaca paper, and
  the ability to run/verify live. Claude owns anything that must be verified against reality.
- **Codex (gpt-5.5, YOLO/autonomous on the `ahmad@192.168.1.35` VM)** sees only the **git repo**.
  Codex owns pure, deterministic, fully-unit-testable modules that need no live environment.

### Division of labor
| Agent | Owns (build + test) | Why |
|---|---|---|
| **Codex** | `decision/` (pure fn + Kronos rewrap), `risk/` gates, `journal/` schema + `report`, the **backtest harness** | Pure/deterministic; provable with unit tests against fixtures; no live deps |
| **Claude** | `broker/` + `execution/` (need real Alpaca paper behavior), `engine/` tick loop, `state/` auto-resume, Docker rebuild, **all live acceptance** | Requires the live container, real paper fills, and the `pending_new` behavior only observable live |
| **Shared** | Module interfaces (the typed contracts: `Decision`, order intent, journal row) are agreed **first**, before parallel work starts | Prevents integration drift |

### Branch & integration protocol
- Interfaces/contracts land on `master` **first** (small commit, both agents pull).
- **Codex works on a `codex/core-engine` branch**; commits per task; pushes.
- **Claude integrates on `master`**: pulls Codex's branch, wires modules into the live `engine/`,
  runs live acceptance, merges. Claude is the integrator because only Claude can live-verify.
- Docker rebuild + restart of `swingbot` is Claude's, after every integrated change (standing rule).

### Handoff over the tmux bridge (ref: `codex-vm-bridge` memory)
- Claude → Codex: write task file → `scp` to VM → `tmux -L codex-managed load-buffer` →
  `paste-buffer -t codex` → `send-keys Enter`.
- Codex → Claude: `ssh redji@…` then `tmux load-buffer`/`paste-buffer -t claude`; messages prefixed
  `FROM CODEX:`.
- Pattern: push+pull as tasks need; no permanent poller. Codex pings Claude when a branch is ready
  for integration/live-verification; Claude pings Codex with the next pure-module task or a fixture
  it needs.

---

## 8. Deliverable / definition of done

A headless engine that, with no user input, autonomously trades paper BTC/USD on 5-min bars in the
`swingbot` container, enforces client-side exits and risk gates, survives restarts (auto-resume),
and records every decision and outcome to a journal readable via `report`. Full test suite green;
backtest harness runs the shared path; live acceptance passes on `:8000`/CLI. No UI, no
self-improvement, no health-check machinery.

---

## 9. Open items for the implementation plan

- Exact `Decision` / order-intent / journal-row type contracts (write these first; they gate the
  parallel split).
- Which concrete v1 files map into each module (audit during planning; reuse, don't rewrite).
- Kronos invocation details inside the pure `decide()` (model load is I/O — passed in as a handle,
  kept out of the pure boundary).
- `report` exact columns/format.
