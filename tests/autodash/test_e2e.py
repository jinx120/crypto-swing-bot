import json
import sqlite3

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from swingbot.autodash import AutoDashConfig, AutoDashboardService
from swingbot.web import create_app


class _Ctl:
    def status(self): return {}
    def journal(self, s=None): return []
    def metrics(self, s=None): return {}
    def readiness(self): return {}
    def trading_health(self): return {}


def _seed(tmp_path):
    j = sqlite3.connect(str(tmp_path / "journal.db"))
    j.execute("CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
              "ts TEXT, kind TEXT, symbol TEXT, reason TEXT, payload TEXT)")
    j.execute("INSERT INTO events (ts,kind,symbol,reason,payload) VALUES (?,?,?,?,?)",
              ("2026-06-17T18:30:00+00:00", "pnl", "BTC/USD", "closed: tp",
               json.dumps({"realized": 7.0, "won": True})))
    j.commit(); j.close()
    s = sqlite3.connect(str(tmp_path / "state.db"))
    s.execute("CREATE TABLE runtime_state (key TEXT PRIMARY KEY, value TEXT)")
    s.commit(); s.close()
    c = sqlite3.connect(str(tmp_path / "candles.db"))
    c.execute("CREATE TABLE bars (symbol TEXT, timeframe TEXT, ts INTEGER, "
              "open REAL, high REAL, low REAL, close REAL, volume REAL, "
              "PRIMARY KEY (symbol, timeframe, ts))")
    c.execute("INSERT INTO bars VALUES ('BTC/USD','5m',1781265600,1,2,0,1.5,1.0)")
    c.commit(); c.close()


def _candle_loader(_cfg):
    n = 120
    base = np.linspace(100.0, 120.0, n)
    return pd.DataFrame({
        "ts": np.arange(n, dtype=np.int64) * 300 + 1781265600,
        "open": base, "high": base + 1, "low": base - 1,
        "close": base + 0.5, "volume": np.ones(n)})


def test_full_stack_six_routes(tmp_path):
    _seed(tmp_path)
    cfg = AutoDashConfig(core_engine_data=str(tmp_path),
                         history_db=str(tmp_path / "candles.db"))
    svc = AutoDashboardService(cfg, kronos_factory=lambda: None,
                               candle_loader=_candle_loader)
    app = create_app(controller=_Ctl(), profiles=None, creds=None,
                     token="t", auto_dashboard=svc)
    c = TestClient(app)

    for path in ("/api/backtest/ema", "/api/backtest/kronos"):
        body = c.get(path).json()
        assert set(body) == {"n_trades", "win_rate", "total_pnl",
                             "sharpe", "final_equity", "equity_curve"}
    assert c.get("/api/live/position").json() is None
    assert c.get("/api/live/trades").json()[0]["pnl"] == 7.0
    assert c.get("/api/live/journal").json()[0]["kind"] == "pnl"
    assert c.get("/api/live/candles").json()[0]["time"] == 1781265600
