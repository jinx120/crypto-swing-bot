from __future__ import annotations

import argparse
import os

from swingbot.data.backfill import ArchiveConfig, Backfiller
from swingbot.data.ccxt_provider import CcxtProvider
from swingbot.data.csv_import import CsvImporter
from swingbot.data.store import CandleStore

DATA_DIR = os.environ.get("SWINGBOT_DATA_DIR", os.path.expanduser("~/.swingbot"))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="swingbot-backfill",
                                 description="Backfill deep OHLCV history into the candle store")
    d = ArchiveConfig()
    ap.add_argument("--exchange", default=d.exchange)
    ap.add_argument("--symbols", default=",".join(d.symbols),
                    help="comma-separated, e.g. BTC/USD,ETH/USD")
    ap.add_argument("--timeframes", default=",".join(d.timeframes),
                    help="comma-separated, e.g. 5m,15m,1h")
    ap.add_argument("--start", default=d.history_start, help="ISO date, e.g. 2024-06-01")
    # CSV import mode (overrides the CCXT path when --csv is given)
    ap.add_argument("--csv", default=None, help="import a CSV dump instead of fetching")
    ap.add_argument("--symbol", default=None, help="symbol for --csv import")
    ap.add_argument("--timeframe", default=None, help="timeframe for --csv import")
    ap.add_argument("--csv-layout", default="cryptodatadownload",
                    help="cryptodatadownload | binance")
    return ap


def config_from_args(args) -> ArchiveConfig:
    return ArchiveConfig(
        exchange=args.exchange,
        symbols=[s.strip() for s in args.symbols.split(",") if s.strip()],
        timeframes=[t.strip() for t in args.timeframes.split(",") if t.strip()],
        history_start=args.start,
    )


def main() -> None:
    args = build_parser().parse_args()
    store = CandleStore(os.path.join(DATA_DIR, "candles.db"))
    if args.csv:
        if not (args.symbol and args.timeframe):
            raise SystemExit("--csv requires --symbol and --timeframe")
        res = CsvImporter(store).import_csv(
            args.csv, args.symbol, args.timeframe, layout=args.csv_layout)
        print(f"[backfill] imported {res['imported']} bars "
              f"({res['skipped']} skipped) from {args.csv}")
        return
    cfg = config_from_args(args)
    provider = CcxtProvider(exchange_id=cfg.exchange,
                            quote_map=cfg.quote_map,
                            symbol_overrides=cfg.symbol_overrides)
    written = Backfiller(store, provider=provider).run(cfg)
    print(f"[backfill] done: {written} new bars across "
          f"{len(cfg.symbols)} symbols x {len(cfg.timeframes)} timeframes")


if __name__ == "__main__":
    main()
