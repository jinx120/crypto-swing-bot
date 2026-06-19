# Autonomous Dashboard API

All routes are GET, read-only, unauthenticated. Mounted by `create_app(..., auto_dashboard=AutoDashboardService(...))`.

## GET /api/backtest/ema  and  GET /api/backtest/kronos
Cached once at first call. Returns:
`{ "n_trades": int, "win_rate": float, "total_pnl": float, "sharpe": float, "final_equity": float, "equity_curve": [float, ...] }`

## GET /api/live/position
`null` when flat, else:
`{ "symbol": str, "entry_price": float, "qty": float, "stop": float|null, "tp": float|null, "entry_ts": str|null }`

## GET /api/live/trades?limit=50
`[ { "ts": str, "pnl": float, "won": bool, "reason": str }, ... ]` (newest first; from core-engine `pnl` events)

## GET /api/live/journal?limit=50
`[ { "ts": str, "kind": str, "symbol": str, "reason": str, "payload": object }, ... ]` (newest first)

## GET /api/live/candles?limit=200
`[ { "time": int(epoch_seconds), "open": float, "high": float, "low": float, "close": float, "volume": float }, ... ]` (oldest first)

Data sources: backtest reads `~/.swingbot/candles.db`; live routes read `~/.core-engine/{journal,state,candles}.db`.
