# Roadmap Status — crypto-swing-bot

> **Single source of truth for "where are we / what's next."** A new session should read this
> file first for any platform-roadmap work, then jump to the **NEXT ACTION** below.
> Keep this file updated at the end of every work session (it is the cross-session memory anchor).

**Last updated:** 2026-06-14

---

## ▶ NEXT ACTION

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

**NEXT ACTION — write the Phase 3 plan.** The lifecycle truth layer is now hardened, so Phase 3's
`/api/health/trading` (spec §3.3: "a desired-but-not-running loop is immediately unhealthy") can be
built on a `running_actual`/`running_desired` surface that cannot lie. Phase 3 scope: durable
cycle/decision telemetry, order/pending/fill state with broker-confirmed positions, persistent
trades, and the three `/api/health/*` contracts (spec §5 Phase 3). Load
`superpowers:brainstorming` only if design forks remain, else `superpowers:writing-plans`. Spec
basis: `specs/2026-06-13-visible-autonomous-entry-design-reviewed.md`.

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
