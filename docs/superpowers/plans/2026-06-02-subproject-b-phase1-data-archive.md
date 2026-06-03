# Sub-project B Phase 1 — Historical Market-Data Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `swingbot-backfill` path (CLI + API) that populates the existing `CandleStore` with deep history from CCXT and CSV dumps, so every backtest runs on real multi-month history instead of the current ~5 days — with zero changes to `backtest.py` / `strategy_search.py`.

**Architecture:** All new code lives under `src/swingbot/data/`, mirroring `alpaca.py`/`store.py`/`market.py`. A `CcxtProvider` implements the existing `MarketDataProvider` Protocol and adds a paginating `get_candles_range`. A `CsvImporter` ingests bulk dumps. A `Backfiller` orchestrates fetch→upsert, using a new `CandleStore.coverage` query to stay idempotent/resumable. Wiring is a CLI entry point plus two token-guarded endpoints that mirror existing `web.py` patterns.

**Tech Stack:** Python 3.11, pandas, SQLite (`CandleStore`), FastAPI, `ccxt` (new dependency), pytest. The venv is `.venv` — run everything with `.venv/bin/python`.

---

## Conventions (read once before starting)

- **Run tests with the project venv:** `.venv/bin/python -m pytest ...`. Plain `python`/`pytest` are not on PATH.
- **Baseline:** the suite is currently **207 passed, 4 skipped**. Every task must keep it green; the final task confirms 207 + new tests pass.
- **Canonical bar DataFrame** (what `CandleStore.upsert_df` consumes): columns `ts, open, high, low, close, volume`, where `ts` is a **UTC pandas Timestamp** (upsert calls `int(r.ts.timestamp())`). Match `data/historical.py:REQUIRED_COLUMNS` and `data/alpaca.py:bars_to_df`.
- **Store `ts` is epoch seconds.** Coverage and the store speak seconds; CCXT speaks milliseconds. Convert at the CCXT boundary only.
- **Timeframes** use the app's `15m/5m/1h/4h/1d` form. `swingbot.data.market.timeframe_seconds(tf)` already converts these to seconds — reuse it, do not re-implement.
- **No-network tests:** mirror the existing style (the 4 skipped tests are Alpaca-network). Unit tests inject a *fake* ccxt exchange — never hit the network.
- **Commit after every task** with the exact message given.

## File Structure

**Create:**
- `src/swingbot/data/ccxt_provider.py` — `CcxtProvider`: Protocol impl + `get_candles_range` pagination + symbol/timeframe mapping.
- `src/swingbot/data/csv_import.py` — `CsvImporter`: layout-aware CSV → canonical df → `store.upsert_df`.
- `src/swingbot/data/backfill.py` — `ArchiveConfig` + `Backfiller`: coverage-driven, idempotent orchestration.
- `src/swingbot/backfill_cli.py` — `swingbot-backfill` entry point.
- `tests/test_ccxt_provider.py`, `tests/test_csv_import.py`, `tests/test_backfill.py`, `tests/test_backfill_cli.py`, `tests/test_web_archive.py`.

**Modify:**
- `src/swingbot/data/store.py` — add `coverage()` (the only store change).
- `tests/test_candle_store.py` — add coverage tests.
- `src/swingbot/web.py` — add `backfiller=None` param to `create_app`; add `/api/archive/status` + `/api/archive/backfill`.
- `src/swingbot/webmain.py` — construct a `Backfiller` and pass it to `create_app`.
- `pyproject.toml` — add `ccxt` dependency and the `swingbot-backfill` script.

---

## Task 1: `CandleStore.coverage`

**Files:**
- Modify: `src/swingbot/data/store.py` (add one method after `get`)
- Test: `tests/test_candle_store.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_candle_store.py`:

```python
def test_coverage_reports_min_max_count(tmp_path):
    store = CandleStore(str(tmp_path / "candles.db"))
    store.upsert_df("TRX/USD", "15m", _df([10, 11, 12]))
    cov = store.coverage("TRX/USD", "15m")
    bars = store.get("TRX/USD", "15m")
    assert cov["count"] == 3
    assert cov["min_ts"] == bars[0]["time"]
    assert cov["max_ts"] == bars[-1]["time"]


def test_coverage_empty_when_no_bars(tmp_path):
    store = CandleStore(str(tmp_path / "candles.db"))
    cov = store.coverage("TRX/USD", "15m")
    assert cov == {"min_ts": None, "max_ts": None, "count": 0}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_candle_store.py -k coverage -v`
Expected: FAIL with `AttributeError: 'CandleStore' object has no attribute 'coverage'`

- [ ] **Step 3: Implement `coverage`**

In `src/swingbot/data/store.py`, add this method to `CandleStore` immediately after `get` (before `symbols`):

```python
    def coverage(self, symbol: str, timeframe: str) -> dict:
        """Min/max bar timestamp (epoch seconds) and count for a series.
        Powers backfill resumability and the archive status endpoint."""
        with self._lock, self._connect() as con:
            cur = con.execute(
                "SELECT MIN(ts), MAX(ts), COUNT(*) FROM bars "
                "WHERE symbol=? AND timeframe=?",
                (symbol, timeframe),
            )
            min_ts, max_ts, count = cur.fetchone()
        return {"min_ts": min_ts, "max_ts": max_ts, "count": count}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_candle_store.py -v`
