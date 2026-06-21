# Roadmap Status — crypto-swing-bot

> **Single source of truth for "where are we / what's next."** A new session should read this
> file first for any platform-roadmap work, then jump to the **NEXT ACTION** below.
> Keep this file updated at the end of every work session (it is the cross-session memory anchor).

**Last updated:** 2026-06-20

---

## ▶ NEXT ACTION

**▶ EXECUTE (in progress, via Codex VM bridge) — "Kronos POC Paper Trader".** Plan:
**`docs/superpowers/plans/2026-06-20-kronos-poc-paper-trader-implementation.md`** (24 tasks, 6 phases A–F).
Codex (gpt-5.5, VM bridge) implements code+TDD+commits+push per task; **clawd docker-rebuilds + live-verifies
per phase** (Codex has no live container). To resume mid-execution: check `origin/core-engine` HEAD + the
Codex pane (`tmux -L codex-managed capture-pane -t codex -p`), pull, find first unchecked `- [ ]`, continue.

- **✅ Phase A (Tasks 1–5, data decoupling) DONE + LIVE-VERIFIED (2026-06-21)** @ `origin/core-engine 0295a6b`.
  Gate: 581 passed, 5 skipped, ruff clean, frontend build+test green. Live on `:8000`: `/api/data-source`=coinbase;
  BTC/USD 15m candles populate from Coinbase with the **broker unconfigured** → the "no fresh closed bar" root
  cause is FIXED (data fully decoupled from broker). Task 3 plan amendment `aedb527` (updated `test_market_provider.py`
  to the alpaca path — the old tests encoded the removed coupling).
- **▶ Phase B (Tasks 6–9, fixed-% Kronos bracket) IN PROGRESS** by Codex.

