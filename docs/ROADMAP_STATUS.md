# Roadmap Status — crypto-swing-bot

> **Single source of truth for "where are we / what's next."** A new session should read this
> file first for any platform-roadmap work, then jump to the **NEXT ACTION** below.
> Keep this file updated at the end of every work session (it is the cross-session memory anchor).

**Last updated:** 2026-06-03

---

## ▶ NEXT ACTION

**Write the Sub-project B **Phase 2** spec (Auto-Strategy Discovery), then plan → execute.**

- It has **no spec yet** → start with the **`superpowers:brainstorming`** skill (design decisions first), output to
  `docs/superpowers/specs/2026-06-03-subproject-b-phase2-discovery-design.md`, then `superpowers:writing-plans`.
- Context to read first: the Phase 2 outline in `docs/superpowers/specs/2026-06-02-subproject-b-data-archive-design.md`
  (section "Phase 2 — Auto-Strategy Discovery") and the roadmap outline in
  `docs/superpowers/specs/2026-06-02-platform-improvement-roadmap-design.md` (§ "Sub-project B").
- Phase 2 builds on the now-deep archive (B Phase 1) **and** Sub-project A's `/api/universe` + `/api/watchlist`.

**Housekeeping:** Sub-projects A and B1 are both committed **and pushed to `origin/master`** (as of 2026-06-03).

---

## Status board

| # | Sub-project / phase | Status | Spec | Plan | Notes |
|---|---------------------|--------|------|------|-------|
| A | UI cleanup + multi-position dashboard | ✅ **DONE** (Playwright-verified) | roadmap §A | `plans/2026-06-02-subproject-a-ui-cleanup-dashboard.md` (all boxes ✓) | committed **and pushed to origin** |
| B1 | Historical data archive | ✅ **DONE** | `specs/2026-06-02-subproject-b-data-archive-design.md` | `plans/2026-06-02-subproject-b-phase1-data-archive.md` (all boxes ✓) | **Pushed to origin.** Use Coinbase for deep history (Binance 451-blocked, Kraken caps 720) |
| B2 | Auto-strategy discovery | ⬜ **NOT STARTED** ← next | _none yet — write it_ | _none yet_ | sweep→rank→"eligible now"→`/api/discovery`→Discover panel; depends on A + B1 |
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
