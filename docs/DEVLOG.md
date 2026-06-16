# Devlog

Running log of platform improvements. Newest first.

2026-06-16 03:00:02 UTC  GREEN  80.57s  pytest✓ ruff✓ npm-build✓  ui:0fatal  sessions:5/6  drift:1  proposals:0

2026-06-13 03:21:07 UTC  GREEN  46.59s  pytest✓ ruff✓ npm-build✓  ui:0fatal  sessions:6/6  drift:0  proposals:0

2026-06-13 03:12:01 UTC  GREEN  45.29s  pytest✓ ruff✓ npm-build✓  ui:0fatal  sessions:6/6  drift:0  proposals:0

2026-06-12 20:56:26 UTC  GREEN  43.25s  pytest✓ ruff✓ npm-build✓  ui:0fatal  sessions:6/6  drift:0  proposals:0

2026-06-12 20:54:08 UTC  GREEN  52.23s  pytest✓ ruff✓ npm-build✓  ui:0fatal  sessions:5/6  drift:1  proposals:0

2026-06-12 20:52:37 UTC  GREEN  52.85s  pytest✓ ruff✓ npm-build✓  ui:0fatal  sessions:5/6  drift:1  proposals:0

## Sub-project E — Usage Agent (2026-06-13)

Scripted usage sessions that drive the app like a real user, reconcile observed
behavior against documented intent, and emit drift as proposals into the brain inbox.

- **Six sessions, two tiers.** S1 (tab navigation) and S6 (guide-affordance
  reconciliation) run read-only against the live `:8000` container. S2–S5
  (guided strategy flow, watchlist round-trip, settings persistence, brain
  inbox) mutate state against an **ephemeral** `uvicorn` on `:8001` with a
  throwaway `SWINGBOT_DATA_DIR` — the live paper-trading state is never touched.
  Ephemeral teardown + stale-pidfile cleanup guard against leaked instances.
- **Drift → proposals.** An expectations catalog ties each session step to a
  documented claim (with a doc ref + `doc`/`ui` fix bias). Failed steps become
  `DriftFinding`s, mapped to `doc_fix`/`ui_fix` proposals (`source="usage-agent"`,
  recommend-only) in the existing inbox. A `supersede_pending` carve-out keeps
  these findings on the Health tab across brain `recommend()` runs.
- **New action type `doc_fix`** alongside `ui_fix` — both are `NON_EXECUTABLE_ACTIONS`:
  guardrails open them, but `_dispatch` rejects apply with a clear "recommend-only"
  message, and the Brain page hides the Apply button (fixes the ui_fix Apply dead-end).
- **Hash routing** (`#/dashboard … #/health`) so the selftest probe and sessions
  can deep-link every tab; the probe now renders all 7 routes.
- **Health tab** + `/api/agent/runs`, `/runs/latest`, `/artifacts/{name}`
  endpoints serving per-session step traces, screenshots, and drift cards from a
  `runs.json` ring under `DATA_DIR/agent/`.
- **Pipeline:** sessions stage added to the gate (browser/ephemeral infra
  failure → RED; assertion drift stays GREEN and is stored). DEVLOG now inserts
  newest-first under the header; a ROADMAP NEXT-ACTION pointer is written when
  drift is pending.
- **Audit fixes folded in:** honest selftest guardrail stamping (executable
  proposals now `pending` "deferred", not a misleading `approved`); the proposal
  store unified to `brain_proposals.json` (D was writing to a file the UI never
  read); Guide rewritten (arm-not-set-active model, real FVG signal, new
  Discover/Brain/Health section); Discover `alert()` → inline toast.
- **Live-verified:** full gate green, all 6 sessions pass, 0 drift; Health tab
  confirmed live via Playwright (GREEN banner, 6/6 sessions, run history).

## Sub-project C — Ollama Decision Brain (2026-06-03)

- New `decision/` package: `ollama.py` (schema-constrained JSON client that never raises),
  `prompt.py` (prompt builder + strict parser), `guardrails.py` (pure per-action gate),
  `proposals.py` (`Proposal` + JSON inbox + issue log), `brain.py` (`DecisionBrain` orchestrator),
  plus `notify.py` (failure-tolerant Discord webhook).
- Turns B2 discovery output + live portfolio context into guardrailed proposals
  (arm / disarm / tune / portfolio_settings). **Recommend-only by default**; opt-in
  `brain_autonomous_mode` auto-applies guardrail-approved proposals above a confidence threshold
  (all action types, no carve-out). All brain work runs off the trading thread.
- Config lives in portfolio settings (`brain_model`, `brain_ollama_url`, `brain_confidence_threshold`,
  `brain_timeout_s`, `brain_autonomous_mode`, `brain_auto_recommend`); Discord webhook URL is a
  write-only secret. Model is fully swappable — never hardcoded.
- API: `POST /api/brain/recommend`, `GET /api/brain/proposals`, `POST .../apply`, `POST .../dismiss`,
  `GET /api/brain/issues`, `POST /api/brain/summary`, `GET/PUT /api/brain/webhook`. Opt-in
  `auto_recommend` kicks a run after each discovery sweep.
- UI: new **Brain** page — proposals inbox (apply/dismiss, blocked greyed w/ reason), autonomous &
  auto-recommend toggles, model/connection config, Discord webhook field, issues feed.
- Verified live with real `qwen2.5` (Playwright + API). `288 passed, 5 skipped`; frontend builds.
  See `docs/SUBPROJECT_C_FINDINGS.md` — notably the Docker→host Ollama URL must be the bridge
  gateway (`http://172.17.0.1:11434`), not `localhost`.

## 2026-06-02 — Sub-project A: UI cleanup + multi-position dashboard
- Removed the hardcoded `TRX/USD` default; symbol is now picked from a curated
  Alpaca USD list (`GET /api/universe`, live with static fallback).
- Added a persisted watchlist (`GET/PUT /api/watchlist`) and a `default_symbol` setting.
- Strategy page: low-level form collapsed behind an "Advanced" disclosure; the
  default flow is pick-crypto → preset → backtest → arm.
- Dashboard: new `PositionGrid` shows every open position as a mini chart, plus a
  watchlist row.
- Roadmap: B (auto-discovery) → C (Ollama brain) → D (self-test gate) still to come.

## Sub-project B Phase 2 — Auto-Strategy Discovery (2026-06-03)

- `DiscoveryEngine` (`src/swingbot/discovery.py`): sweeps the universe × non-AI archetypes
  over the deep archive, ranks by expectancy; `eligible_now = good_history + regime OK`,
  `fires_now` shown as a non-gating indicator; coverage-derived scenario windows.
- API: `GET /api/discovery`, `GET /api/discovery/windows`, `POST /api/discovery/refresh`
  (daemon-thread sweep + `discovery.json` cache), `POST /api/discovery/arm` (save + arm, paper).
- UI: `Discover` page — ranked-by-coin table, eligible badges, fires dot, one-click arm.
- Deferred: per-row equity curves / trade tables, hardcoded crisis windows, timer recompute,
  real-money live gating.

2026-06-08 22:55:05 UTC  RED  22.32s  pytest✗ ruff✗ npm-build✓  ui:0fatal  proposals:0
2026-06-08 22:59:42 UTC  GREEN  24.9s  pytest✓ ruff✓ npm-build✓  ui:0fatal  proposals:0