# Live acceptance — core-engine

1. Backfill ~5 days of 5-min BTC/USD candles into $CORE_ENGINE_DATA/candles.db.
2. `python -m core_engine backtest --limit 1500` → prints a sane trade count + final equity.
3. `python -m core_engine run` (paper) → leave one full 5-min tick to elapse.
4. `python -m core_engine report` → shows a decision was made; if it entered, an open
   position with stop/tp; P&L line present.
5. Kill the process, restart `run` → it auto-resumes (running_desired persisted).
6. Confirm: a stalled (pending_new) BUY is reported as "entry pending", NOT as an open position.