Expected: PASS (all candle-store tests, including the two new ones)

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/data/store.py tests/test_candle_store.py
git commit -m "feat(archive): add CandleStore.coverage for resumable backfill"
```

---

## Task 2: Add `ccxt` dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add ccxt to dependencies**

In `pyproject.toml`, change the `dependencies` line under `[project]`:

```toml
dependencies = ["pandas>=2.0", "numpy>=1.24", "alpaca-py>=0.20", "fastapi>=0.110", "uvicorn>=0.29", "ccxt>=4.0"]
```

- [ ] **Step 2: Install it into the venv**

Run: `.venv/bin/python -m pip install "ccxt>=4.0"`
Expected: ends with `Successfully installed ccxt-<version> ...`

- [ ] **Step 3: Verify the import works**

Run: `.venv/bin/python -c "import ccxt; print(ccxt.__version__)"`
Expected: a version string like `4.x.y` (no traceback)

- [ ] **Step 4: Confirm the suite still passes**

Run: `.venv/bin/python -m pytest -q`
Expected: `207 passed, 4 skipped`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "build: add ccxt dependency for the historical data archive"
```

---

## Task 3: `CcxtProvider` — symbol & timeframe mapping

**Files:**
- Create: `src/swingbot/data/ccxt_provider.py`
- Test: `tests/test_ccxt_provider.py`

This task builds the provider class with mapping only; range pagination is Task 4 (same file).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ccxt_provider.py`:

```python
from swingbot.data.ccxt_provider import CcxtProvider


def test_quote_map_translates_usd_to_usdt():
    p = CcxtProvider(exchange_id="binance", exchange=object())
    assert p.map_symbol("BTC/USD") == "BTC/USDT"
    assert p.map_symbol("ETH/USD") == "ETH/USDT"


def test_per_symbol_override_wins_over_quote_map():
    p = CcxtProvider(exchange_id="kraken", exchange=object(),
                     symbol_overrides={"BTC/USD": "XBT/USD"})
    assert p.map_symbol("BTC/USD") == "XBT/USD"


def test_custom_quote_map_passes_unknown_quotes_through():
    p = CcxtProvider(exchange_id="coinbase", exchange=object(), quote_map={})
    assert p.map_symbol("BTC/USD") == "BTC/USD"  # exact USD venue, no remap
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_ccxt_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.data.ccxt_provider'`

- [ ] **Step 3: Create the provider with mapping**

Create `src/swingbot/data/ccxt_provider.py`:

```python
from __future__ import annotations

import pandas as pd

from swingbot.data.market import timeframe_seconds

_CANON = ["ts", "open", "high", "low", "close", "volume"]
_DEFAULT_QUOTE_MAP = {"USD": "USDT"}


class CcxtProvider:
    """Market data via CCXT's unified API. Implements MarketDataProvider and
    adds get_candles_range() for deep backfill.

    The app speaks Alpaca symbols (BTC/USD); a config-driven quote_map plus
    optional per-symbol overrides translate to the exchange's symbol (e.g. on
    Binance BTC/USD -> BTC/USDT). Pass `exchange` to inject a client (tests);
    otherwise one is lazily built from `exchange_id`.
    """

    def __init__(self, exchange_id: str = "binance", quote_map: dict | None = None,
                 symbol_overrides: dict | None = None, exchange=None,
                 api_key: str | None = None, secret: str | None = None):
        self.exchange_id = exchange_id
        self.quote_map = _DEFAULT_QUOTE_MAP if quote_map is None else quote_map
        self.symbol_overrides = symbol_overrides or {}
        self._api_key = api_key
        self._secret = secret
        self._exchange = exchange

    def _build_exchange(self):
        import ccxt  # lazy: import only when a real client is needed
        cls = getattr(ccxt, self.exchange_id)
        cfg = {"enableRateLimit": True}
        if self._api_key:
            cfg["apiKey"] = self._api_key
        if self._secret:
            cfg["secret"] = self._secret
        return cls(cfg)

    @property
    def exchange(self):
        if self._exchange is None:
            self._exchange = self._build_exchange()
        return self._exchange

    def map_symbol(self, symbol: str) -> str:
        if symbol in self.symbol_overrides:
            return self.symbol_overrides[symbol]
        if "/" in symbol:
            base, quote = symbol.split("/", 1)
            return f"{base}/{self.quote_map.get(quote, quote)}"
        return symbol
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_ccxt_provider.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/data/ccxt_provider.py tests/test_ccxt_provider.py
git commit -m "feat(archive): add CcxtProvider with config-driven symbol mapping"
```

---

## Task 4: `CcxtProvider.get_candles_range` + Protocol methods

**Files:**
- Modify: `src/swingbot/data/ccxt_provider.py`
- Test: `tests/test_ccxt_provider.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ccxt_provider.py`:

