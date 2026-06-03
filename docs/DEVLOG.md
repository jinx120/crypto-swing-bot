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
