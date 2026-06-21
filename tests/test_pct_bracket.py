from datetime import datetime, timezone

import numpy as np
import pandas as pd

from swingbot.exits import pct_bracket_levels
from swingbot.journal import TradeJournal
from swingbot.orchestrator import Orchestrator
from swingbot.profile import StrategyProfile
from swingbot.risk import RiskManager
from swingbot.state import StateStore
from swingbot.types import (
    BrokerOrder,
    ConfluenceResult,
    DecisionCode,
    OrderSide,
    OrderStatus,
    Regime,
    RegimeResult,
    SignalResult,
)

NOW = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


def test_pct_bracket_levels():
    stop, tp = pct_bracket_levels(100.0, tp_pct=0.015, sl_pct=0.01)
    assert round(tp, 6) == 101.5
    assert round(stop, 6) == 99.0


def test_profile_defaults_atr_mode_with_pct_fields():
    p = StrategyProfile(symbol="BTC/USD")
    assert p.bracket_mode == "atr"
    assert p.tp_pct == 0.015 and p.sl_pct == 0.01


def test_profile_from_dict_round_trips_pct_mode():
    p = StrategyProfile.from_dict(
        {
            "symbol": "BTC/USD",
            "bracket_mode": "pct",
            "tp_pct": 0.02,
            "sl_pct": 0.012,
        }
    )
    assert p.bracket_mode == "pct" and p.tp_pct == 0.02 and p.sl_pct == 0.012


def _candles_at_100():
    closes = np.full(80, 100.0)
    return pd.DataFrame(
        {
            "ts": pd.date_range(end=NOW, periods=len(closes), freq="15min", tz="UTC"),
            "open": closes,
            "high": closes + 1.0,
            "low": closes - 1.0,
            "close": closes,
            "volume": np.full(len(closes), 100.0),
        }
    )


class FakeData:
    def __init__(self):
        self.frame = _candles_at_100()

    def get_candles(self, *args, **kwargs):
        return self.frame

    def get_latest_price(self, symbol):
        return 100.0


class FakeBroker:
    def __init__(self):
        self.position = None

    def get_account(self):
        return {"equity": 1000.0, "cash": 1000.0, "buying_power": 1000.0}

    def get_position(self, symbol):
        return self.position

    def get_order(self, order_id=None, client_order_id=None):
        return None

    def submit_market_buy(self, symbol, qty, client_order_id):
        return BrokerOrder(
            "buy-1", symbol, OrderSide.BUY, OrderStatus.NEW, qty, 0.0, None, client_order_id
        )

    def submit_market_sell(self, symbol, qty, client_order_id):
        return BrokerOrder(
            "sell-1", symbol, OrderSide.SELL, OrderStatus.NEW, qty, 0.0, None, client_order_id
        )


def _pct_orch(tmp_path, broker=None):
    profile = StrategyProfile.from_dict(
        {
            "symbol": "BTC/USD",
            "timeframe": "15m",
            "signals": {"oversold": {"weight": 1.0, "oversold_level": 45, "period": 14}},
            "entry_threshold": 0.25,
            "regime_ma_period": 50,
            "bracket_mode": "pct",
            "tp_pct": 0.015,
            "sl_pct": 0.01,
            "risk_per_trade": 0.02,
        }
    )
    state = StateStore(str(tmp_path / "state.db"))
    return Orchestrator(
        profile,
        FakeData(),
        broker or FakeBroker(),
        state,
        RiskManager(profile, state.load_risk_state()),
        TradeJournal(),
    )


def test_orchestrator_pct_bracket_sets_pending_levels(tmp_path, monkeypatch):
    orch = _pct_orch(tmp_path)
    monkeypatch.setattr(orch.regime, "evaluate", lambda ctx: RegimeResult(Regime.NEUTRAL))
    monkeypatch.setattr(
        orch.engine,
        "evaluate",
        lambda ctx: ConfluenceResult(1.0, 0.25, True, {}, {}),
    )

    decision = orch.tick(now=NOW)
    pending = orch.state.load_pending_order()

    assert decision.code is DecisionCode.ORDER_SUBMITTED
    assert round(pending.tp, 4) == 101.5
    assert round(pending.stop, 4) == 99.0


def test_reconcile_adopts_broker_position_with_pct_bracket(tmp_path):
    broker = FakeBroker()
    broker.position = {
        "symbol": "BTC/USD",
        "qty": 2.0,
        "avg_entry_price": 100.0,
        "market_value": 200.0,
    }
    orch = _pct_orch(tmp_path, broker=broker)

    decision = orch.reconcile(NOW)
    pos = orch.state.load_position()

    assert decision.code is DecisionCode.BROKER_POSITION_EXISTS
    assert round(pos.tp, 4) == 101.5
    assert round(pos.stop, 4) == 99.0


def test_kronos_unavailable_holds_and_flags(tmp_path, monkeypatch):
    orch = _pct_orch(tmp_path)
    monkeypatch.setattr(orch.regime, "evaluate", lambda ctx: RegimeResult(Regime.NEUTRAL))
    monkeypatch.setattr(
        orch.engine,
        "evaluate",
        lambda ctx: ConfluenceResult(
            0.0,
            1.0,
            False,
            {},
            {"kronos_forecast": SignalResult("kronos_forecast", 0.0, {"error": "no_forecast"})},
        ),
    )

    decision = orch.tick(now=NOW)

    assert orch.state.load_pending_order() is None
    assert decision.code is DecisionCode.SIGNAL_BELOW_THRESHOLD
    assert decision.details.get("kronos") == "unavailable"
