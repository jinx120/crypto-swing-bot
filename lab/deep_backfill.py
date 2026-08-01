"""Deep Coinbase backfill for the Phase 2 exit-geometry study.

Why this exists instead of `python -m swingbot.backfill_cli`: the CLI builds an
ArchiveConfig with `quote_map=None`, which CcxtProvider turns into its default
{"USD": "USDT"} - so `--symbols BTC/USD --exchange coinbase` has always fetched
Coinbase's BTC/USDT market. That market returns ZERO rows before 2022-01-01,
which is exactly why every prior archive starts there. The USD-quoted markets
reach 2015-07-20 (BTC) and 2016-05-18 (ETH). The CLI has no flag to express "no
quote mapping", so the deep archive is built here.

Writes to its own data dir so the USD-quoted deep series never mixes with the
USDT-quoted 2022+ archive under the same symbol key.

Run:
    SWINGBOT_DATA_DIR=/tmp/swingbot-deep .venv/bin/python -m lab.deep_backfill
"""
from __future__ import annotations

import os

from swingbot.data.backfill import ArchiveConfig, Backfiller
from swingbot.data.ccxt_provider import CcxtProvider
from swingbot.data.store import CandleStore

DATA_DIR = os.environ.get("SWINGBOT_DATA_DIR", "/tmp/swingbot-deep")

# Coinbase USD-market inception, probed live 2026-08-01. Asking for earlier just
# returns nothing, so these are limits of the venue, not preferences.
HISTORY_START = {"BTC/USD": "2015-07-20", "ETH/USD": "2016-05-18"}

# 1h is the study resolution (resampled to 4h); 1d is the secondary arm. Both are
# fetched in one pass because the second costs ~4k bars on top of ~96k.
TIMEFRAMES = ["1h", "1d"]


def deep_config(symbol: str) -> ArchiveConfig:
    """One symbol's deep-archive config.

    `quote_map={}` is the whole point: it disables the USD->USDT rewrite that
    silently caps Coinbase history at 2022-01-01.
    """
    return ArchiveConfig(
        exchange="coinbase",
        symbols=[symbol],
        timeframes=list(TIMEFRAMES),
        history_start=HISTORY_START[symbol],
        quote_map={},
    )


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    store = CandleStore(os.path.join(DATA_DIR, "candles.db"))
    total = 0
    for symbol in HISTORY_START:
        cfg = deep_config(symbol)
        provider = CcxtProvider(exchange_id=cfg.exchange, quote_map=cfg.quote_map)
        # Backfiller is coverage-driven and idempotent: a re-run fills only the
        # gaps, so an interrupted fetch is safe to resume by re-running.
        total += Backfiller(store, provider=provider).run(cfg)
    print(f"[deep-backfill] {total} new bars into {DATA_DIR}")


if __name__ == "__main__":
    main()
