import numpy as np
import pandas as pd

from swingbot.autodash.config import AutoDashConfig
from swingbot.autodash.service import AutoDashboardService


def _candles(n=120):
    base = np.linspace(100.0, 120.0, n)
    return pd.DataFrame({
        "ts": np.arange(n, dtype=np.int64) * 300 + 1781265600,
        "open": base, "high": base + 1, "low": base - 1,
        "close": base + 0.5, "volume": np.ones(n)})


def _service(tmp_path, calls):
    cfg = AutoDashConfig(core_engine_data=str(tmp_path),
                         history_db=str(tmp_path / "hist.db"))

    def comparison_fn(candles, **kw):
        calls.append("ran")
        return {"ema": {"n_trades": 1}, "kronos": {"n_trades": 1}}

    return AutoDashboardService(cfg, comparison_fn=comparison_fn,
                                kronos_factory=lambda: None,
                                candle_loader=lambda cfg: _candles())


def test_backtest_runs_once_and_caches(tmp_path):
    calls = []
    svc = _service(tmp_path, calls)
    a = svc.backtest()
    b = svc.backtest()
    assert a == b and set(a) == {"ema", "kronos"}
    assert calls == ["ran"]                 # computed exactly once


def test_live_reads_return_empty_when_dbs_absent(tmp_path):
    svc = _service(tmp_path, [])
    assert svc.position() is None
    assert svc.trades() == []
    assert svc.journal() == []
    assert svc.candles() == []


def test_backtest_returns_pending_placeholder_while_computing(tmp_path):
    # Hold the lock to simulate an in-progress prewarm; backtest() must NOT block and
    # must return a valid pending placeholder instead.
    calls = []
    svc = _service(tmp_path, calls)
    svc._lock.acquire()
    try:
        out = svc.backtest()
    finally:
        svc._lock.release()
    assert set(out) == {"ema", "kronos"}
    assert out["ema"]["pending"] is True
    assert out["ema"]["equity_curve"] == []
    assert calls == []                          # did not compute while locked
    assert svc.backtest_ready() is False


def test_default_candle_loader_adds_tzaware_ts(tmp_path):
    # The Kronos adapter reads a tz-aware 'ts' column; the loader must derive it from
    # CandleStore's epoch-seconds 'time'.
    import sqlite3
    from swingbot.autodash.service import _default_candle_loader

    db = str(tmp_path / "hist.db")
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE bars (symbol TEXT, timeframe TEXT, ts INTEGER, "
              "open REAL, high REAL, low REAL, close REAL, volume REAL, "
              "PRIMARY KEY (symbol, timeframe, ts))")
    c.executemany("INSERT INTO bars VALUES (?,?,?,?,?,?,?,?)", [
        ("BTC/USD", "15m", 1781265600, 1, 2, 0, 1.5, 1.0),
        ("BTC/USD", "15m", 1781266500, 1.5, 2, 1, 1.8, 1.0)])
    c.commit()
    c.close()

    cfg = AutoDashConfig(core_engine_data=str(tmp_path), history_db=db,
                         backtest_timeframe="15m")
    rows = _default_candle_loader(cfg)
    assert len(rows) == 2
    assert all(getattr(r["ts"], "tzinfo", None) is not None for r in rows)
    assert rows[0]["ts"] == pd.Timestamp(1781265600, unit="s", tz="UTC")
