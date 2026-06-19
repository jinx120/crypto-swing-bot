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
