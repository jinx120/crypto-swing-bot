# Sub-project E — Usage Agent — Design

**Date:** 2026-06-12
**Status:** Proposed (awaiting user review). Depends on A–D, all DONE.
**Roadmap ref:** `docs/superpowers/specs/2026-06-02-platform-improvement-roadmap-design.md`
(extends §D's self-test gate into a usage-driven feedback loop).

## Goal

Close the gap between "the routes load without errors" (Sub-project D) and "the platform
works the way the docs say it should." The Usage Agent drives the app through scripted
**usage sessions** that mirror real intended workflows, reconciles observed behavior against
documented intent (the in-app Guide, the specs), and turns each divergence into a structured
**drift finding** that lands in the existing proposal inbox, the DEVLOG, and a new UI panel —
so the platform continuously tests and documents its own gaps without manual click-throughs.

Everything stays recommend-only. The agent never applies trading or settings changes; the
existing guardrail model (`decision/guardrails.py`) is unchanged.

## Review-pass findings that motivate this design (2026-06-12 audit)

1. **D's probe has never tested 2 of 3 pages.** The frontend has no URL routing — tabs are
   `useState` in `App.jsx`. The probe's routes `/discover` and `/brain` 404 against
   `StaticFiles` (live `SELFTEST_REPORT.md` shows exactly these 404 warns), so only the
   Dashboard has ever been rendered by the gate, and the run still reports GREEN.
2. **The in-app Guide is stale.** It instructs "Set active on that profile" and says "the bot
   only ever runs the *active* profile" — the active-profile model was replaced by multi-arm
   (`StrategyManager` has Arm/Disarm; no "Set active" button exists). A user following the
   Guide dead-ends. The Guide also predates Discover and Brain entirely.
3. **`ui_fix` proposals dead-end on Apply.** They are always guardrail-"approved", so the
   Brain page shows an Apply button, but `DecisionBrain._dispatch` has no `ui_fix` branch —
   clicking Apply raises `ValueError` into the issues feed. Apply can never succeed.
4. **Selftest-sourced `tune` proposals bypass the re-backtest guardrail.**
   `selftest/llm.py` calls `evaluate(p, {}, [], backtest_ok=lambda *_: True)`, so a tune shows
   "approved" without the backtest check C's spec requires ("the LLM cannot silently degrade
   a strategy"). Recommend-only saves us, but the badge is misleading.
5. **`tune`/`arm` apply always rebuilds a `disc-*` profile with style "swing"** — a tune
   targeting a manually-named strategy silently writes a different profile than the one armed.
6. **Stale docs elsewhere:** `HANDOVER.md` still says the FVG signal is a stub (real since
   `e852ea7`) and targets TRX/USD (removed in A). `ROADMAP_STATUS.md` "Last updated" lags the
   Jun 8 session. DEVLOG says "newest first" but selftest one-liners append at the bottom.
7. **Blocking dialogs:** Discover uses `alert()` on arm; ControlBar/StrategyCard use
   `window.confirm` — hostile to headless automation and a UX rough edge.
8. **Housekeeping:** Sub-project D's plan file was never committed (untracked); D's commits
   are unpushed; nothing actually schedules the selftest yet.

Items 2–5 are exactly the class of issue the Usage Agent must detect (and several are fixed
directly by this sub-project's plan as prerequisites or demonstrations of the loop).

## Decisions

- **Sessions are deterministic Python scripts, not LLM-driven.** Replayable, debuggable,
  offline-testable. The LLM only analyzes results afterwards (green-gated, `--no-llm`
  skippable), same as D.
- **Two-tier safety model (trust boundary, called out explicitly):**
  - **Read-only sessions** (navigation, rendering, data display) run against the **live**
    `:8000` container.
  - **Mutating sessions** (arm/disarm, watchlist edits, settings changes, proposal
    apply/dismiss) run against an **ephemeral instance**: `uvicorn` launched from the host
    `.venv` on `:8001` with a throwaway `SWINGBOT_DATA_DIR` seeded from fixtures, torn down
    after. **The live container's state is never mutated by the agent.** No change to
    `decision/guardrails.py`; `autonomous_mode` never extends to agent findings.
- **Hash-based routing added to the frontend** (`#/dashboard`, `#/strategy`, `#/discover`,
  `#/brain`, `#/settings`, `#/guide`). Minimal `App.jsx` change (read hash → `setTab`, write
  hash on tab click). This fixes D's broken probe routes, makes every tab deep-linkable, and
  needs no server-side SPA fallback. D's `ROUTES` switch to hash URLs.
- **Expectations catalog** — `src/swingbot/selftest/expectations.py` + per-session expected
  outcomes, each carrying a **doc source reference** (file + section, e.g.
  `frontend/src/guide.md §"The 5 steps"`). A drift finding is "expected (per <doc ref>) vs
  observed", machine-distinguishable from a plain bug.
- **New proposal action `doc_fix`** (target = `{doc, section, expected, observed, suggestion}`)
  joining `ui_fix` as always-recommend-only. Drift findings become `doc_fix` (when the docs
  are wrong) or `ui_fix` (when the code is wrong) proposals in the **same `ProposalStore`
  inbox** as C and D, `source="usage-agent"`.
- **Fix the Apply dead-end:** the Brain/Health UI hides Apply for non-executable actions
  (`ui_fix`, `doc_fix`); Dismiss remains. `_dispatch` rejects them with a clear message
  instead of `ValueError("unknown action")`.
- **Artifacts live under `DATA_DIR`** (`~/.swingbot/agent/` → `/data/agent` in the container):
  `runs.json` (ring of recent run summaries + session traces) and `screenshots/`. The
  containerized app can therefore serve them — `docs/` on the host cannot be seen by the
  container.
- **Doc feedback loop:** after each run the agent inserts a dated entry **at the top** of
  `docs/DEVLOG.md` (restoring newest-first; D's one-liner writer is fixed to do the same) and,
  when there are actionable findings, rewrites the `ROADMAP_STATUS.md` **NEXT ACTION** block to
  point at them — so the next session (human or agent) picks them up automatically.

## Architecture

Extends the existing `selftest/` package (one gate, one CLI) rather than a new top-level package:

```
selftest/
  sessions.py       # UsageSession protocol + the scripted sessions (S1–S6)
  expectations.py   # expected outcomes + doc source references
  ephemeral.py      # EphemeralApp: launch/seed/teardown uvicorn on :8001, temp DATA_DIR
  drift.py          # reconcile SessionTrace vs expectations -> DriftFinding -> Proposal
  agentstore.py     # runs.json ring writer/reader (DATA_DIR/agent/)
  runner.py         # (extended) pipeline + gate
  uiprobe.py        # (extended) hash routes; session step driver helpers
  llm.py            # (extended) drift-aware analysis prompt; proper guardrail ctx for tune
```

### Data shapes

- `SessionStep{ desc, action (goto|click|fill|assert|api), ok, detail, screenshot_path }`
- `SessionTrace{ session, ok, steps: list[SessionStep], console_events, network_events,
  started_at, duration_s }`
- `DriftFinding{ session, step, expected, observed, doc_ref, kind (drift|bug),
  suggestion, screenshot_path }`
- `AgentRun{ ts, green, checks, route_findings, traces: list[SessionTrace],
  drift: list[DriftFinding], proposal_ids }` — persisted to `runs.json` (cap ~20 runs).

### Usage sessions v1 (sourced from Guide + specs)

| # | Session | Tier | Expectation source |
|---|---------|------|--------------------|
| S1 | Tab navigation: every tab renders its key element, zero console errors | live | roadmap spec §A, App tabs |
| S2 | Guided strategy flow: universe pick → preset → backtest → arm → appears in dashboard grid & `/api/state` | ephemeral | Guide "5 steps", A spec §Strategy page |
| S3 | Watchlist round-trip: add/remove → dashboard watchlist row reflects | ephemeral | A spec §Dashboard grid |
| S4 | Portfolio settings persistence: change `max_concurrent` → reload → persisted & served | ephemeral | C spec §Configuration |
| S5 | Brain inbox flow: seed proposals into the store → apply approved arm → strategy armed; dismiss → leaves pending; blocked shows reason; `ui_fix` shows no Apply | ephemeral | C spec §Frontend, D spec §New action type |
| S6 | Guide reconciliation: every UI affordance the Guide names exists in the DOM (e.g. "Set active") | live | `frontend/src/guide.md` |

Sessions use the same injectable-page pattern as `uiprobe.py` so unit tests run offline with
fake pages; only the real run launches Chromium.

### Pipeline (extended `runner.run()`)

1. Deterministic checks (unchanged: pytest, ruff, npm-build).
2. Route probe (now hash routes — actually renders all pages).
3. **Usage sessions**: read-only tier against live; mutating tier against `EphemeralApp`.
   - Infrastructure failure (ephemeral app won't start, browser crash) → **RED**, exit 1.
   - Assertion divergence → **drift findings**, run stays GREEN (drift is the product,
     not a gate failure).
4. Gate decision as today (checks ok + no fatal UI findings + session infra ok).
5. **GREEN only:** drift reconciliation → `doc_fix`/`ui_fix` proposals into `ProposalStore`
   (`source="usage-agent"`, guardrail-stamped, recommend-only) + optional LLM analysis pass
   for suggestions/rationale (`--no-llm` skips; Ollama down → findings still stored with
   templated rationale).
6. Report: `SELFTEST_REPORT.md` gains sessions + drift sections; `runs.json` written;
   DEVLOG entry inserted at top; `ROADMAP_STATUS.md` NEXT ACTION updated when findings exist;
   Discord ping `usage_drift` when new drift found.

CLI: `python -m swingbot.selftest` runs everything; flags `--no-sessions`, `--no-llm`,
`--base-url`, `--ephemeral-port`. Exit codes unchanged (0 green / 1 red / 2 crash).
Scheduling stays external (`/schedule` or `/loop`), nightly suggested.

### Endpoints (`web.py`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/agent/runs` | recent `AgentRun` summaries (from `DATA_DIR/agent/runs.json`) |
| GET | `/api/agent/runs/latest` | last run with full traces + drift |
| GET | `/api/agent/artifacts/{name}` | serve screenshots from `DATA_DIR/agent/screenshots` (path-safe) |

Read-only; no token needed (consistent with other GET endpoints). Proposals continue to flow
through the existing `/api/brain/*` endpoints.

### UI home: new **Health** tab (justification)

A new tab rather than a Brain section: the Brain page is already a dense console (inbox,
toggles, config, webhook, issues), and the agent surface is meaty — run status, per-session
step traces, screenshots, expected-vs-observed cards. Mixing them buries both. The split
keeps a clean mental model: **Brain = what the platform wants to change about trading;
Health = whether the platform works as documented.** Findings remain one inbox: drift cards
on Health are the same `ProposalStore` items (filtered `source="usage-agent"`), wired to the
existing apply/dismiss endpoints, and still visible on Brain like every other proposal.

Health tab contents:
- Last run banner: GREEN/RED, timestamp, duration, checks summary, sessions passed/total.
- Session list: each session expandable to its step trace with per-step ✓/✗ and screenshots.
- Drift cards: expected vs observed, doc reference, suggestion, screenshot link;
  Dismiss (and Apply only where an executable action exists).
- Run history sparkline/list from `runs.json`.

### Targeted fixes folded into this sub-project (prerequisites / loop demonstrations)

1. Hash routing in `App.jsx` + D's `ROUTES` updated (prerequisite for sessions).
2. `ui_fix`/`doc_fix` Apply dead-end fixed (UI + `_dispatch` message).
3. `selftest/llm.py` guardrail call gets real context + real `backtest_ok` (or stamps
   non-executable actions only) so "approved" stops being misleading.
4. DEVLOG writers insert at top (newest-first restored).
5. Replace `alert()` on Discover arm with inline toast/banner (headless-automation friendly;
   `window.confirm` on destructive controls stays).
6. Rewrite the stale Guide sections (arm/disarm model, add Discover/Brain/Health sections) —
   S6 then guards against future Guide rot.
7. Commit the untracked Sub-project D plan file; push policy decision left to the user.

## Error handling

Same defensive contract as D: every external interaction (subprocess, browser, ephemeral app,
Ollama, file IO) is wrapped; failures become findings or issues, never crashes. A runner crash
still writes a RED report and pings Discord (existing top-level try/except). The ephemeral app
is torn down in `finally`; leaked processes are killed by port+pid tracking on next run.

## Testing (offline, deterministic)

- `sessions.py`: fake page + fake API client per session — assert step sequences, that
  divergences produce the right `DriftFinding`s, and traces serialize.
- `expectations.py`: catalog loads; every doc_ref points at an existing file.
- `ephemeral.py`: fake `Popen`/socket — start/seed/teardown lifecycle, port-busy handling.
- `drift.py`: trace+expectation table-tests → finding kinds, proposal mapping
  (`doc_fix` vs `ui_fix`), dedupe via existing proposal id hash.
- `agentstore.py`: ring cap, corrupt-file tolerance, round-trip.
- `runner.py`: gate table extended — session infra failure → exit 1; drift-only → exit 0 +
  proposals stored; `--no-sessions` skips cleanly.
- Endpoints: shapes + artifact path traversal rejected.
- Frontend: `npm run build` green; hash routing covered by S1 itself at runtime.
- Suite gate: `.venv/bin/python -m pytest -q` green (`328 passed` + new tests),
  `cd frontend && npm run build`.

## Out of scope (YAGNI)

- LLM-authored/exploratory sessions (scripted only in v1; the catalog is the extension point).
- Auto-applying doc edits or code fixes — everything is recommend-only.
- Testing real-money flows, graduation, or live-mode switching.
- Multi-browser; report retention beyond `runs.json` ring + DEVLOG lines.
- In-app scheduling — stays external via `/schedule`.

## Sequencing within the plan (sketch)

1. Hash routing + D `ROUTES` fix (unblocks everything; probe finally sees all pages).
2. `agentstore.py` + `AgentRun`/trace/finding types.
3. `expectations.py` catalog (S1–S6 expectations with doc refs).
4. `ephemeral.py`.
5. `sessions.py` S1, S6 (read-only tier) → wire into runner.
6. `sessions.py` S2–S5 (mutating tier).
7. `drift.py` + `doc_fix` action + guardrails/`_dispatch`/Brain-UI dead-end fixes + llm.py ctx fix.
8. Endpoints + Health tab.
9. Report/DEVLOG/ROADMAP writers + Discord event.
10. Guide rewrite + alert() removal; full-loop live verification; docs + ROADMAP update.
