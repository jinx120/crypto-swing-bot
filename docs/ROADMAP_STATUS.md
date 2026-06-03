# Roadmap Status — crypto-swing-bot

> **Single source of truth for "where are we / what's next."** A new session should read this
> file first for any platform-roadmap work, then jump to the **NEXT ACTION** below.
> Keep this file updated at the end of every work session (it is the cross-session memory anchor).

**Last updated:** 2026-06-03

---

## ▶ NEXT ACTION

**Execute the Sub-project B **Phase 2** plan (Auto-Strategy Discovery).**

- Spec ✅ written: `docs/superpowers/specs/2026-06-03-subproject-b-phase2-discovery-design.md`.
- Plan ✅ written & ready to execute: `docs/superpowers/plans/2026-06-03-subproject-b-phase2-discovery.md`
  (10 TDD tasks). Continue from the **first unchecked `- [ ]` task** with `superpowers:executing-plans`
  (or `superpowers:subagent-driven-development`); tick checkboxes and commit per task.
  ```bash
  grep -n "^- \[ \] \*\*Step" docs/superpowers/plans/2026-06-03-subproject-b-phase2-discovery.md | head -1
  ```
- Key design calls baked into the plan: full-universe × archetypes sweep over the deep archive;
  `eligible_now = good_history + regime OK` (`fires_now` non-gating); coverage-derived scenario windows;
  background daemon sweep + `discovery.json` cache; one-click arm = save + arm (paper, `live_eligible` is
  a non-gating status marker today). Builds on B1's deep archive + A's `/api/universe`+`/api/watchlist`.
- After the plan's Task 10 lands, NEXT ACTION becomes **Sub-project C (Ollama decision brain)** — write its
  spec via `superpowers:brainstorming`.

**Housekeeping:** Sub-projects A and B1 are committed **and pushed to `origin/master`**. B2 spec + plan are
committed locally on `master` (not yet pushed) as of 2026-06-03.

---

## Status board

| # | Sub-project / phase | Status | Spec | Plan | Notes |
|---|---------------------|--------|------|------|-------|
| A | UI cleanup + multi-position dashboard | ✅ **DONE** (Playwright-verified) | roadmap §A | `plans/2026-06-02-subproject-a-ui-cleanup-dashboard.md` (all boxes ✓) | committed **and pushed to origin** |
| B1 | Historical data archive | ✅ **DONE** | `specs/2026-06-02-subproject-b-data-archive-design.md` | `plans/2026-06-02-subproject-b-phase1-data-archive.md` (all boxes ✓) | **Pushed to origin.** Use Coinbase for deep history (Binance 451-blocked, Kraken caps 720) |
| B2 | Auto-strategy discovery | 🟡 **SPEC+PLAN READY** ← execute next | `specs/2026-06-03-subproject-b-phase2-discovery-design.md` | `plans/2026-06-03-subproject-b-phase2-discovery.md` (10 tasks, all boxes ⬜) | sweep→rank→"eligible now"→`/api/discovery`→Discover panel; depends on A + B1 |
| C | Ollama decision brain | ⬜ outline only | roadmap §C | — | `decision` module → local qwen2.5; recommend-only by default. Depends on B |
| D | Self-test gate + LLM proposals | ⬜ outline only | roadmap §D | — | pytest+build+Playwright+ruff health → devlog; depends on A's smoke |

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
5. **Before claiming done:** run `.venv/bin/python -m pytest -q` (expect `235 passed, 5 skipped` as of 2026-06-03),
   and for UI work `cd frontend && npm run build`.

## Environment notes (carry forward)

- Python venv: **`.venv/bin/python`** (plain `python`/`pytest` are not on PATH).
- graphify CLI is **`python3 -m graphify`** (not on PATH); run `python3 -m graphify update .` after code changes.
- `~/.swingbot/candles.db` is **read-only in the sandbox** — for backfills point `SWINGBOT_DATA_DIR=/tmp/...`.
- The app runs in Docker (`crypto-swing-bot-swingbot-1` on :8000). Rebuild/restart = `docker compose build swingbot && docker compose up -d swingbot`; this **interrupts the live paper-trading bot**, so get user consent.
- Working on `master` is user-approved for this project; scope each `git add` to your task's files (the tree carries unrelated uncommitted FVG/presets/graphify work that must stay untouched).
