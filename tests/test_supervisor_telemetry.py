from datetime import timedelta

from swingbot.journal import Trade
from swingbot.types import (
    DecisionCode,
    ExitReason,
    OpenPosition,
    Regime,
    Side,
)
from tests.test_supervisor import T0, _supervisor


def _position(symbol="BTC/USD"):
    return OpenPosition(
        symbol=symbol,
        entry_ts=T0,
        entry_price=100.0,
        qty=1.0,
        stop=90.0,
        tp=120.0,
        max_hold_until=T0 + timedelta(hours=8),
        score_at_entry=0.7,
        regime_at_entry=Regime.UPTREND,
        side=Side.LONG,
        entry_order_id="buy-1",
    )


def _trade():
    return Trade(
        entry_ts=T0,
        exit_ts=T0 + timedelta(hours=1),
        side=Side.LONG,
        entry_price=100.0,
        exit_price=105.0,
        qty=1.0,
        pnl=5.0,
        exit_reason=ExitReason.TAKE_PROFIT,
        score_at_entry=0.7,
        regime_at_entry=Regime.UPTREND,
    )


def test_tick_all_writes_one_distinct_terminal_record_per_strategy(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD", "ETH/USD"])

    sup.tick_all(T0)

    rows = sup._telemetry.recent(limit=10)
    assert {row.strategy for row in rows} == {"btc", "eth"}
    assert len({row.cycle_id for row in rows}) == 2
    assert all(row.completed_at is not None for row in rows)


def test_confirmed_flat_cycle_requires_decide_and_skips_manage(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD"])

    sup.tick_all(T0)

    row = sup._telemetry.recent(strategy="btc")[0]
    assert row.manage == "skipped"
    assert row.decide == "ok"


def test_confirmed_position_cycle_requires_manage_and_skips_decide(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD"])
    sup._store.save_position(_position(), strategy="btc")
    broker.positions["BTC/USD"] = {
        "symbol": "BTC/USD", "qty": 1.0, "avg_entry_price": 100.0, "market_value": 100.0,
    }

    sup.tick_all(T0)

    row = sup._telemetry.recent(strategy="btc")[0]
    assert row.manage == "ok"
    assert row.decide == "skipped"


def test_warm_failure_records_ingest_failure_and_submits_no_order(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD"])
    market.refresh_many = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("warm failed"))

    sup.tick_all(T0)

    row = sup._telemetry.recent(strategy="btc")[0]
    assert row.ingest == "failed"
    assert row.decision_code is DecisionCode.ERROR
    assert broker.buys == []


def test_between_bars_idle_is_not_an_error(tmp_path):
    # Five minutes past the last close: outside the act-now window but the latest
    # closed bar is still the current one. This is healthy idle, not an error: it
    # must not be an ERROR, must not tank the ingest reliability, and must place
    # no order (the bot only acts once per freshly-closed bar).
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD"])

    sup.tick_all(T0 + timedelta(minutes=5))

    row = sup._telemetry.recent(strategy="btc")[0]
    assert row.decision_code is DecisionCode.IDLE
    assert row.ingest == "ok"
    assert row.decide == "skipped"
    assert broker.buys == []


def test_provider_fallen_a_full_bar_behind_records_error(tmp_path):
    # 40 minutes past the last bar: the provider has missed a full bar — genuinely
    # stale data, which should still surface as an ERROR.
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD"])

    sup.tick_all(T0 + timedelta(minutes=40))

    row = sup._telemetry.recent(strategy="btc")[0]
    assert row.ingest == "failed"
    assert row.decision_code is DecisionCode.ERROR
    assert broker.buys == []


def test_reconcile_exception_records_failure_and_preserves_position(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD"])
    position = _position()
    sup._store.save_position(position, strategy="btc")
    orch = sup._strategies["btc"]["orch"]
    orch.reconcile = lambda now: (_ for _ in ()).throw(RuntimeError("reconcile failed"))

    sup.tick_all(T0)

    row = sup._telemetry.recent(strategy="btc")[0]
    assert row.reconcile == "failed"
    assert row.decision_code is DecisionCode.ERROR
    assert sup._store.load_position("btc") == position


def test_decide_exception_records_failed_required_stage(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD"])
    orch = sup._strategies["btc"]["orch"]
    orch.tick = lambda now: (_ for _ in ()).throw(RuntimeError("decide failed"))

    sup.tick_all(T0)

    row = sup._telemetry.recent(strategy="btc")[0]
    assert row.manage == "skipped"
    assert row.decide == "failed"
    assert row.decision_code is DecisionCode.ERROR


def test_manage_exception_records_failed_required_stage(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD"])
    sup._store.save_position(_position(), strategy="btc")
    broker.positions["BTC/USD"] = {
        "symbol": "BTC/USD", "qty": 1.0, "avg_entry_price": 100.0, "market_value": 100.0,
    }
    orch = sup._strategies["btc"]["orch"]
    orch.tick = lambda now: (_ for _ in ()).throw(RuntimeError("manage failed"))

    sup.tick_all(T0)

    row = sup._telemetry.recent(strategy="btc")[0]
    assert row.manage == "failed"
    assert row.decide == "skipped"
    assert row.decision_code is DecisionCode.ERROR


def test_final_portfolio_write_exception_records_persist_failed(tmp_path, monkeypatch):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD"])
    monkeypatch.setattr(
        sup._store,
        "save_portfolio_risk_state",
        lambda state: (_ for _ in ()).throw(RuntimeError("persist failed")),
    )

    sup.tick_all(T0)

    row = sup._telemetry.recent(strategy="btc")[0]
    assert row.persist == "failed"
    assert row.decision_code is DecisionCode.ERROR


def test_in_progress_bar_is_excluded_and_bar_ts_is_latest_closed(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD"])

    sup.tick_all(T0)

    row = sup._telemetry.recent(strategy="btc")[0]
    assert row.bar_ts == T0 - timedelta(minutes=15)


def test_persisted_exception_reason_is_sanitized_and_capped(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD"])
    orch = sup._strategies["btc"]["orch"]
    orch.tick = lambda now: (_ for _ in ()).throw(RuntimeError("bad\nreason\0" + "x" * 600))

    sup.tick_all(T0)

    reason = sup._telemetry.recent(strategy="btc")[0].decision_reason
    assert "\n" not in reason
    assert "\0" not in reason
    assert len(reason) <= 500


def test_journal_and_metrics_read_durable_trades_after_rebuild(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD"])
    sup._trade_store.record(
        "btc", _trade(), symbol="BTC/USD", entry_order_id="buy-1", exit_order_id="sell-1"
    )

    sup.build()

    assert sup.journal("btc")[0]["pnl"] == 5.0
    assert sup.metrics("btc")["n_trades"] == 1
