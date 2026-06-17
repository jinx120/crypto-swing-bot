from datetime import datetime, timezone
import pandas as pd
from swingbot.data.store import CandleStore
from swingbot.exits import exit_decision
from swingbot.risk import RiskManager, RiskState
from core_engine.journal import EngineJournal
from core_engine.loop import Engine
from core_engine.config import PROFILE, SYMBOL, TIMEFRAME
from tests.conftest import FakeBroker, FakeKronos


class _Fetcher:
    def fetch(self, symbol, timeframe):
        return None  # candles pre-seeded; no live fetch in test


class _RT:
    def get_running_desired(self): return True
    def set_running_desired(self, v): pass


def _seed(store):
    closes = [100 + i * 0.5 for i in range(80)]
    df = pd.DataFrame({
        "ts": pd.date_range("2026-06-17", periods=80, freq="5min", tz="UTC"),
        "open": closes, "high": [c + 0.4 for c in closes],
        "low": [c - 0.4 for c in closes], "close": closes, "volume": [9.0] * 80,
    })
    store.upsert_df(SYMBOL, TIMEFRAME, df)


def test_one_tick_never_raises_and_journals(tmp_path):
    store = CandleStore(str(tmp_path / "c.db")); _seed(store)
    journal = EngineJournal(str(tmp_path / "j.db"))
    risk = RiskManager(PROFILE, RiskState())
    eng = Engine(store=store, fetcher=_Fetcher(), broker=FakeBroker(),
                 journal=journal, risk=risk, runtime_state=_RT(),
                 profile=PROFILE, kronos=FakeKronos(0.95))
    eng.tick(datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc))
    assert len(journal.events()) >= 1  # at minimum a decision was journaled


def test_tick_swallows_stage_errors(tmp_path):
    store = CandleStore(str(tmp_path / "c.db"))  # empty -> build_context will fail
    journal = EngineJournal(str(tmp_path / "j.db"))
    eng = Engine(store=store, fetcher=_Fetcher(), broker=FakeBroker(),
                 journal=journal, risk=RiskManager(PROFILE, RiskState()),
                 runtime_state=_RT(), profile=PROFILE, kronos=FakeKronos(0.1))
    eng.tick(datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc))  # must not raise
    assert any(e.kind == "error" for e in journal.events())


def test_tick_adopts_live_position_without_immediate_exit(tmp_path):
    store = CandleStore(str(tmp_path / "c.db")); _seed(store)
    journal = EngineJournal(str(tmp_path / "j.db"))
    broker = FakeBroker(position={
        "symbol": SYMBOL,
        "qty": 0.02,
        "avg_entry_price": 139.5,
    })
    eng = Engine(store=store, fetcher=_Fetcher(), broker=broker,
                 journal=journal, risk=RiskManager(PROFILE, RiskState()),
                 runtime_state=_RT(), profile=PROFILE, kronos=FakeKronos(0.1))

    eng.tick(datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc))

    assert eng.position is not None
    assert broker.get_position(SYMBOL) is not None
    assert not [order for order in broker.orders if order.startswith("sell-")]


def test_exit_decision_ignores_missing_time_cap():
    assert exit_decision(
        stop=95.0,
        tp=105.0,
        max_hold_until=None,
        high=100.0,
        low=100.0,
        close=100.0,
        now=datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc),
    ) is None
