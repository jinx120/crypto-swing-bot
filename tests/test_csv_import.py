
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
