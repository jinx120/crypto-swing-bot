# Roadmap Status — crypto-swing-bot

> **Single source of truth for "where are we / what's next."** A new session should read this
> file first for any platform-roadmap work, then jump to the **NEXT ACTION** below.
> Keep this file updated at the end of every work session (it is the cross-session memory anchor).

**Last updated:** 2026-06-03

---

## ▶ NEXT ACTION

**Write the Sub-project D plan from the approved spec.** Phase = PLAN.

- The D spec is ✅ DONE & committed: `docs/superpowers/specs/2026-06-03-subproject-d-self-test-gate-design.md`.
  Load `superpowers:writing-plans`, read that spec, and write the plan to
  `docs/superpowers/plans/2026-06-03-subproject-d-self-test-gate.md`. Do NOT re-brainstorm — design is final.
- Spec summary (all forks locked with user): new `src/swingbot/selftest/` package with a CLI
  `python -m swingbot.selftest`. Deterministic gate (`pytest -q` + `ruff check` + `npm run build`) +
  a **real headless Python Playwright probe** of the running `:8000` app (captures console errors,
  failed/5xx requests, page exceptions, screenshots → `UIFinding`s). Gate-first: red → write report,
  Discord ping, **skip LLM**, exit 1. Green → LLM pass via `decision/ollama.py` (model
  **`qwen3.5:9b` Q4_K_M**, configurable) turns health+findings+`git diff --stat` into structured
  `Proposal`s in C's `ProposalStore` inbox (recommend-only; new `ui_fix` action). Report →
  overwrite `docs/SELFTEST_REPORT.md` + one dated GREEN/RED line in `DEVLOG.md`. Scheduled via `/loop`/`/schedule`.
- Modules to build: `checks.py`, `uiprobe.py`, `llm.py`, `report.py`, `runner.py`, `__main__.py`.
  Reuse `decision/ollama.py`, `decision/proposals.py`, `decision/guardrails.py`, `notify.py`.
  New dev dep: `pytest-playwright` + `playwright install chromium`.
- Sub-project C (Ollama Decision Brain) is ✅ DONE — all 11 plan tasks executed, `288 passed, 5 skipped`,
  frontend builds, live-verified with real qwen2.5. See `docs/DEVLOG.md` and `docs/SUBPROJECT_C_FINDINGS.md`.

**Active-dev rebuild policy (NEW):** during D implementation the user expects a Docker
rebuild/restart of `swingbot` on **every change** — it is pre-authorized and routine. Do NOT
announce or block on it; just `docker compose build swingbot && docker compose up -d swingbot`.
(Recorded in `~/CLAUDE.md` standing-authorization section.)

**Housekeeping:** Sub-projects A, B1, B2 are committed **and pushed to `origin/master`**. Sub-project C
(spec, plan, Tasks 1–11) is committed **and pushed to `origin/master`** as of 2026-06-03. One open
finding to action: the brain's default `brain_ollama_url` (`localhost:11434`) does
not work inside Docker — use the bridge gateway `http://172.17.0.1:11434` (already set on the running
instance). See `docs/SUBPROJECT_C_FINDINGS.md`.

---

## Status board

| # | Sub-project / phase | Status | Spec | Plan | Notes |
|---|---------------------|--------|------|------|-------|
| A | UI cleanup + multi-position dashboard | ✅ **DONE** (Playwright-verified) | roadmap §A | `plans/2026-06-02-subproject-a-ui-cleanup-dashboard.md` (all boxes ✓) | committed **and pushed to origin** |
| B1 | Historical data archive | ✅ **DONE** | `specs/2026-06-02-subproject-b-data-archive-design.md` | `plans/2026-06-02-subproject-b-phase1-data-archive.md` (all boxes ✓) | **Pushed to origin.** Use Coinbase for deep history (Binance 451-blocked, Kraken caps 720) |
| B2 | Auto-strategy discovery | ✅ **DONE** | `specs/2026-06-03-subproject-b-phase2-discovery-design.md` | `plans/2026-06-03-subproject-b-phase2-discovery.md` (10 tasks, all boxes ✓) | sweep→rank→"eligible now"→`/api/discovery`→Discover panel; committed locally (not pushed) |
| C | Ollama decision brain | ✅ **DONE** (live-verified) | `specs/2026-06-04-subproject-c-decision-brain-design.md` | `plans/2026-06-04-subproject-c-decision-brain.md` (11 tasks, all boxes ✓) | `decision/` pkg → qwen2.5; recommend-only default + autonomous toggle; Brain page. **Pushed to origin** |
| D | Self-test gate + LLM proposals | 🟡 **PLAN NEXT** ← write plan | `specs/2026-06-03-subproject-d-self-test-gate-design.md` (approved) | — ← write next | pytest+ruff+build gate + real Playwright probe → report+devlog; green→LLM (`qwen3.5:9b`) proposals into C's inbox |

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