**⚠️ Parked work:** clawd's host working tree had a large set of unrelated uncommitted changes (token-auth/E-removal
era: web.py, webmain.py, many tests, frontend, README, docker-compose.yml). To sync+build cleanly it is stashed at
**`stash@{0}` ("clawd-temp-pull")** with a clean tree at `0295a6b`. Restore later with `git stash pop` (it conflicts
with Phase A's `frontend/src/api.js` — resolve that one file) or drop if obsolete. **Do not lose it.**

**Key implementation reframe baked into the plan (transparent, reversible):** "KronosBracketStrategy" is
realized via the **existing** `KronosForecastSignal` (which already computes `pct_change/threshold_pct`) +
a **profile preset** (Task 8) + a **new fixed-% bracket** (Tasks 6–7), all running through the existing
`Orchestrator` (broker-confirmed fills/reconcile from phases 3–6) — NOT a new standalone class. This
reuses what the DECISIONS brief said to KEEP and avoids re-implementing the fill safety net. Phase A
(data decoupling, Tasks 1–5) is the demoable core and ships first.

**One-line product summary:** a hands-off autonomous **paper** trader on the principle *"it does what I
don't need to know how to do"* — selectable data feed (Coinbase default, decoupled from the broker) →
a single **Kronos-bracket** strategy (predict up ≥ +0.75% → market BUY → software TP +1.5% / SL −1%) →
deterministic auto-rebalance + drawdown circuit breakers → a tiny local-LLM **advisor** (bounded
auto-apply) that tunes config/weights so the user never types a number. Strips discovery, old strategy
editor, managed strategies, paper_probe, and the old per-trade brain. Full detail in the DECISIONS brief.

**Carry-forward (still true, lower priority under the new design):** the stored Alpaca paper key
`PKPLVRJZQKCYWE7VZ6W6OHDGFZ` is **401 unauthorized** — but under the new design this **no longer blocks
the charts** (data decouples to Coinbase); a valid Alpaca paper key is needed only for **order
execution / fills**. (`core-engine` → `master` consolidation done earlier: FF `8705783 → 40cf49d`,
pushed; `master` = `core-engine` = `40cf49d`.)

---

**✅ AUTONOMOUS-FIRST UI REDESIGN — COMPLETE & LIVE (2026-06-20).** Plan
`docs/superpowers/plans/2026-06-20-autonomous-ui-redesign.md` executed end-to-end. **Tasks 1–13 (the full
frontend rebuild) implemented by Codex (gpt-5.5) over the VM bridge** — committed per task, pushed to
`origin/core-engine`; **clawd ran Task 14 on the host** (gate + Docker + Playwright smoke + live-verify).
The 8-tab manual UI is gone; the app is now a **3-route HashRouter SPA**:
- `#/` **Mission Control** — status strip (loop state/mode/equity/PnL, health dots, Start/Stop, broker
  banner), per-coin grid (arm/disarm/flatten + Add coin dialog), rebalance strip, live decision journal.
- `#/coin/:name` **Coin Detail** — six per-symbol panels (chart, position, live stats, EMA-vs-Kronos
  backtest, recent trades, decision journal); routed by **strategy name** (symbols contain `/`).
- `#/settings` **Settings** — broker connection (Test/Save/Reconnect), rebalance config, advanced
  controls, API token.
Stack: Tailwind v3 + hand-authored shadcn-style primitives (Radix Dialog), `react-router-dom` v6,
`lightweight-charts` v5, pure view-logic in tested `lib/derive.js` (12 Vitest tests).

**Two plan-ordering bugs found & fixed during execution** (Codex stopped + signaled each via the SSH
bridge; clawd patched the plan, pushed, re-handed): (1) Task 1 dropped the `marked` dep while the old
`App.jsx` still mounted `Guide.jsx` → build gate broke; `marked` now **retained until Task 13**. (2)
`vitest run` exits 1 on "No test files found" → the `test` script now uses **`--passWithNoTests`**.

**✅ SUB-PROJECT E (Usage Agent / selftest) REMOVED (2026-06-20, user-directed "remove this nonsense").**
The redesign deleted the Health page + `frontend/src/guide.md` + every old route the nightly Usage Agent
audited (`/#/guide`, `/#/brain`, `/#/health`, `/#/strategy`, `/#/discover`), so it audited a UI that no
longer exists (surfaced as a backend doc-ref test failure). Removed: `src/swingbot/selftest/` package +
its 12 tests + `tests/test_web_agent.py`; the `/api/agent/*` endpoints + `agent_dir` wiring
(`web.py`/`webmain.py`, dropped the now-unused `FileResponse` import); the dead `api.js` agent client
methods; `scripts/nightly-selftest.sh`; and the **03:00 cron entry** (`crontab` cleaned). **Sub-project E
is retired — the platform is now A–D + the autonomous-entry sub-project.**

**Gates:** backend **570 passed, 5 skipped** (new baseline — down from 659 after the E removal), ruff
clean; frontend `npm run build` green + `npm run test` **12/12** (derive). **Live-verified on `:8000`**
(container rebuilt, `runtime: runc` override): all spec-§13 smoke checks pass (screenshot
`docs/redesign-smoke.png`); `GET /api/agent/runs` → **404** (removed); broker-recovery surface reachable
(amber "Broker not connected" banner on `#/` + form on `#/settings`); the Start/Stop toggle is wired and
truthfully surfaces the 401 (no clean flip possible under the stale key) — `running_desired` was restored
to `false` after the test. **`core-engine` `40cf49d` merged to `master` (FF) and pushed**;
`master` = `core-engine` = `origin/master` = `40cf49d`.
**Smoke note:** no `@playwright/test` runner exists in the repo, so the smoke is MCP-driven (matching the
`docs/autodash-smoke.png` precedent) — the committed artifact is the screenshot, not a `.spec.js`.

---

**✅ `core-engine` MERGED TO `master` (2026-06-20).** Fast-forward merge (`f37fc02 → 3a94791`, +70
commits, no conflicts/no merge commit) — `master` was a strict ancestor of `core-engine`. Pushed to
`origin/master` (non-force FF). This reconciled all previously-unmerged core-engine work onto `master`:
the **Autonomous Trading Dashboard**, the **Portfolio Rebalancing Layer**, and the **Broker Connection
Manager**. Merged code is identical to the gated `256a1a7` (+ a docs commit), so the **659 passed,
6 skipped**, ruff-clean, frontend-build-green gate holds. `core-engine` is **kept** as the shared
ongoing branch (Codex VM tracks it); it was not deleted. `master` = `core-engine` = `3a94791`.

**✅ BROKER CONNECTION MANAGER — COMPLETE & LIVE (2026-06-20).** Plan
`docs/superpowers/plans/2026-06-20-broker-connection-manager.md` executed end-to-end (11 tasks) via
subagent-driven development — a fresh implementer subagent per task with a two-stage (spec + code
quality) review between tasks — then a **Codex (gpt-5.5) final whole-branch review over the VM
bridge**. Branch `core-engine` @ `256a1a7`, pushed to `origin/core-engine` (clawd = origin = VM synced).

Shipped: `swingbot.broker.adapter` registry (`CredentialField` schema + `make_broker`/`make_data`/
`test_connection`; Alpaca registered); versioned **v2 multi-broker `CredentialStore`** with transparent
v1→v2 migration (legacy `set/status/get` preserved); adapter-backed `make_broker`/`make_data`/
`test_broker`; supervisor **`reconnect()`** hot-swap (mirrors `set_mode` lock ordering); `MarketData`
via `make_data()`; web endpoints `GET /api/brokers`, `PUT /api/brokers/{id}/credentials`,
`POST /api/brokers/{id}/test`, `POST /api/brokers/active`, `POST /api/brokers/reconnect`; **autonomous
auth** (`SWINGBOT_TOKEN` env + `GET /api/auth/bootstrap`, safe-by-default 403 unless
`SWINGBOT_LOCAL_TRUST=1`); schema-driven **Settings → Broker connection** panel; `docker-compose.yml`
env (`SWINGBOT_TOKEN`, `SWINGBOT_LOCAL_TRUST=1`).

Review caught real defects: (a) a stale `NoCredentials` test double after the `build()`→`make_broker()`
change (fixed `b65fd75`); (b) **Codex final review found a genuine secret-leak** — `test_connection`
returned `str(exc)`, and an Alpaca auth error can embed the submitted `secret_key`, which
`POST /api/brokers/{id}/test` would echo; fixed by redacting schema-marked secret values from error
detail + regression test (`256a1a7`). Gate: **659 passed, 6 skipped**, ruff clean, frontend build green.

**Live-verified on `:8000`** (container rebuilt + restarted): `GET /api/brokers` →
`active:alpaca, configured:true` with secrets masked; `GET /api/auth/bootstrap` → `{"token":"swingbot-local"}`;
`POST /api/brokers/reconnect` (X-Token) → `{"ok":true,"detail":"reconnected"}`; reconnect without token → 401;
secret never present in any status/list/test response.

**⚠️ NEXT ACTION (carry-forward): the stored Alpaca paper key returns 401 unauthorized.** This is a
**pre-existing** condition (key `PKPLVRJZQKCYWE7VZ6W6OHDGFZ` invalid/rotated since ~2026-06-20, per the
S179/S180 auth investigation), NOT introduced by this feature — it is exactly what this feature was built
to remedy. The bot auto-start fails with `"unauthorized"` (`running_actual:false`). **Remedy:** generate a
fresh Alpaca paper API key pair and enter it via **Settings → Broker connection → Test → Save → Reconnect**
(the new hands-off UI); the running bot will adopt it without a manual restart. (NB: during live-verify a
probe `PUT` briefly overwrote the stored creds; restored from backup
`~/.swingbot/backups/swingbot-data-20260616T194951Z.tar.gz` — same real key pair, hence the same 401.)

**✅ PORTFOLIO REBALANCING LAYER — COMPLETE & LIVE (2026-06-19).** Plan
`docs/superpowers/plans/2026-06-19-portfolio-rebalancing-implementation.md` executed end-to-end
(all 13 TDD tasks) via the Codex VM bridge (Codex implemented + committed 1–13, pushed to
`origin/core-engine` @ `14a2090`); clawd pulled, re-ran the gate, and completed the Docker
rebuild + live verification. Shipped off by default: `RebalanceSettings(enabled=False, mode="soft")`.

Shipped: pure `swingbot.rebalance` allocation/drift/trim logic with interval, volatility,
correlation, and fee guards; ProfileStore target/settings persistence; StateStore
`RebalanceState`; `rebalance_events` telemetry; orchestrator `sizing_equity` hook; supervisor soft
sizing and per-strategy soft cap; hard-mode reduce-only sells that shrink stored positions while
respecting portfolio and strategy kill switches; `/api/rebalance/*` settings/targets/status/run
endpoints; and a Settings-page Rebalance panel for allocations, targets, controls, and manual hard
run.

Safety state: disabled behavior remains unchanged when `enabled=false`; trims are sells only, never
entries; portfolio kill switch suppresses all trims; per-strategy kill switch excludes that
strategy; paper/live routing uses the existing broker sell path. Gates (re-run by clawd on the live
host): backend pytest **626 passed, 6 skipped**, ruff clean; frontend `npm run build` green.
**Live-verified on `:8000`:** container healthy; `GET /api/rebalance/settings` → `enabled:false`
(+ all defaults), `/status` and `/targets` correct; POST routes correctly auth-gated (`X-Token`);
dashboard served (HTTP 200). Feature is dormant until a user sets targets and flips `enabled`/`hard`.
**NEXT:** optional — exercise soft mode live (set targets + `enabled=true, mode=soft`) and watch the
allocation table populate; then opt into `hard` when comfortable.

**✅ AUTONOMOUS TRADING DASHBOARD — COMPLETE & LIVE (2026-06-19).** Plan
`docs/superpowers/plans/2026-06-19-autonomous-dashboard-implementation.md` executed end-to-end
(all 23 tasks ticked) via subagent-driven development + the Codex VM bridge (Codex implemented the
backend Python over the tmux bridge with SFTP file transfer; local subagents did core-engine +
frontend; each task individually reviewed clean). New read-only dashboard at **`http://localhost:8000/#/auto`**.

Shipped: `swingbot.autodash` package (config, backtest_runner with EMA-vs-Kronos `run_comparison`
reusing `core_engine.backtest`, GPU-preferring kronos_factory, read-only sqlite queries, cached
service, 6-route APIRouter mounted in `web.py`); core-engine `PositionStore` write-through; React
`AutoDashboard.jsx` page with 6 polling panels (chart, position, live stats, EMA-vs-Kronos backtest,
recent trades, decision journal) reusing lightweight-charts v5. Gates: **598 passed, 6 skipped**,
ruff clean, `npm run build` green. Playwright smoke PASS (`docs/autodash-smoke.png`) — all 6 panels
render with **live** core-engine data (journal streaming fresh decisions, real backtest numbers).

**Integration fixes found during live container verification (not in the original plan):**
- Dockerfile now packages `core-engine` into the swingbot image (autodash imports `core_engine.backtest`;
  was crash-looping `ModuleNotFoundError`).
- `docker-compose.yml` mounts the live `core_engine_data` named volume into swingbot (`CORE_ENGINE_DATA=/core-engine-data`)
  so the dashboard reads the **real running-bot** DBs (the live data lives in that volume, not host `~/.core-engine`).
- Backtest uses `backtest_timeframe="15m"` (the archive has BTC/USD at 15m/1d, not the live 5m) and the candle
  loader aliases epoch `time`→tz-aware `ts` Timestamp (the Kronos adapter requires it).
- **Kronos is gated to real CUDA only.** This Docker daemon lacks the `nvidia` runtime (runs `runc` via an
  untracked `docker-compose.override.yml`), so on CPU the comparison falls back to the deterministic EMA
  baseline (Kronos column mirrors EMA — documented). A real EMA-vs-Kronos comparison needs the nvidia Docker
  runtime fixed; bar-by-bar CPU Kronos is ~40 min/run, so a startup background prewarm + non-blocking pending
  placeholder is in place for the GPU path.

**Deployment state:** `swingbot` container rebuilt + live on `:8000` (serves the dashboard); `core-engine`
container rebuilt from repo-root context + swapped, PositionStore deployed, bot auto-resumed and trading.
Branch `feat/autodash-dashboard` (not yet merged to master at time of writing — see finish step).

**Follow-ups (optional):** (a) fix the host Docker `nvidia` runtime to enable a real GPU Kronos backtest;
(b) surface a "Kronos: GPU required" badge in `BacktestComparisonPanel` when degraded; (c) backfill BTC/USD
5m into the archive if a 5m backtest is wanted.

---

**Usage Agent drift finding (s6-guide "Start bot") RESOLVED at source (2026-06-17).** It was a
false positive: the Start/Stop control (`ControlBar.jsx`) is one toggle that renders "Stop bot"
while the bot is running, so the s6 probe — which runs against the live bot left running + desired —
never saw "Start bot" and flagged it missing. Fixed the detector, not the docs: `GUIDE_AFFORDANCES`
now declares the toggle as `"Start bot | Stop bot"` and `GuideReconciliationSession` accepts any
" | "-separated alternative as satisfying the affordance (`expectations.py`, `sessions.py`). Added
`test_s6_start_toggle_satisfied_by_stop_label`. Full suite **573 passed, 6 skipped**, ruff clean.
No live re-run of the nightly selftest was possible here (no swingbot container on this host, only
`xray-reality`); the next nightly run will reconcile s6 drift to 0. NB: this fix landed on the
`core-engine` branch (current checkout), not `master` — cherry-pick/merge to `master` when the
branches are reconciled.


**Visible Autonomous Entry — Phase 2 (persisted desire + paper auto-resume) is DONE (2026-06-13).**
Plan `plans/2026-06-13-visible-autonomous-entry-phase-2.md` executed end-to-end; all 6 tasks
committed on `master`. Full suite **412 passed, 6 skipped**; frontend builds; container rebuilt +
restarted clean. **Live acceptance verified on `:8000`:** pressing Start persists
`running_desired=true`; a full `docker compose build && up -d` with **no** Start press auto-resumed
the paper loop (`running_actual: true`, `startup_error: null`) — **success criterion 1**; an
explicit Stop then `restart` stayed stopped (`running_desired: false`, `running_actual: false`) —
**success criterion 2**. Bot left running + desired so future rebuilds auto-resume.

What shipped: new `RuntimeStateStore` (SQLite, persists only `running_desired`, defaults false — no
silent opt-in); supervisor gains `running_desired` property, `mark_desired()`, `startup_error`, and
`auto_start_if_desired()` (paper-only, failure-tolerant, never raises); `POST /api/control/start`
marks desire true only after a successful start, `POST /api/control/stop` marks false before
stopping, `halt`/`pause`/`resume`/shutdown never touch desire; new `GET /api/control/lifecycle`;
FastAPI lifespan calls `auto_start_if_desired()` after the poller and tolerates its failure;
`webmain` wires the store into the supervisor.

**Phase 2 review corrections integrated (2026-06-14):** applied the code-review-revised plan's
hardening to `master`. `RuntimeStateStore` now guards its shared `check_same_thread=False`
connection with an `RLock`. The supervisor gained serialized `request_start()` / `request_stop()`
that hold `_lifecycle_lock` across both the loop transition and desire persistence (so a concurrent
Stop can't be overwritten by an in-flight earlier Start, and an explicit Stop never auto-resumes on
restart); a successful explicit Start clears any stale `startup_error`; `auto_start_if_desired()` now
runs under `_lifecycle_lock` and captures runtime-state read failures. `POST /api/control/start|stop`
route through these serialized methods (with `hasattr` fallbacks for fakes). Suite **420 passed,
6 skipped**; ruff clean; frontend builds; container rebuilt + live-verified on `:8000`
(`running_actual:true`, `running_desired:true`, `startup_error:null`). +20 tests over the prior 412
(new concurrency/request-ordering coverage).

**Phase 2 code review (2026-06-14) found 4 remaining lifecycle *failure-path* defects** (handoff:
`plans/2026-06-14-phase2-lifecycle-code-review-handoff.md`, reviewed head `2f13bda`): (1) a failed
desire-write during Start leaves the loop running while the API returns failure; (2) Stop reports
`{"ok":true}` while the loop thread is still alive, and `running_actual` is mis-computed as
`running_flag and thread_alive` instead of the reviewed "thread is alive" contract; (3) a captured
runtime-state read failure makes `lifecycle_state()` itself raise; (4) a failed desire-clear during
Stop skips `stop()` entirely so the bot keeps trading. The happy paths and concurrent Start/Stop
ordering from `2f13bda` are sound — these are all partial-failure truthfulness gaps.

**Phase 2.1 lifecycle failure-path hardening is DONE (2026-06-15).** Plan
`plans/2026-06-14-visible-autonomous-entry-phase-2-1-lifecycle-hardening.md` executed end-to-end via
subagent-driven development (fresh implementer + spec-compliance + code-quality review per task);
7 commits on `master` (`0c5783e`, `51270d6`, `a27beba`, `feb567d`, `68e5c26`, `fc79cd0`, `ea0b1f3`).
All 4 review findings fixed:
- **F1 (Start):** `request_start()` now rolls back a loop it just started if desire-persistence fails
  (guarded by `was_running` so an already-running loop is never stopped), raises `DesirePersistError`,
  and clears stale `startup_error` only on full success.
- **F2 (Stop truthfulness):** new typed `LifecycleError`/`DesirePersistError`; `stop()` returns a bool
  (True=stopped, False=thread alive after join, retaining the thread ref so duplicate starts stay
  blocked); `running_actual` now = `thread_alive` per spec §3.1, with `running_flag` reported
  separately.
- **F3 (read failure):** `lifecycle_state()` tolerates an unreadable runtime store — reports
  `running_desired=null` + `running_desired_error`, never raises, keeps `startup_error` visible.
- **F4 (Stop skip):** `request_stop()` always attempts `stop()` even when clearing desire fails, and
  surfaces both failures in one `LifecycleError`.
- **Web:** `POST /api/control/start|stop` map `LifecycleError` → HTTP 500 (never `{"ok":true}` on a
  live thread); precondition `RuntimeError` on Start stays 400. `GET /api/control/lifecycle` passes
  the new fields through (pinned by test).

Full suite **431 passed, 6 skipped** (+11 over prior 420); ruff clean; frontend builds; container
rebuilt + live-verified on `:8000` (`running_actual:true`, `running_desired:true`,
`running_desired_error:null`, `startup_error:null` — auto-resume intact, new fields correct). Bot
left running + desired. Fault-injection findings (F1/F4/F5 timeouts) are covered by the test suite
(can't inject disk-full/stuck-thread into the live container).

**Visible Autonomous Entry — Phase 3 is DONE (2026-06-15).** Plan
`plans/2026-06-15-visible-autonomous-entry-phase-3.md` executed end-to-end in 8 tasks. Shipped:
stable decision/order contracts; durable 200-cycle telemetry and reliability; closed-bar
freshness; restart-safe pending orders and broker order lookup; broker-confirmed position/fill
transitions; durable trades/journal/metrics; one terminal record per strategy cycle; and separate
`/api/health/live`, `/api/health/ready`, and `/api/health/trading` contracts. Deterministic
integration coverage verifies restart/no-duplicate behavior, confirmed durable exits, broker error
truth, the exact latest-200 health window, and desired-but-not-running override.

Final gates: **521 passed, 6 skipped**; Phase 3 focused matrix **72 passed**; ruff clean; frontend
untouched. `python3 -m graphify update .` was attempted but this clean host has no `graphify`
module (and PyPI has no matching distribution); no tracked graph artifacts exist in this clone.
No live Alpaca/container acceptance is claimed; that remains Phase 6.

**Phase 3 independently reviewed & APPROVED (2026-06-16).** Codex's 8 commits (`ffa7377`→`2430de5`)
were fetched, fast-forwarded onto local `master`, and reviewed against spec §Phase 3 by a fresh
session: contracts clean (`types.py`); crash-safe order intent (pending row persisted with
`client_order_id` *before* the broker call; submit-exception leaves it for reconcile); broker-
confirmed promotion (buy→position only after `FILLED` + `get_position`; sell→trade only after broker
flat; idempotent via `client_order_id`); health read-models are local-only (no network). Re-ran on
this host: **521 passed, 6 skipped**, ruff clean. No blocking issues. Merged, not re-pushed (already
on origin).

**Phase 4 plan WRITTEN (2026-06-16) and pushed to `origin/master`.** Phase: EXECUTE.
Plan: `docs/superpowers/plans/2026-06-16-visible-autonomous-entry-phase-4.md` (8 tasks, TDD,
self-contained with a "Context for a cold code-gen agent" preamble — it IS the Codex handoff).
Both design forks resolved in the plan: (#4) implement the **opt-in `paper_probe`** (spec §3.4
recommended; preserves success criterion #10; default off, `SWINGBOT_ENABLE_PAPER_PROBE=1` to
enable); (#5) **managed-canvas server-side enforcement is OUT OF SCOPE** (spec makes it conditional
on a mode we are not adopting) — the reconciler's user-profile preservation is the safety guarantee.

Tasks: (1) EMA indicator; (2) `EmaTrendSignal` + registry; (3) managed definitions
(`btc_trend`/`eth_trend`/`paper_probe`) + labels; (4) probe signal + `ProbeMarkerStore` +
`probe_should_fire`; (5) `ProfileStore.get_meta/set_meta`; (6) versioned `reconcile_managed_profiles`
(backup-before-write, never deletes/overwrites user profiles); (7) supervisor `build()` reconcile
hook + `note_managed_decision` probe-complete-on-entry + webmain wiring; (8) regression gate
(`pytest -q`, `ruff check src/`, `npm run build`).

**Phase 4 code by Codex REVIEWED (2026-06-16).** Codex's 7 commits (`42f4b2e`→`06ef0d9`) were
fast-forwarded onto local `master` and reviewed against the plan/spec. Implementation matches the
plan line-for-line; **548 passed, 6 skipped**, ruff clean on review. **One Medium correctness gap
found & fixed:** the fire-once guarantee was not enforced in the live path — the probe wrote its
durable marker on entry but nothing consumed it (`probe_should_fire()` was dead code), so a completed
probe re-entered every flat cycle. **Fixed in `e0523ba`:** `tick_all` now gates the probe via
`_probe_suppressed()` (reuses `probe_should_fire`) — a completed, flat probe is suppressed with a new
terminal `DecisionCode.PROBE_COMPLETE`; a probe still holding a position keeps ticking so it can exit.
+3 regression tests in `test_supervisor_managed.py`; Phase-3 decision-code contract test updated for
the additive code. **551 passed, 6 skipped**, ruff clean; container rebuilt + live-verified on `:8000`
(`running_actual:true`, `startup_error:null`, ready; reconciler seeded managed strategies → 7 armed,
probe correctly absent with `SWINGBOT_ENABLE_PAPER_PROBE` unset). Minor (deferred, doc-note only):
the reconciler overwrites a *pre-existing user profile that shares a managed name* (backup mitigates).

**Phase 4 DONE & reviewed; fix `e0523ba` + docs `9f1cb9c` pushed to `origin/master` (2026-06-16).**

**Visible Autonomous Entry — Phase 5 is DONE (2026-06-16).** Plan
`docs/superpowers/plans/2026-06-16-visible-autonomous-entry-phase-5.md` executed task-by-task on
`master` in 7 implementation commits (`b817a74`→`85b6d2e`) plus this roadmap/plan tracking update.
Shipped: `managed_meta()` and `kind`/`label` on `/api/strategies`; `/api/state` now exposes
`pending_orders`, per-strategy `kind`/`label`/`probe_complete`, and open-position
`mark_price`/`mark_ts`/`unrealized` from the local market cache; the Dashboard polls
`/api/health/trading`; lifecycle, pending-order, reliability, realized P&L, last-decision, probe-state,
unrealized P&L, and durable trade-marker surfaces are visible; usage-agent health remains isolated on
the Health tab; operational controls remain available.

Plan adjustments documented inline: `ruff` is available as `.venv/bin/ruff`; `Regime`/`OrderSide`/
`PendingOrder` are in `swingbot.types`; supervisor market data is `self.market`; reliability fields
are `ratio`/`completed_cycles`/`cycle_completion_ratio`/`critical_stage_floor`/`window_started_at`/
`window_completed_at`; and `ChartPanel` needed a small mini-marker opt-in because mini charts
previously disabled trade markers with no settings UI.

Final gates: **556 passed, 6 skipped**, ruff clean via `.venv/bin/ruff check src/`, frontend build
green. Docker image rebuilt. Default `docker compose up -d swingbot` failed on this host because the
daemon lacks the compose file's hardcoded `runtime: nvidia`; the service was started for smoke with a
temporary local override `runtime: runc`. Live smoke on `:8000`: `/api/state` returned
`pending_orders: []` (no armed strategies in this local data dir); `/api/health/trading` returned
`status: inactive`, lifecycle with `running_desired:false`, `running_actual:false`,
`startup_error:null`, empty decisions, and reliability counts/window fields.

**Phase 5 independently REVIEWED & APPROVED (2026-06-16).** Codex's 8 commits (`b817a74`→`8740471`)
were fetched, fast-forwarded onto local `master`, and reviewed against the plan/spec by a fresh
session. Implementation matches the plan line-for-line; the three flagged deviations are all handled
correctly: (1) `self.market` (not `self._market`); (2) `ReliabilityPanel.jsx` rewritten to the real
telemetry field names (`window_started_at`/`window_completed_at`/`cycle_completion_ratio`/
`critical_stage_floor`/`stages.*.ratio`/`ok`/`failed`/`skipped`/`samples`) — verified against
`TelemetryStore.reliability()` in `telemetry.py:144`; (3) `ChartPanel` `showMarkersInMini` opt-in so
per-strategy durable entry/exit markers render in the mini chart. Backend `status()` enrichment is
local-only (no broker/network calls), all in `try/except` returning nulls on failure. **No blocking
issues; no corrections needed.** Re-ran the gate on this host: **556 passed, 6 skipped**, ruff clean,
frontend build green — matches Codex's reported gate exactly. **Live-deployed on this host:** image
rebuilt + container recreated with the `runtime: runc` override (host daemon lacks `runtime: nvidia`);
`:8000` now serves Phase 5 — `/api/state` carries `pending_orders` + per-strategy `kind`/`label`/
`probe_complete`, `/api/health/trading` returns `status:active`, `running_desired:true`/
`running_actual:true`, `startup_error:null`, and the full reliability key set. Already on `origin`; not
re-pushed.

**Phase 6 Tasks 1–6 DONE (2026-06-16), pushed to `origin/master` (`bc268f0`→`9310e81`).** Plan:
`docs/superpowers/plans/2026-06-16-visible-autonomous-entry-phase-6.md`. Shipped: the deterministic,
Alpaca-free acceptance harness `tests/test_phase6_acceptance.py` (4 tests — auto-resume without Start;
probe fill→broker-confirmed position→durable completion marker + cycle record; restart does not
re-enter a completed flat probe; broker failure stays truthful with no false-flat/duplicate);
`scripts/backup-data-dir.sh` (timestamped tarball, real-run verified); and the operator runbook
`docs/PHASE6_LIVE_ACCEPTANCE.md` (exact commands + a concrete pass check per spec step 1–7).

**Real defect found & fixed (issue #2, closed).** Task 4 exposed a genuine `src/` gap exactly as the
plan anticipated: `tick_all` fetched the broker account *outside* the per-strategy try/except, so a
total broker/credential/network outage raised straight out of the cycle (no telemetry, no truthful
health). Fixed via TDD as its own focused task in `1553eba`: the account fetch is now wrapped — on
failure the daily-counter reset is skipped (never fabricate equity), every strategy's cycle is recorded
as a failed broker cycle (no entries, the open position is preserved rather than read as flat), and the
last-known-good summary is retained. Regression-guarded by
`tests/test_phase3_integration.py::test_account_fetch_failure_records_failed_cycle_without_clearing_or_duplicating`.
Gate: **561 passed, 6 skipped**, ruff clean; container rebuilt + live-verified on `:8000` (readiness
answers, 7 armed strategies).

**✅ VISIBLE AUTONOMOUS ENTRY SUB-PROJECT COMPLETE (2026-06-17).** Phase 6 Tasks 7–8 executed against
the live container with **real Alpaca paper credentials** (already configured in `~/.swingbot/credentials.json`).
Acceptance evidence recorded in `docs/PHASE6_LIVE_ACCEPTANCE.md`. **Overall verdict: PASS** (with one
deferred sub-step + one real defect found & fixed). Summary:
- **Steps 1–4 ✅ PASS:** data-dir backup (55 MB tarball); managed/probe config armed (`btc_trend`,
  `eth_trend`=strategy, `paper_probe`=probe); auto-resume on rebuild with **no** Start press
  (`running_desired/actual:true`, `startup_error:null`); truthful `/api/health/trading` (status active,
  recent closed bar, per-strategy decision code+reason, full reliability window).
- **Step 5 ⚠️ PARTIAL:** probe correctly **decided + submitted** a market buy on the first fresh 15m bar;
  first attempt **rejected** for insufficient cash → handled truthfully (no false position); after freeing
  cash (liquidated a stale 1.47 BTC paper position) the resubmit was **broker-accepted** and the bot
  correctly **did not fabricate** a position while unconfirmed. **Actual fill DEFERRED** — a documented
  Alpaca **paper-side** bug: crypto BUY orders stall in `pending_new` for hours/indefinitely (verified
  raw-REST + SDK + marketable-limit all stall identically; SELLs fill instantly; account unrestricted;
  Jun 14/15 buys took 8–57 h; matches Alpaca community forum reports). The `FILLED→position→durable-marker`
  promotion remains covered by the deterministic harness `tests/test_phase6_acceptance.py`.
- **Step 6 ✅ PASS:** restart re-adopted the in-flight pending order (no duplicate on Alpaca).
- **Step 7 ✅ PASS + REAL DEFECT FOUND & FIXED:** credential-removal → all endpoints HTTP 200 (no 500
  storm), `/api/health/ready` not-ready with "missing credentials", lifecycle truthful
  (`running_desired:true`, `running_actual:false`, exact `startup_error`), no false-flat, no orders. On
  restore, auto-start crashed with `"unknown Alpaca order status: pending_new"` — the `OrderStatus` enum
  was missing transient Alpaca statuses, so the live `pending_new` probe order took the bot down on
  reconcile. **Fixed via TDD (commit `341d78f`):** full Alpaca order lifecycle added to `OrderStatus`
  (decision logic unchanged — only REJECTED/CANCELED/EXPIRED are terminal failures; all other non-FILLED
  statuses are still-pending). Bot now auto-resumes cleanly past a `pending_new`/`pending_cancel` order.
- **Close-out:** full gate **571 passed, 6 skipped**, `ruff` clean; container rebuilt + live-verified;
  probe returned to default OFF (`SWINGBOT_ENABLE_PAPER_PROBE` unset); bot left running + desired with
  managed (`btc_trend`/`eth_trend`) + user strategies.

**NEXT ACTION — none required for this sub-project.** Optional follow-ups: (a) to capture the one deferred
live probe fill, re-enable the probe once Alpaca's paper crypto buy-fill bug clears (set
`SWINGBOT_ENABLE_PAPER_PROBE=1` via a temporary `docker-compose.override.yml`, watch a 15m boundary);
(b) consider sizing the probe off *available cash* rather than equity (`max_position_frac`) so it can't be
rejected when equity is deployed elsewhere — observed during this run, low priority.

**Codex handoff decision (resolved this session):** do NOT write a separate `PHASE4_CODEX_HANDOFF.md`.
The Phase 3 handoff (`docs/PHASE3_CODEX_HANDOFF.md`, 210 lines) overlapped heavily with the 773-line
plan — its only additive value over a good plan is cold-agent orientation (build-on-this vs gaps),
verbatim spec excerpts, and house rules (venv `.venv/bin/python`, TDD, "don't touch unrelated
uncommitted FVG/presets work"). So author the Phase 4 **plan to be self-contained for a cold agent**
— add a short "## Context for a cold code-gen agent" preamble (current-code state, component
boundaries, env/house rules, success criteria) at its top. That one plan file IS the Codex handoff;
paste it whole. The ready-to-paste Codex prompt lives in the session that resolved this (re-derivable:
"You are implementing Phase 4 from this plan verbatim, TDD task-by-task, tick each `- [ ]` and commit
per task; do not touch files outside the plan's File Structure; run `.venv/bin/python -m pytest -q`
and `ruff check src/` before each commit").

---

**Sub-project E is DONE and live-verified** (full gate green, 6/6 usage sessions pass, 0 drift;
Health tab confirmed live). The platform roadmap A→E is complete. Suggested next steps:

1. ~~Schedule the nightly usage-agent run~~ ✅ **DONE (2026-06-13).** A **system cron job**
   runs `scripts/nightly-selftest.sh` daily at **03:00 local** (`crontab -l` to view; logs to
   `~/.swingbot/selftest-cron.log`). It drives all six sessions, reconciles against the
   Guide/specs, and files new drift into the Brain inbox. Runs `--no-llm` (deterministic gate +
   sessions + drift, no Ollama dependency); drop that flag in the wrapper to also get LLM
   improvement proposals. NB: `/schedule` (cloud routines) was **not** used — cloud agents can't
   reach the local `:8000` container; this is a local cron job by design.
2. **Triage drift on the Health tab** (`http://localhost:8000/#/health`) whenever a run goes
   non-green or files findings: each `doc_fix`/`ui_fix` card is recommend-only — fix manually,
   then Dismiss.
3. **All work is pushed** — A–E are all committed **and pushed to `origin/master`** (B2, D, E
   pushed 2026-06-13, commit `e0229fb`).

**Housekeeping:** The brain's default `brain_ollama_url` (`localhost:11434`) does not work inside
Docker — use `http://172.17.0.1:11434` (already set on running instance). See
`docs/SUBPROJECT_C_FINDINGS.md`. The selftest/usage-agent now writes proposals to
`brain_proposals.json` (the file the UI reads); artifacts live under `~/.swingbot/agent/`.

---

## Status board

| # | Sub-project / phase | Status | Spec | Plan | Notes |
|---|---------------------|--------|------|------|-------|
| A | UI cleanup + multi-position dashboard | ✅ **DONE** (Playwright-verified) | roadmap §A | `plans/2026-06-02-subproject-a-ui-cleanup-dashboard.md` (all boxes ✓) | committed **and pushed to origin** |
| B1 | Historical data archive | ✅ **DONE** | `specs/2026-06-02-subproject-b-data-archive-design.md` | `plans/2026-06-02-subproject-b-phase1-data-archive.md` (all boxes ✓) | **Pushed to origin.** Use Coinbase for deep history (Binance 451-blocked, Kraken caps 720) |
| B2 | Auto-strategy discovery | ✅ **DONE** | `specs/2026-06-03-subproject-b-phase2-discovery-design.md` | `plans/2026-06-03-subproject-b-phase2-discovery.md` (10 tasks, all boxes ✓) | sweep→rank→"eligible now"→`/api/discovery`→Discover panel; committed locally (not pushed) |
| C | Ollama decision brain | ✅ **DONE** (live-verified) | `specs/2026-06-04-subproject-c-decision-brain-design.md` | `plans/2026-06-04-subproject-c-decision-brain.md` (11 tasks, all boxes ✓) | `decision/` pkg → qwen2.5; recommend-only default + autonomous toggle; Brain page. **Pushed to origin** |
| D | Self-test gate + LLM proposals | ✅ **DONE** | `specs/2026-06-03-subproject-d-self-test-gate-design.md` | `plans/2026-06-03-subproject-d-self-test-gate.md` (8 tasks, all ✓) | `selftest/` pkg; `python -m swingbot.selftest`; pytest+ruff+npm gate + Playwright probe → SELFTEST_REPORT.md + DEVLOG; green→qwen3.5:9b proposals into C's inbox; 328 passed |
| E | Usage Agent (usage sessions + drift detection) | ✅ **DONE** (live-verified) | `specs/2026-06-12-subproject-e-usage-agent-design.md` | `plans/2026-06-12-subproject-e-usage-agent.md` (10 tasks, all boxes ✓) | S1–S6 sessions (live `:8000` read-only + ephemeral `:8001` mutating); drift → `doc_fix`/`ui_fix` in brain inbox; Health tab + `/api/agent/*`; hash routing; 6/6 sessions green, 0 drift. **Pushed to origin** |

Paths are under `docs/superpowers/`. Roadmap spec: `docs/superpowers/specs/2026-06-02-platform-improvement-roadmap-design.md`.

---

## How to resume (mechanics)

1. **Read this file → NEXT ACTION.**
2. **Check memory:** `MEMORY.md` (auto-loaded) lists per-topic memory files; read the ones the NEXT ACTION touches.
   Key files: `platform-improvement-roadmap`, `subproject-a-ui-cleanup-status`, `archive-data-source-findings`.
3. **If NEXT ACTION points to an existing plan** (a `*.md` in `docs/superpowers/plans/`):
   the work is task-by-task with `- [ ]` / `- [x]` checkboxes. Find the first unchecked task and continue from there:
   ```bash
   grep -n "^- \[ \] \*\*Step" docs/superpowers/plans/<the-plan>.md | head -1   # first unfinished step
   grep -nE "^## Task|✅ DONE" docs/superpowers/plans/<the-plan>.md              # per-task status
   ```
   Then load `superpowers:executing-plans` and continue. Tick checkboxes + commit as you finish each task.
4. **If NEXT ACTION is "write a spec"**: load `superpowers:brainstorming` (design first), then `superpowers:writing-plans`.
5. **Before claiming done:** run `.venv/bin/python -m pytest -q` (expect `288 passed, 5 skipped` as of 2026-06-03),
   and for UI work `cd frontend && npm run build`.

## Environment notes (carry forward)

- Python venv: **`.venv/bin/python`** (plain `python`/`pytest` are not on PATH).
- graphify CLI is **`python3 -m graphify`** (not on PATH); run `python3 -m graphify update .` after code changes.
- `~/.swingbot/candles.db` is **read-only in the sandbox** — for backfills point `SWINGBOT_DATA_DIR=/tmp/...`.
- The app runs in Docker (`crypto-swing-bot-swingbot-1` on :8000). Rebuild/restart = `docker compose build swingbot && docker compose up -d swingbot`; this **interrupts the live paper-trading bot**, so get user consent.
- Working on `master` is user-approved for this project; scope each `git add` to your task's files (the tree carries unrelated uncommitted FVG/presets/graphify work that must stay untouched).
