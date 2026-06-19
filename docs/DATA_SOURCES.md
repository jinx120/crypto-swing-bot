# Free Market Data Sources

The backtest loads candles from a `CandleStore` keyed by `(symbol, timeframe)`, so any
asset present in the store works. Backfill via `python -m swingbot.backfill_cli`.

## Crypto (no API key)
- **Coinbase** (`--exchange coinbase`) — deep OHLCV, key-free. Primary source.
- **Kraken** (`--exchange kraken`) — key-free; shallower depth (~720 bars/request).
- Binance is geo-blocked (HTTP 451) from this host — do not use.

## Stocks / indices / ETFs (free, account + key)
These are NOT yet wired into `backfill_cli`; they need a small provider adapter
(follow-on sub-project — see ROADMAP). Free tiers that cost $0:
- **Alpaca** — already have paper keys; IEX stock data free. Good first add.
- **Stooq** — free CSV, no key, daily history for stocks/indices/ETFs.
- **Alpha Vantage / Twelve Data / Finnhub / Tiingo** — free API key, rate-limited.

## How the dashboard uses this
The EMA-vs-Kronos backtest runs on whatever BTC/USD history is in `~/.swingbot/candles.db`.
Today that is the window backfilled in Task 21; extend depth by re-running the backfill.
A universal multi-asset data layer (stocks/indices) is tracked as a separate sub-project.
