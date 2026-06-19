import os
from swingbot.autodash.config import AutoDashConfig


def test_default_resolves_core_engine_db_paths():
    cfg = AutoDashConfig.default()
    assert cfg.symbol == "BTC/USD"
    assert cfg.timeframe == "5m"
    assert cfg.backtest_timeframe == "15m"
    assert cfg.journal_db.endswith("/journal.db")
    assert cfg.state_db.endswith("/state.db")
    assert cfg.candle_db.endswith("/candles.db")
    assert os.path.basename(os.path.dirname(cfg.journal_db)) == ".core-engine"


def test_explicit_data_dir_overrides_paths():
    cfg = AutoDashConfig(core_engine_data="/tmp/ce", history_db="/tmp/h.db")
    assert cfg.journal_db == "/tmp/ce/journal.db"
    assert cfg.candle_db == "/tmp/ce/candles.db"
