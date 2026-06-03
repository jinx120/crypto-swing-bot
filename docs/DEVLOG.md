# Devlog

Running log of platform improvements. Newest first.

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
