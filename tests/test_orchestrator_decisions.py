from datetime import datetime, timezone

import numpy as np
import pandas as pd

from swingbot.journal import TradeJournal
from swingbot.orchestrator import Orchestrator
from swingbot.portfolio_risk import PortfolioDecision
from swingbot.profile import StrategyProfile
from swingbot.risk import RiskDecision, RiskManager
from swingbot.state import StateStore
from swingbot.types import (
    BrokerOrder,
    ConfluenceResult,
    DecisionCode,
    OrderSide,
    OrderStatus,
    Regime,
    RegimeResult,
)

T0 = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


class Data:
    def __init__(self):
        closes = np.array(list(np.linspace(100, 130, 80)) + list(np.linspace(130, 118, 6)))
        self.frame = pd.DataFrame({
            "ts": pd.date_range(end=T0, periods=len(closes), freq="15min", tz="UTC"),
            "open": closes, "high": closes * 1.002, "low": closes * 0.998,
            "close": closes, "volume": np.full(len(closes), 100.0),
        })

    def get_candles(self, *args, **kwargs):
        return self.frame

    def get_latest_price(self, symbol):
        return float(self.frame["close"].iloc[-1])


class Broker:
    def __init__(self):
        self.position = None
        self.submit_error = None

    def get_account(self):
        return {"equity": 1000.0, "cash": 1000.0, "buying_power": 1000.0}

    def get_position(self, symbol):
        return self.position

    def get_order(self, order_id=None, client_order_id=None):
        return None

    def submit_market_buy(self, symbol, qty, client_order_id):
        if self.submit_error:
            raise self.submit_error
        return BrokerOrder(
            "buy-1", symbol, OrderSide.BUY, OrderStatus.NEW, qty, 0.0, None, client_order_id
        )

    def submit_market_sell(self, symbol, qty, client_order_id):
        return BrokerOrder(
            "sell-1", symbol, OrderSide.SELL, OrderStatus.NEW, qty, 0.0, None, client_order_id
        )


def _profile():
    return StrategyProfile.from_dict({
        "symbol": "TRX/USD", "timeframe": "15m",
        "signals": {"oversold": {"weight": 1.0, "oversold_level": 45, "period": 14}},
        "entry_threshold": 0.25, "regime_ma_period": 50, "atr_period": 14,
        "stop_atr_mult": 2.0, "take_profit_atr_mult": 2.0,
        "max_hold_bars": 32, "risk_per_trade": 0.02,
    })


def _orch(tmp_path, portfolio_gate=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    profile = _profile()
    state = StateStore(str(tmp_path / "state.db"))
    return Orchestrator(
        profile, Data(), Broker(), state, RiskManager(profile, state.load_risk_state()),
        TradeJournal(), portfolio_gate=portfolio_gate,
    )


def test_entry_gate_decision_codes_are_stable(tmp_path, monkeypatch):
    orch = _orch(tmp_path)
    orch.paused = True
    assert orch._maybe_enter(T0, 1000).code is DecisionCode.PAUSED
    orch.paused = False
    orch.halted = True
    assert orch._maybe_enter(T0, 1000).code is DecisionCode.HALTED
    orch.halted = False
    orch.broker.position = {"symbol": "TRX/USD"}
    assert orch._maybe_enter(T0, 1000).code is DecisionCode.BROKER_POSITION_EXISTS
    orch.broker.position = None
    monkeypatch.setattr(
        orch.risk, "check_can_enter", lambda *args, **kwargs: RiskDecision(False, "blocked")
    )
    assert orch._maybe_enter(T0, 1000).code is DecisionCode.RISK_BLOCKED


def test_strategy_and_portfolio_gate_decision_codes_are_stable(tmp_path, monkeypatch):
    orch = _orch(tmp_path)
    monkeypatch.setattr(
        orch.regime, "evaluate", lambda ctx: RegimeResult(Regime.DOWNTREND)
    )
    assert orch._maybe_enter(T0, 1000).code is DecisionCode.REGIME_BLOCKED

    orch = _orch(tmp_path / "signal")
    monkeypatch.setattr(
        orch.engine,
        "evaluate",
        lambda ctx: ConfluenceResult(0.1, 0.25, False, {}, {}),
    )
    assert orch._maybe_enter(T0, 1000).code is DecisionCode.SIGNAL_BELOW_THRESHOLD

    orch = _orch(tmp_path / "atr")
    with monkeypatch.context() as context:
        context.setattr("swingbot.orchestrator.atr", lambda *args, **kwargs: pd.Series([0.0]))
        assert orch._maybe_enter(T0, 1000).code is DecisionCode.ATR_INVALID

    orch = _orch(tmp_path / "size")
    monkeypatch.setattr(orch.risk, "size", lambda **kwargs: 0.0)
    assert orch._maybe_enter(T0, 1000).code is DecisionCode.SIZE_ZERO

    orch = _orch(tmp_path / "portfolio", lambda *args: PortfolioDecision(False, "cap"))
    assert orch._maybe_enter(T0, 1000).code is DecisionCode.PORTFOLIO_BLOCKED


def test_tick_and_flatten_return_decision_results(tmp_path):
    orch = _orch(tmp_path)
    result = orch.tick(T0)
    assert result.code is DecisionCode.ORDER_SUBMITTED
    assert orch.flatten(T0).code is DecisionCode.ORDER_PENDING
    assert _orch(tmp_path / "flat").flatten(T0).code is DecisionCode.MANAGED_NO_EXIT


def test_ambiguous_submission_failure_returns_error_and_keeps_intent(tmp_path):
    orch = _orch(tmp_path)
    orch.broker.submit_error = TimeoutError("timed out")

    result = orch.tick(T0)

    assert result.code is DecisionCode.ERROR
    assert orch.state.load_pending_order() is not None
