from datetime import datetime, timezone

from swingbot.types import (
    BrokerOrder,
    DecisionCode,
    DecisionResult,
    OrderSide,
    OrderStatus,
    PendingOrder,
    Regime,
)


def test_decision_codes_match_phase3_api_contract():
    assert {code.value for code in DecisionCode} == {
        "PAUSED",
        "HALTED",
        "BROKER_POSITION_EXISTS",
        "RISK_BLOCKED",
        "REGIME_BLOCKED",
        "GATE_BLOCKED",
        "SIGNAL_BELOW_THRESHOLD",
        "ATR_INVALID",
        "SIZE_ZERO",
        "PORTFOLIO_BLOCKED",
        "ORDER_SUBMITTED",
        "ORDER_PENDING",
        "ENTERED",
        "ORDER_FAILED",
        "MANAGED_NO_EXIT",
        "EXIT_SUBMITTED",
        "EXITED",
        "IDLE",
        "ERROR",
    }


def test_decision_result_defaults_to_empty_details():
    result = DecisionResult(DecisionCode.PAUSED, "operator paused entries")
    assert result.details == {}


def test_pending_order_carries_restart_safe_entry_context():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    pending = PendingOrder(
        client_order_id="swingbot-btc-001",
        broker_order_id=None,
        symbol="BTC/USD",
        side=OrderSide.BUY,
        submitted_at=now,
        requested_qty=0.1,
        stop=90.0,
        tp=120.0,
        max_hold_until=now,
        score_at_entry=0.7,
        regime_at_entry=Regime.UPTREND,
    )
    assert pending.side is OrderSide.BUY


def test_broker_order_exposes_normalized_fill_truth():
    order = BrokerOrder(
        order_id="buy-1",
        symbol="BTC/USD",
        side=OrderSide.BUY,
        status=OrderStatus.PARTIALLY_FILLED,
        requested_qty=1.0,
        filled_qty=0.4,
        filled_avg_price=101.0,
    )
    assert order.status is OrderStatus.PARTIALLY_FILLED
