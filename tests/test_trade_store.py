from datetime import datetime, timezone

from swingbot.journal import Trade, TradeJournal
from swingbot.metrics import compute_metrics
from swingbot.trade_store import TradeStore
from swingbot.types import ExitReason, Regime, Side


def _trade(pnl=5.0, hour=1):
    return Trade(
        entry_ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        exit_ts=datetime(2026, 1, 1, hour, tzinfo=timezone.utc),
        side=Side.LONG,
        entry_price=100.0,
        exit_price=100.0 + pnl,
        qty=1.0,
        pnl=pnl,
        exit_reason=ExitReason.TAKE_PROFIT if pnl > 0 else ExitReason.STOP,
        score_at_entry=0.7,
        regime_at_entry=Regime.UPTREND,
    )


def test_trade_records_roundtrip_and_filter_by_strategy(tmp_path):
    store = TradeStore(str(tmp_path / "state.db"))
    btc = _trade(5.0, hour=1)
    eth = _trade(-2.0, hour=2)

    store.record("btc", btc, symbol="BTC/USD", entry_order_id="b1", exit_order_id="s1")
    store.record("eth", eth, symbol="ETH/USD", entry_order_id="b2", exit_order_id="s2")

    assert store.list(strategy="btc") == [btc]
    assert store.list(strategy="eth") == [eth]
    assert store.list() == [btc, eth]


def test_trade_record_survives_reopen(tmp_path):
    path = str(tmp_path / "state.db")
    expected = _trade()
    store = TradeStore(path)
    store.record("btc", expected, symbol="BTC/USD", entry_order_id="b1", exit_order_id="s1")
    store.close()

    assert TradeStore(path).list(strategy="btc") == [expected]


def test_duplicate_exit_order_id_is_idempotent(tmp_path):
    store = TradeStore(str(tmp_path / "state.db"))
    first = _trade(5.0)
    store.record("btc", first, symbol="BTC/USD", entry_order_id="b1", exit_order_id="s1")

    store.record(
        "btc", _trade(999.0), symbol="BTC/USD", entry_order_id="b1", exit_order_id="s1"
    )

    assert store.list(strategy="btc") == [first]


def test_durable_journal_exposes_trades_written_before_it_was_created(tmp_path):
    store = TradeStore(str(tmp_path / "state.db"))
    expected = _trade()
    store.record("btc", expected, symbol="BTC/USD", entry_order_id="b1", exit_order_id="s1")

    journal = TradeJournal(store=store, strategy="btc")

    assert journal.trades == [expected]


def test_durable_journal_record_delegates_to_store(tmp_path):
    store = TradeStore(str(tmp_path / "state.db"))
    journal = TradeJournal(store=store, strategy="btc")
    expected = _trade()

    journal.record(
        expected,
        symbol="BTC/USD",
        entry_order_id="b1",
        exit_order_id="s1",
    )

    assert store.list(strategy="btc") == [expected]


def test_metrics_are_identical_after_trade_store_restart(tmp_path):
    path = str(tmp_path / "state.db")
    store = TradeStore(path)
    store.record("btc", _trade(5.0, 1), symbol="BTC/USD", entry_order_id="b1", exit_order_id="s1")
    store.record("btc", _trade(-2.0, 2), symbol="BTC/USD", entry_order_id="b2", exit_order_id="s2")
    before = compute_metrics(TradeJournal(store=store, strategy="btc").trades)
    store.close()

    after = compute_metrics(TradeJournal(store=TradeStore(path), strategy="btc").trades)

    assert after == before
