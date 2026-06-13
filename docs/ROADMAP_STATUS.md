# Roadmap Status — crypto-swing-bot

> **Single source of truth for "where are we / what's next."** A new session should read this
> file first for any platform-roadmap work, then jump to the **NEXT ACTION** below.
> Keep this file updated at the end of every work session (it is the cross-session memory anchor).

**Last updated:** 2026-06-13

---

## ▶ NEXT ACTION

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
