from __future__ import annotations

import pandas as pd

from swingbot.data.store import CandleStore

_CANON = ["ts", "open", "high", "low", "close", "volume"]

# Each layout maps canonical fields -> source column (name for header CSVs,
# integer index for headerless ones) plus the unit of the timestamp column.
_LAYOUTS = {
    "cryptodatadownload": {
        "header": True, "ts_unit": "s",
        "cols": {"ts": "unix", "open": "open", "high": "high",
                 "low": "low", "close": "close", "volume": "Volume USD"},
    },
    "binance": {
        "header": False, "ts_unit": "ms",
        "cols": {"ts": 0, "open": 1, "high": 2, "low": 3, "close": 4, "volume": 5},
    },
}


class CsvImporter:
    """Ingest bulk OHLCV CSV dumps (binance.vision, cryptodatadownload) into the
    CandleStore. Malformed rows are skipped, never abort the import."""

    def __init__(self, store: CandleStore):
        self.store = store

    def import_csv(self, path: str, symbol: str, timeframe: str,
                   layout: str = "cryptodatadownload") -> dict:
        spec = _LAYOUTS.get(layout)
        if spec is None:
            raise ValueError(f"unknown CSV layout {layout!r}; "
                             f"choose from {sorted(_LAYOUTS)}")
        raw = pd.read_csv(path, header=0 if spec["header"] else None)
        rows = []
        skipped = 0
        for _, src in raw.iterrows():
            try:
                ts = pd.to_datetime(int(float(src[spec["cols"]["ts"]])),
                                    unit=spec["ts_unit"], utc=True)
                row = {"ts": ts}
                for field in ["open", "high", "low", "close", "volume"]:
                    row[field] = float(src[spec["cols"][field]])
                rows.append(row)
            except (ValueError, TypeError, KeyError):
                skipped += 1
        df = pd.DataFrame(rows, columns=_CANON)
        imported = self.store.upsert_df(symbol, timeframe, df)
        return {"imported": imported, "skipped": skipped}