```python
class _FakeExchange:
    """Serves OHLCV from an in-memory list, paginating like ccxt:
    fetch_ohlcv returns up to `page` bars at ts >= since. Rows are
    [ts_ms, open, high, low, close, volume]."""

    def __init__(self, rows, page=3):
        self.rows = rows
        self.page = page
        self.calls = []  # (symbol, timeframe, since, limit) for assertions

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
        self.calls.append((symbol, timeframe, since, limit))
        since = since or 0
        out = [r for r in self.rows if r[0] >= since]
        return out[: (limit or self.page)]

    def fetch_ticker(self, symbol):
        return {"last": self.rows[-1][4]}


def _rows(start_ms, n, step_ms=900_000):
    # 900_000 ms = 15m. price climbs so bars are distinguishable.
    return [[start_ms + i * step_ms, 100 + i, 101 + i, 99 + i, 100.5 + i, 10 + i]
            for i in range(n)]


def test_range_paginates_until_end_and_maps_symbol():
    rows = _rows(0, 10)  # ts 0 .. 9*900_000
    ex = _FakeExchange(rows, page=3)
    p = CcxtProvider(exchange_id="binance", exchange=ex)
    df = p.get_candles_range("BTC/USD", "15m", start_ms=0, end_ms=9 * 900_000)
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume"]
    assert len(df) == 10                       # all bars, across multiple pages
    assert len(ex.calls) >= 4                  # 10 bars / 3 per page -> paginated
    assert ex.calls[0][0] == "BTC/USDT"        # symbol was mapped
    assert str(df["ts"].dt.tz) == "UTC"        # canonical UTC Timestamp
    assert df["ts"].is_monotonic_increasing


def test_range_stops_at_end_ms():
    ex = _FakeExchange(_rows(0, 10), page=100)
    p = CcxtProvider(exchange_id="binance", exchange=ex)
    df = p.get_candles_range("BTC/USD", "15m", start_ms=0, end_ms=3 * 900_000)
    assert df["ts"].max() <= pd.Timestamp(3 * 900_000, unit="ms", tz="UTC")


def test_get_candles_range_tail_is_deterministic():
    ex = _FakeExchange(_rows(0, 50), page=1000)
    p = CcxtProvider(exchange_id="binance", exchange=ex)
    df = p.get_candles_range("BTC/USD", "15m", start_ms=0, end_ms=49 * 900_000).tail(5)
    assert len(df) == 5
    assert df["open"].tolist() == [145.0, 146.0, 147.0, 148.0, 149.0]


def test_get_latest_price_uses_ticker():
    ex = _FakeExchange(_rows(0, 3), page=10)
    p = CcxtProvider(exchange_id="binance", exchange=ex)
    assert p.get_latest_price("BTC/USD") == ex.rows[-1][4]
```

Add `import pandas as pd` at the top of the test file if not already present (it is used by `test_range_stops_at_end_ms`).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_ccxt_provider.py -k "range or get_candles or latest_price" -v`
Expected: FAIL with `AttributeError: 'CcxtProvider' object has no attribute 'get_candles_range'`

- [ ] **Step 3: Implement range pagination and Protocol methods**

Append these methods to `CcxtProvider` in `src/swingbot/data/ccxt_provider.py` (after `map_symbol`):

```python
    @staticmethod
    def _rows_to_df(rows: list[list]) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame(columns=_CANON)
        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = df[c].astype(float)
        return df[_CANON]

    def get_candles_range(self, symbol: str, timeframe: str,
                          start_ms: int, end_ms: int, page_limit: int = 1000) -> pd.DataFrame:
        """Fetch all bars in [start_ms, end_ms], paginating fetch_ohlcv forward.
        CCXT returns <= ~1000 bars/page; we advance `since` past the last bar
        until we reach end_ms or a page returns no progress."""
        ex_symbol = self.map_symbol(symbol)
        step_ms = timeframe_seconds(timeframe) * 1000
        since = start_ms
        collected: list[list] = []
        while since <= end_ms:
            page = self.exchange.fetch_ohlcv(ex_symbol, timeframe, since=since, limit=page_limit)
            if not page:
                break
            for row in page:
                if row[0] > end_ms:
                    break
                collected.append(row)
            last_ts = page[-1][0]
            if last_ts < since:           # exchange returned no forward progress
                break
            since = last_ts + step_ms
            if len(page) < page_limit:     # last (partial) page; nothing more upstream
                break
        df = self._rows_to_df(collected)
        if not df.empty:
            df = df.drop_duplicates(subset="ts").sort_values("ts").reset_index(drop=True)
        return df

    def get_candles(self, symbol: str, timeframe: str, lookback: int) -> pd.DataFrame:
        """MarketDataProvider impl: most-recent `lookback` bars."""
        step_ms = timeframe_seconds(timeframe) * 1000
        end_ms = self.exchange.milliseconds() if hasattr(self.exchange, "milliseconds") \
            else int(pd.Timestamp.utcnow().timestamp() * 1000)
        start_ms = end_ms - lookback * step_ms * 3  # 3x cushion for venue gaps
        df = self.get_candles_range(symbol, timeframe, start_ms, end_ms)
        return df.tail(lookback).reset_index(drop=True)

    def get_latest_price(self, symbol: str) -> float:
        return float(self.exchange.fetch_ticker(self.map_symbol(symbol))["last"])
