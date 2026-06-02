# Platform Improvement Roadmap — Design

**Date:** 2026-06-02
**Status:** Approved (design); Sub-project A specced in detail, B/C/D as scoped outlines.

## Goal

Improve the crypto-swing-bot platform along four lines the user asked for: clean up the
UI (drop the hardcoded `TRX/USD`, simplify the Strategy page), see all open positions at
once as a grid of live charts, let users pick which cryptos to trade, auto-discover viable
strategies, add a local-LLM decision brain, and run continuous self-testing. Delivered as
four sequenced sub-projects (A→B→C→D), each with its own spec→plan when reached.

## Decisions (locked with user)

- **Crypto picker:** curated list of Alpaca-tradable **USD** pairs (fetched from broker).
  Structurally avoids the BTC/USDT silent-no-fill trap.
- **Dashboard grid:** open positions **plus** a watchlist row.
- **LLM autonomy:** recommend-only by default, with an opt-in toggle for full autonomy
  (auto-apply within risk guardrails).
- **Self-testing:** deterministic checks gate first; if green, LLM proposes improvements.

## Current state (grounded in code)

- Frontend: React/Vite. `Dashboard.jsx` is a thin (22-line) composer; `Strategy.jsx` is the
  247-line page to simplify. `ChartPanel.jsx` already supports mini mode + explicit symbol.
  `PortfolioBanner`/`StrategyCard`/`PositionPanel` exist from Phase 3.
- Backend: `web.py` exposes `/api/state` (holds positions), `/api/strategies`, arm/disarm,
  `/api/portfolio/settings`, `/api/presets`, `/api/strategy/backtest`, `/api/strategy/build`,
  per-strategy control. **No universe/tradable-assets endpoint exists.**
- `presets.py` + `strategy_search.py` + `backtest.py` already generate & backtest candidates.
- Ollama installed with `qwen2.5:latest` (4.7 GB).
- `TRX/USD` is the hardcoded default symbol in `Strategy.jsx`, `PresetGallery.jsx`,
  `StrategyBuilder.jsx`, and README — a default, not a bug.
- No devlog file exists yet. 160 tests passing.

---

## Sub-project A — UI cleanup + multi-position dashboard *(build first)*

### Backend (additions to `web.py`)
- `GET /api/universe` → curated Alpaca-tradable USD crypto pairs, sourced from
  `broker/alpaca.py` (list assets, filter `*/USD`, tradable), cached in-process. On
  credential/network failure, return a small static fallback list (BTC/USD, ETH/USD, …).
- `GET /api/watchlist` / `PUT /api/watchlist` → list of symbols persisted in `swingbot.db`.
- Positions are already in `/api/state`; no new positions endpoint.

### Symbol-agnostic cleanup
- Remove all `'TRX/USD'` literals from `Strategy.jsx`, `PresetGallery.jsx`,
  `StrategyBuilder.jsx`. Default symbol resolves to a user setting (`default_symbol` in
  portfolio settings), falling back to the first `/api/universe` entry.
- Update README target-asset wording to be symbol-agnostic.

### Strategy page → straightforward
- Collapse `Strategy.jsx` into one linear flow: **pick crypto (universe dropdown) → pick
  preset (risk/style) → backtest → arm.** Raw-field / JSON editing moves behind an
  "Advanced" disclosure that defaults closed. Preset-first; advanced is opt-in.

### Dashboard grid
- New `PositionGrid` component: a responsive grid of mini `ChartPanel`s — one tile per
  **open position** (read from `/api/state`), followed by a **watchlist row** of mini charts
  (from `/api/watchlist`). Clear empty states ("No open positions", "Watchlist empty").
- `Dashboard.jsx` composes `PositionGrid` above the existing portfolio banner.

### Devlog
- Create `docs/DEVLOG.md`; first entry records Sub-project A.

### Verification (Playwright)
- Dashboard renders the position grid + watchlist row with no console errors.
- Strategy page lets the user select a crypto sourced from `/api/universe`.
- No remaining `TRX/USD` literal in the served frontend bundle.
- `pytest` green for new backend endpoints (universe fallback, watchlist persistence).

### Out of scope for A
Strategy discovery automation, any LLM calls, scheduled self-testing — those are B/C/D.

---

## Sub-project B — Auto-strategy discovery *(outline)*

Reuse `presets.build_candidates` + `strategy_search`. Add a sweep that runs candidates across
the watchlist/universe, ranks by backtest metrics (expectancy/profit factor), and exposes an
"eligible now" ranked list via `GET /api/discovery` plus a background job. UI: a Discover
panel showing ranked strategies per crypto with one-click arm. Depends on A's universe +
watchlist. Own spec→plan when reached.

## Sub-project C — Ollama decision brain *(outline)*

New `decision` module calls local `qwen2.5` (via Ollama HTTP) with discovery results +
portfolio state, returning proposed arm/disarm/tune actions as structured JSON. **Default
recommend-only**: proposals surface in the UI and the user applies them. A settings toggle
`autonomous_mode`, when enabled, auto-applies proposals **within `portfolio_risk` guardrails**
(max positions, risk budget). Endpoints: `POST /api/brain/recommend`, `GET /api/brain/proposals`,
apply via existing arm/disarm/control endpoints. Depends on B. Own spec→plan.

## Sub-project D — Self-test gate + LLM proposals *(outline)*

A runner executes `pytest` + `npm run build` + a Playwright smoke + `ruff`, writing a health
summary (pass/fail + key output) to `DEVLOG.md`. **If green**, an Ollama pass reviews recent
diffs/usage and appends improvement proposals to the devlog. Scheduled via the `/loop` or
`/schedule` skill. Depends on the Playwright smoke from A. Own spec→plan.

---

## Sequencing rationale

A delivers immediate visible value and is a prerequisite for the rest: you must pick cryptos
and see positions (A) before automating discovery (B), and discovery must exist before an LLM
can choose among strategies (C). D's self-test reuses A's Playwright smoke. C/D are the
riskiest/least-defined, so they are last — designed once A/B reveal what "good automation"
concretely means here. Each sub-project stays one small plan to keep token cost low.