```

Note: `get_candles` (the Protocol method) computes `start_ms` from the exchange clock, so it is not deterministic against the fixed-epoch fake; it is exercised live in Task 9's network-gated smoke test. The unit layer covers the deterministic `get_candles_range` path that all backfilling actually uses (the `test_get_candles_returns_tail_lookback` test above drives `get_candles_range(...).tail(5)` directly).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_ccxt_provider.py -v`
Expected: PASS (all CcxtProvider tests)

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/data/ccxt_provider.py tests/test_ccxt_provider.py
git commit -m "feat(archive): paginating CcxtProvider.get_candles_range + provider methods"
```

---

## Task 5: `CsvImporter`

**Files:**
- Create: `src/swingbot/data/csv_import.py`
- Test: `tests/test_csv_import.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_csv_import.py`:

```python
import pandas as pd

from swingbot.data.csv_import import CsvImporter
from swingbot.data.store import CandleStore


def _write(path, text):
    path.write_text(text)
    return str(path)


def test_imports_cryptodatadownload_layout(tmp_path):
    # cryptodatadownload: header row, `unix` epoch seconds, title-case Volume.
    csv = _write(tmp_path / "cdd.csv",
        "unix,date,symbol,open,high,low,close,Volume USD\n"
        "1704067200,2024-01-01,BTC/USD,100,110,90,105,1000\n"
        "1704068100,2024-01-01,BTC/USD,105,115,95,108,1200\n")
    store = CandleStore(str(tmp_path / "candles.db"))
    res = CsvImporter(store).import_csv(csv, "BTC/USD", "15m", layout="cryptodatadownload")
    assert res == {"imported": 2, "skipped": 0}
    bars = store.get("BTC/USD", "15m")
    assert len(bars) == 2 and bars[0]["open"] == 100.0


def test_imports_binance_layout_no_header(tmp_path):
    # binance.vision klines: no header; col0 = open_time in ms.
    csv = _write(tmp_path / "binance.csv",
        "1704067200000,100,110,90,105,1000,1704068099999,0,0,0,0,0\n"
        "1704068100000,105,115,95,108,1200,1704068999999,0,0,0,0,0\n")
    store = CandleStore(str(tmp_path / "candles.db"))
    res = CsvImporter(store).import_csv(csv, "BTC/USD", "15m", layout="binance")
    assert res == {"imported": 2, "skipped": 0}
    assert len(store.get("BTC/USD", "15m")) == 2


def test_skips_malformed_rows(tmp_path):
    csv = _write(tmp_path / "bad.csv",
        "unix,date,symbol,open,high,low,close,Volume USD\n"
        "1704067200,2024-01-01,BTC/USD,100,110,90,105,1000\n"
        "1704068100,2024-01-01,BTC/USD,notanumber,115,95,108,1200\n"
        ",,,,,,,\n")
    store = CandleStore(str(tmp_path / "candles.db"))
    res = CsvImporter(store).import_csv(csv, "BTC/USD", "15m", layout="cryptodatadownload")
    assert res["imported"] == 1 and res["skipped"] == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_csv_import.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.data.csv_import'`

- [ ] **Step 3: Implement the importer**

Create `src/swingbot/data/csv_import.py`:

```python
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
        total = len(raw)
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
```

(`imported` = bars successfully upserted; `skipped` = rows that failed to parse. `total` is unused beyond the loop and may be dropped if your linter complains.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_csv_import.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/data/csv_import.py tests/test_csv_import.py
git commit -m "feat(archive): add CsvImporter for bulk OHLCV dumps"
```

---

## Task 6: `ArchiveConfig` + `Backfiller`

**Files:**
- Create: `src/swingbot/data/backfill.py`
- Test: `tests/test_backfill.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_backfill.py`:

```python
import pandas as pd

from swingbot.data.backfill import ArchiveConfig, Backfiller
from swingbot.data.store import CandleStore


class _FakeProvider:
    """Serves canonical bars for a symbol/timeframe within [start_ms, end_ms]."""

    def __init__(self, bars_by_symbol):
        self.bars_by_symbol = bars_by_symbol      # {symbol: DataFrame(ts,o,h,l,c,v)}
        self.range_calls = []

    def get_candles_range(self, symbol, timeframe, start_ms, end_ms, page_limit=1000):
        self.range_calls.append((symbol, timeframe, start_ms, end_ms))
        df = self.bars_by_symbol.get(symbol)
        if df is None:
            return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
        ms = df["ts"].astype("int64") // 1_000_000
        return df[(ms >= start_ms) & (ms <= end_ms)].reset_index(drop=True)


def _bars(start, n):
    ts = pd.date_range(start, periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({"ts": ts, "open": range(n), "high": range(n),
                         "low": range(n), "close": range(n), "volume": range(n)})


def test_backfill_writes_bars_into_store(tmp_path):
    store = CandleStore(str(tmp_path / "candles.db"))
    prov = _FakeProvider({"BTC/USD": _bars("2024-06-01", 100)})
    cfg = ArchiveConfig(symbols=["BTC/USD"], timeframes=["15m"],
                        history_start="2024-06-01")
    written = Backfiller(store, provider=prov).run(cfg)
    assert written == 100
    assert store.coverage("BTC/USD", "15m")["count"] == 100


def test_backfill_is_idempotent_on_rerun(tmp_path):
    store = CandleStore(str(tmp_path / "candles.db"))
    prov = _FakeProvider({"BTC/USD": _bars("2024-06-01", 100)})
    cfg = ArchiveConfig(symbols=["BTC/USD"], timeframes=["15m"],
                        history_start="2024-06-01")
    bf = Backfiller(store, provider=prov)
    bf.run(cfg)
    second = bf.run(cfg)            # re-run over the same window
    assert second == 0             # nothing new written
    assert store.coverage("BTC/USD", "15m")["count"] == 100


def test_backfill_fills_only_the_missing_older_range(tmp_path):
    store = CandleStore(str(tmp_path / "candles.db"))
    full = _bars("2024-06-01", 100)
    # Pre-seed the store with the newest 40 bars only.
    store.upsert_df("BTC/USD", "15m", full.tail(40))
    prov = _FakeProvider({"BTC/USD": full})
    cfg = ArchiveConfig(symbols=["BTC/USD"], timeframes=["15m"],
                        history_start="2024-06-01")
    written = Backfiller(store, provider=prov).run(cfg)
    assert written == 60                       # only the older gap pulled
    assert store.coverage("BTC/USD", "15m")["count"] == 100


def test_config_defaults_are_sensible():
    cfg = ArchiveConfig()
    assert cfg.exchange == "binance"
    assert "BTC/USD" in cfg.symbols
    assert "15m" in cfg.timeframes
    assert cfg.history_start == "2024-06-01"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_backfill.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.data.backfill'`

- [ ] **Step 3: Implement config and backfiller**

Create `src/swingbot/data/backfill.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from swingbot.data.market import timeframe_seconds
from swingbot.data.store import CandleStore


def _default_symbols() -> list[str]:
    return ["BTC/USD", "ETH/USD", "SOL/USD"]


def _default_timeframes() -> list[str]:
    return ["5m", "15m", "1h"]


@dataclass
class ArchiveConfig:
    """Which markets to archive and how far back. CLI args / env override these."""
    exchange: str = "binance"
    symbols: list[str] = field(default_factory=_default_symbols)
    timeframes: list[str] = field(default_factory=_default_timeframes)
    history_start: str = "2024-06-01"     # ISO date; ~2y of depth by default
    quote_map: dict | None = None
    symbol_overrides: dict | None = None

    def start_ms(self) -> int:
        dt = datetime.fromisoformat(self.history_start).replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


class Backfiller:
    """Populate CandleStore with deep history. Coverage-driven and idempotent:
    on each (symbol, timeframe) it fetches only the ranges not already stored,
    so a re-run fills gaps and a crash mid-run is safe to resume."""

    def __init__(self, store: CandleStore, provider=None):
        self.store = store
        self.provider = provider

    def _missing_ranges(self, symbol: str, timeframe: str,
                        start_ms: int, end_ms: int) -> list[tuple[int, int]]:
        cov = self.store.coverage(symbol, timeframe)
        if not cov["count"]:
            return [(start_ms, end_ms)]
        min_ms = cov["min_ts"] * 1000
        max_ms = cov["max_ts"] * 1000
        ranges = []
        if start_ms < min_ms:
            ranges.append((start_ms, min_ms))      # older gap
        if end_ms > max_ms:
            ranges.append((max_ms, end_ms))        # newer gap (top-up)
        return ranges

    def run(self, cfg: ArchiveConfig, end_ms: int | None = None,
            log=print) -> int:
        end_ms = end_ms or _now_ms()
        start_ms = cfg.start_ms()
        total = 0
        for symbol in cfg.symbols:
            for tf in cfg.timeframes:
                for r_start, r_end in self._missing_ranges(symbol, tf, start_ms, end_ms):
                    df = self.provider.get_candles_range(symbol, tf, r_start, r_end)
                    written = self.store.upsert_df(symbol, tf, df)
                    total += written
                cov = self.store.coverage(symbol, tf)
                log(f"[backfill] {symbol} {tf}: {cov['count']} bars "
                    f"({cov['min_ts']} -> {cov['max_ts']})")
        return total
```

Note on `test_backfill_is_idempotent_on_rerun`: after the first run, `max_ts` equals the newest stored bar (2024-06-01 + 99 bars). The second run's "newer gap" `(max_ms, end_ms)` asks the fake for bars after that — none exist within the dataset — so `get_candles_range` returns empty and `written == 0`. The older gap is absent because `start_ms == min_ms`. ✔

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_backfill.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/data/backfill.py tests/test_backfill.py
git commit -m "feat(archive): add ArchiveConfig and coverage-driven Backfiller"
```

---

## Task 7: `swingbot-backfill` CLI

**Files:**
- Create: `src/swingbot/backfill_cli.py`
- Modify: `pyproject.toml` (add script)
- Test: `tests/test_backfill_cli.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_backfill_cli.py`:

```python
from swingbot.backfill_cli import build_parser, config_from_args


def test_parser_reads_ccxt_args():
    args = build_parser().parse_args(
        ["--exchange", "kraken", "--symbols", "BTC/USD,ETH/USD",
         "--timeframes", "15m,1h", "--start", "2023-01-01"])
    cfg = config_from_args(args)
    assert cfg.exchange == "kraken"
    assert cfg.symbols == ["BTC/USD", "ETH/USD"]
    assert cfg.timeframes == ["15m", "1h"]
    assert cfg.history_start == "2023-01-01"


def test_parser_defaults_match_archive_config():
    args = build_parser().parse_args([])
    cfg = config_from_args(args)
    assert cfg.exchange == "binance"
    assert "BTC/USD" in cfg.symbols


def test_csv_args_are_parsed():
    args = build_parser().parse_args(
        ["--csv", "/tmp/x.csv", "--symbol", "BTC/USD",
         "--timeframe", "15m", "--csv-layout", "binance"])
    assert args.csv == "/tmp/x.csv"
    assert args.symbol == "BTC/USD"
    assert args.timeframe == "15m"
    assert args.csv_layout == "binance"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_backfill_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.backfill_cli'`

- [ ] **Step 3: Implement the CLI**

Create `src/swingbot/backfill_cli.py`:

```python
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
```

- [ ] **Step 4: Register the script in pyproject.toml**

In `pyproject.toml`, under `[project.scripts]`, add the line:

```toml
swingbot-backfill = "swingbot.backfill_cli:main"
```

So the block reads:

```toml
[project.scripts]
swingbot-backtest = "swingbot.cli:main"
swingbot-run = "swingbot.run:main"
swingbot-web = "swingbot.webmain:main"
swingbot-backfill = "swingbot.backfill_cli:main"
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_backfill_cli.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add src/swingbot/backfill_cli.py pyproject.toml tests/test_backfill_cli.py
git commit -m "feat(archive): add swingbot-backfill CLI (CCXT + CSV modes)"
```

---

## Task 8: Archive API endpoints + webmain wiring

**Files:**
- Modify: `src/swingbot/web.py` (add `backfiller=None` param + two routes)
- Modify: `src/swingbot/webmain.py` (construct + pass a `Backfiller`)
- Test: `tests/test_web_archive.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_archive.py`:

```python
from datetime import datetime, timezone

import pandas as pd
from fastapi.testclient import TestClient

from swingbot.data.store import CandleStore
from swingbot.web import create_app


def _df(prices):
    rows = []
    for i, p in enumerate(prices):
        ts = pd.Timestamp(datetime(2024, 6, 1, tzinfo=timezone.utc)) + pd.Timedelta(minutes=15 * i)
        rows.append({"ts": ts, "open": p, "high": p + 1, "low": p - 1,
                     "close": p + 0.5, "volume": 100 + i})
    return pd.DataFrame(rows)


class _Ctl:
    def status(self): return {"mode": "paper", "running": False}
    def journal(self, strategy=None): return []
    def metrics(self, strategy=None): return {}


class _Profiles:
    def list_armed(self): return []
    def get(self, name): return {}


class _FakeBackfiller:
    def __init__(self):
        self.ran = False

    def run(self, cfg, end_ms=None, log=print):
        self.ran = True
        return 0


def test_status_reports_coverage(tmp_path):
    store = CandleStore(str(tmp_path / "candles.db"))
    store.upsert_df("BTC/USD", "15m", _df([10, 11, 12]))
    app = create_app(_Ctl(), _Profiles(), None, token="t", store=store)
    r = TestClient(app).get("/api/archive/status")
    assert r.status_code == 200
    body = r.json()
    entry = next(e for e in body if e["symbol"] == "BTC/USD" and e["timeframe"] == "15m")
    assert entry["count"] == 3
    assert entry["min_ts"] < entry["max_ts"]


def test_backfill_requires_token(tmp_path):
    store = CandleStore(str(tmp_path / "candles.db"))
    bf = _FakeBackfiller()
    app = create_app(_Ctl(), _Profiles(), None, token="t", store=store, backfiller=bf)
    c = TestClient(app)
    assert c.post("/api/archive/backfill").status_code == 401
    r = c.post("/api/archive/backfill", headers={"x-token": "t"})
    assert r.status_code == 200 and r.json()["started"] is True


def test_backfill_503_when_unconfigured(tmp_path):
    store = CandleStore(str(tmp_path / "candles.db"))
    app = create_app(_Ctl(), _Profiles(), None, token="t", store=store)  # no backfiller
    r = TestClient(app).post("/api/archive/backfill", headers={"x-token": "t"})
    assert r.status_code == 503
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_web_archive.py -v`
Expected: FAIL — `404` for the routes (and `TypeError` for the unexpected `backfiller` kwarg)

- [ ] **Step 3: Add the `backfiller` param and routes**

In `src/swingbot/web.py`, change the `create_app` signature (line 58) to add `backfiller=None`:

```python
def create_app(controller, profiles, creds, token: str, store=None, market=None, backfiller=None) -> FastAPI:
```

At the top of the file, add `import threading` (it has none yet) alongside the existing `import os` / `import pathlib`:

```python
import os
import pathlib
import threading
```

Then, immediately before the line `app.state.token = token` (currently line 260), insert the archive routes:

```python
    # ---- archive (deep historical backfill) ----
    @app.get("/api/archive/status")
    def archive_status():
        if store is None:
            return []
        out = []
        for entry in store.symbols():
            cov = store.coverage(entry["symbol"], entry["timeframe"])
            out.append({"symbol": entry["symbol"], "timeframe": entry["timeframe"],
                        **cov})
        return out

    @app.post("/api/archive/backfill")
    def archive_backfill(_=Depends(require_token)):
        if backfiller is None or getattr(app.state, "archive_config", None) is None:
            raise HTTPException(status_code=503,
                                detail="archive backfill is not configured on this server")
        cfg = app.state.archive_config

        def job():
            try:
                backfiller.run(cfg)
            except Exception as e:  # a backfill failure must never touch live trading
                print(f"[archive-backfill] {e}")

        threading.Thread(target=job, daemon=True).start()
        return {"started": True}
```

Note: the `test_backfill_requires_token` test passes a `backfiller` but no `app.state.archive_config`. Set a default so the route works when a backfiller is present: just below the inserted routes (still before `app.state.token = token`), add:

```python
    app.state.archive_config = None
    if backfiller is not None:
        from swingbot.data.backfill import ArchiveConfig
        app.state.archive_config = ArchiveConfig()
```

This makes `test_backfill_requires_token` (backfiller present → 200) and `test_backfill_503_when_unconfigured` (no backfiller → 503) both pass. webmain will override `app.state.archive_config` with the real config in Step 5.

- [ ] **Step 4: Run the archive web tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_web_archive.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Wire the backfiller into webmain**

In `src/swingbot/webmain.py`, add imports near the other `data` imports (after line 11):

```python
from swingbot.data.backfill import ArchiveConfig, Backfiller
from swingbot.data.ccxt_provider import CcxtProvider
```

Then, after `store = CandleStore(...)` (line 36) and before `market = MarketData(...)`, construct the archive components:

```python
    archive_cfg = ArchiveConfig()
    archive_provider = CcxtProvider(exchange_id=archive_cfg.exchange,
                                    quote_map=archive_cfg.quote_map,
                                    symbol_overrides=archive_cfg.symbol_overrides)
    backfiller = Backfiller(store, provider=archive_provider)
```

Change the `create_app(...)` call (line 43-44) to pass the backfiller:

```python
    app = create_app(controller=supervisor, profiles=profiles, creds=creds,
                     token=token, store=store, market=market, backfiller=backfiller)
    app.state.archive_config = archive_cfg
```

- [ ] **Step 6: Confirm webmain imports cleanly**

Run: `.venv/bin/python -c "import swingbot.webmain"`
Expected: no output, no traceback

- [ ] **Step 7: Commit**

```bash
git add src/swingbot/web.py src/swingbot/webmain.py tests/test_web_archive.py
git commit -m "feat(archive): add /api/archive status + backfill endpoints and wire webmain"
```

---

## Task 9: Network-gated live smoke test + full-suite verification

**Files:**
- Create: `tests/test_ccxt_network.py` (skipped by default, mirrors the 4 skipped Alpaca tests)

- [ ] **Step 1: Add an opt-in live smoke test**

Create `tests/test_ccxt_network.py`:

```python
import os

import pytest

from swingbot.data.ccxt_provider import CcxtProvider

pytestmark = pytest.mark.skipif(
    os.environ.get("SWINGBOT_LIVE_CCXT") != "1",
    reason="set SWINGBOT_LIVE_CCXT=1 to run live CCXT smoke tests (hits the network)")


def test_live_range_fetch_returns_real_bars():
    p = CcxtProvider(exchange_id="binance")
    # ~2 days of 15m bars ending now; just prove pagination + mapping work live.
    import time
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - 2 * 24 * 60 * 60 * 1000
    df = p.get_candles_range("BTC/USD", "15m", start_ms, end_ms)
    assert len(df) > 100
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume"]
```

- [ ] **Step 2: Confirm it is skipped (no network in CI)**

Run: `.venv/bin/python -m pytest tests/test_ccxt_network.py -v`
Expected: `1 skipped` (reason mentions `SWINGBOT_LIVE_CCXT`)

- [ ] **Step 3: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: `224 passed, 5 skipped` (baseline 207 passed + 17 new unit tests; baseline 4 skipped + 1 new network skip). If the counts differ, reconcile before continuing — do not proceed with failures.

- [ ] **Step 4: Commit**

```bash
git add tests/test_ccxt_network.py
git commit -m "test(archive): add opt-in live CCXT smoke test (skipped by default)"
```

---

## Task 10: Manual end-to-end verification (success criteria)

This task is **manual** — it exercises the live network path and the real `~/.swingbot/candles.db`, proving the spec's success criteria. It writes to the real store; that is intended (deep history is the deliverable).

- [ ] **Step 1: Run a real backfill of BTC/USD 15m**

Run: `.venv/bin/python -m swingbot.backfill_cli --exchange binance --symbols BTC/USD --timeframes 15m --start 2024-06-01`
Expected: prints `[backfill] BTC/USD 15m: <tens of thousands> bars (...)` and a final `done: N new bars` line.

- [ ] **Step 2: Confirm coverage via the store**

Run:
```bash
.venv/bin/python -c "from swingbot.data.store import CandleStore; import os; \
s=CandleStore(os.path.expanduser('~/.swingbot/candles.db')); \
print(s.coverage('BTC/USD','15m'))"
```
Expected: `count` in the tens of thousands; `min_ts` ≈ 2024-06-01 epoch, `max_ts` ≈ now.

- [ ] **Step 3: Confirm idempotency**

Re-run the exact command from Step 1.
Expected: the final line reports `~0 new bars` (only a small top-up of bars formed since the first run, if any).

- [ ] **Step 4: Confirm a backtest now runs on deep history (no engine change)**

Run a preset backtest over the now-deep store and compare against the old ~11-trades/5-days window:
```bash
.venv/bin/python -c "
from swingbot.data.store import CandleStore
from swingbot.data.market import MarketData
from swingbot.strategy_search import backtest_profile
from swingbot.presets import archetype_profile, BUILTIN_ARCHETYPES
import os
store = CandleStore(os.path.expanduser('~/.swingbot/candles.db'))
market = MarketData(store, creds=None)   # creds=None -> never refetches; reads the deep store
prof = archetype_profile(BUILTIN_ARCHETYPES[0], 'BTC/USD', 'swing')
res = backtest_profile(market, prof, lookback=5000)
print('n_trades=', res.get('n_trades'), 'metrics=', res)
"
```
Expected: `n_trades` and the covered date span are materially larger than today's ~11 trades over ~5 days. **`backtest.py` and `strategy_search.py` were not modified** — confirm with `git diff --stat HEAD~9 -- src/swingbot/backtest.py src/swingbot/strategy_search.py` shows no changes to those two files.

If `BUILTIN_ARCHETYPES` / `archetype_profile` arguments differ from the above, adjust to the real `presets.py` API discovered during Task 6 — the intent is "run any existing preset backtest and show more trades over a longer span."

- [ ] **Step 5: (Optional) Confirm the status endpoint**

If running the web server, `GET /api/archive/status` (with `x-token`) should list `BTC/USD 15m` with the deep `min_ts → max_ts` coverage.

---

## Self-Review (completed during planning)

**Spec coverage:**
- `CcxtProvider` (Protocol impl, `get_candles_range`, symbol/timeframe mapping, config) → Tasks 3–4. ✔
- `CsvImporter` (two layouts, malformed-row skipping, count) → Task 5. ✔
- `Backfiller` (orchestration, idempotent/resumable via coverage, progress) → Task 6. ✔
- `CandleStore.coverage` → Task 1. ✔
- CLI `swingbot-backfill` (`--exchange/--symbols/--timeframes/--start/--csv/--symbol/--timeframe`) + pyproject script → Task 7. ✔
- API `POST /api/archive/backfill` (bg thread) + `GET /api/archive/status` → Task 8. ✔
- `archive` config section (exchange, symbols, timeframes, history_start; defaults binance / `[5m,15m,1h]` / 2024-06-01) → `ArchiveConfig` in Task 6, wired in Tasks 7–8. ✔
- Error handling (rate limit via `enableRateLimit`, skip bad CSV rows, idempotent resume, backfill isolated from live loop via daemon thread) → Tasks 3/5/6/8. ✔
- Testing (mocked ccxt, CSV layouts, idempotency, coverage; no reference-parity) → Tasks 1/4/5/6. ✔
- Success criteria (deep BTC/USD 15m, status coverage, idempotent re-run, deeper backtest with no engine change, suite green) → Tasks 9–10. ✔
- Out of scope (windowed backtests, UI panel, scheduled top-ups) → not built. ✔

**Type consistency:** `ArchiveConfig` fields (`exchange`, `symbols`, `timeframes`, `history_start`, `quote_map`, `symbol_overrides`, `start_ms()`) are used identically in `Backfiller`, the CLI, and webmain. `CcxtProvider.get_candles_range(symbol, timeframe, start_ms, end_ms, page_limit)` matches the fake provider and `Backfiller` call sites. `store.coverage(...) -> {min_ts, max_ts, count}` (epoch seconds) is consumed consistently (`*1000` only inside `Backfiller._missing_ranges`). Canonical df columns `[ts, open, high, low, close, volume]` with UTC-Timestamp `ts` are produced by both `CcxtProvider._rows_to_df` and `CsvImporter` and accepted by `CandleStore.upsert_df`.

**Placeholder scan:** No `TBD`/`handle edge cases`/"similar to Task N". Two intentional in-line corrections (the deliberately-wrong `skipped` expression in Task 5 and the now()-based `get_candles` test note in Task 4) are spelled out with the exact replacement code.
