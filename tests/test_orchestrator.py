from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from swingbot.orchestrator import Orchestrator
from swingbot.profile import StrategyProfile
from swingbot.risk import RiskManager, RiskState
from swingbot.state import StateStore
from swingbot.journal import TradeJournal
from swingbot.types import BrokerOrder, ExitReason, OrderSide, OrderStatus

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _series(closes, end_ts=T0):
    n = len(closes)
    closes = np.array(closes, dtype=float)
    ts = pd.date_range(end=end_ts, periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({"ts": ts, "open": closes, "high": closes * 1.002,
                         "low": closes * 0.998, "close": closes,
                         "volume": np.full(n, 100.0)})


class FakeData:
    def __init__(self, candles, price): self._c = candles; self._price = price
    def set_price(self, p): self._price = p
    def get_candles(self, symbol, timeframe, lookback): return self._c
    def get_latest_price(self, symbol): return self._price


class FakeBroker:
    def __init__(self, equity=1000.0):
        self._equity = equity; self.position = None; self.order = None; self.buys = []; self.sells = []
    def get_account(self): return {"equity": self._equity, "cash": self._equity,
                                   "buying_power": self._equity}
    def get_position(self, symbol): return self.position
    def get_order(self, order_id=None, client_order_id=None): return self.order
    def submit_market_buy(self, symbol, qty, client_order_id):
        self.position = {"symbol": symbol, "qty": qty, "avg_entry_price": 100.0,
                         "market_value": qty * 100.0}
        self.buys.append((symbol, qty))
        self.order = BrokerOrder("buy-1", symbol, OrderSide.BUY, OrderStatus.FILLED,
                                 qty, qty, 100.0, client_order_id)
        return self.order
    def submit_market_sell(self, symbol, qty, client_order_id):
        self.position = None; self.sells.append((symbol, qty))
        self.order = BrokerOrder("sell-1", symbol, OrderSide.SELL, OrderStatus.FILLED,
                                 qty, qty, 99.0, client_order_id)
        return self.order
    def cancel_all(self): pass


def _profile(**kw):
    base = {"symbol": "TRX/USD", "timeframe": "15m",
            "signals": {"oversold": {"weight": 0.6, "oversold_level": 45, "period": 14},
                        "vwap": {"weight": 0.4, "window": 20, "max_dist": 0.05}},
            "entry_threshold": 0.25, "regime_ma_period": 50, "atr_period": 14,
            "stop_atr_mult": 2.0, "take_profit_atr_mult": 2.0, "max_hold_bars": 32,
            "risk_per_trade": 0.02, "max_concurrent": 1}
    base.update(kw)
    return StrategyProfile.from_dict(base)


def _orch(data, broker, tmp_path, profile=None):
    profile = profile or _profile()
    state = StateStore(str(tmp_path / "s.db"))
    risk = RiskManager(profile, state.load_risk_state())
    return Orchestrator(profile=profile, data=data, broker=broker, state=state,
                        risk=risk, journal=TradeJournal())


def _dip_and_recover():
    base = list(np.linspace(100, 130, 80)); dip = list(np.linspace(130, 118, 6))
    return _series(base + dip)


def test_tick_opens_position_on_signal(tmp_path):
    df = _dip_and_recover()
    data = FakeData(df, price=float(df["close"].iloc[-1]))
    broker = FakeBroker(equity=1000.0)
    orch = _orch(data, broker, tmp_path)
    orch.tick(now=T0)
    assert len(broker.buys) == 1
    orch.reconcile(now=T0)
    assert orch.state.load_position() is not None


def test_tick_no_entry_when_flat_and_no_signal(tmp_path):
    df = _series(list(np.linspace(100, 130, 90)))
    data = FakeData(df, price=float(df["close"].iloc[-1]))
    broker = FakeBroker()
    orch = _orch(data, broker, tmp_path)
    orch.tick(now=T0)
    assert broker.buys == []


def test_tick_exits_on_stop(tmp_path):
    df = _dip_and_recover()
    data = FakeData(df, price=float(df["close"].iloc[-1]))
    broker = FakeBroker(equity=1000.0)
    orch = _orch(data, broker, tmp_path)
    orch.tick(now=T0)
    orch.reconcile(now=T0)
    pos = orch.state.load_position()
    assert pos is not None
    data.set_price(pos.stop * 0.99)
    orch.tick(now=T0 + timedelta(minutes=1))
    assert len(broker.sells) == 1
    orch.reconcile(now=T0 + timedelta(minutes=1))
    assert orch.state.load_position() is None
    assert len(orch.journal.trades) == 1
    assert orch.journal.trades[0].exit_reason == ExitReason.STOP


def test_tick_blocked_by_killswitch(tmp_path):
    df = _dip_and_recover()
    data = FakeData(df, price=float(df["close"].iloc[-1]))
    broker = FakeBroker()
    state = StateStore(str(tmp_path / "s.db"))
    rs = RiskState(kill_switch_active=True, kill_switch_reason="test")
    state.save_risk_state(rs)
    risk = RiskManager(_profile(), state.load_risk_state())
    orch = Orchestrator(profile=_profile(), data=data, broker=broker, state=state,
                        risk=risk, journal=TradeJournal())
    orch.tick(now=T0)
    assert broker.buys == []


def test_reconcile_adopts_broker_position_if_state_empty(tmp_path):
    df = _dip_and_recover()
    data = FakeData(df, price=110.0)
    broker = FakeBroker()
    broker.position = {"symbol": "TRX/USD", "qty": 50.0, "avg_entry_price": 100.0,
                       "market_value": 5500.0}
    orch = _orch(data, broker, tmp_path)
    orch.reconcile(now=T0)
    assert orch.state.load_position() is not None


def test_tick_does_not_double_enter_when_broker_already_holds(tmp_path):
    df = _dip_and_recover()
    data = FakeData(df, price=float(df["close"].iloc[-1]))
    broker = FakeBroker(equity=1000.0)
    # state is empty, but the broker already reports an open position
    broker.position = {"symbol": "TRX/USD", "qty": 10.0, "avg_entry_price": 118.0,
                       "market_value": 1180.0}
    orch = _orch(data, broker, tmp_path)
    orch.tick(now=T0)
    assert broker.buys == []   # must NOT submit a second buy


def test_killswitch_allows_exit_of_open_position(tmp_path):
    df = _dip_and_recover()
    data = FakeData(df, price=float(df["close"].iloc[-1]))
    broker = FakeBroker(equity=1000.0)
    orch = _orch(data, broker, tmp_path)
    orch.tick(now=T0)                      # opens a position
    orch.reconcile(now=T0)
    pos = orch.state.load_position()
    assert pos is not None
    # trip kill switch AFTER entry
    orch.risk.state.kill_switch_active = True
    orch.risk.state.kill_switch_reason = "test"
    orch.state.save_risk_state(orch.risk.state)
    data.set_price(pos.stop * 0.99)        # stop is hit
    orch.tick(now=T0 + timedelta(minutes=1))
    assert len(broker.sells) == 1          # exit still happens despite kill switch
    orch.reconcile(now=T0 + timedelta(minutes=1))
    assert orch.state.load_position() is None

def test_stop_exit_updates_risk_state(tmp_path):
    df = _dip_and_recover()
    data = FakeData(df, price=float(df["close"].iloc[-1]))
    broker = FakeBroker(equity=1000.0)
    orch = _orch(data, broker, tmp_path)
    orch.tick(now=T0)
    orch.reconcile(now=T0)
    pos = orch.state.load_position()
    data.set_price(pos.stop * 0.99)
    orch.tick(now=T0 + timedelta(minutes=1))
    orch.reconcile(now=T0 + timedelta(minutes=1))
    assert orch.risk.state.consecutive_losses == 1
    assert "TRX/USD" in orch.risk.state.cooldown_until


def test_sizing_equity_override_scales_position(tmp_path):
    df = _dip_and_recover()
    data = FakeData(df, price=float(df["close"].iloc[-1]))
    full_path = tmp_path / "full"
    half_path = tmp_path / "half"
    full_path.mkdir()
    half_path.mkdir()
    full_broker = FakeBroker(equity=10_000.0)
    full = _orch(data, full_broker, full_path)
    full.tick(now=T0)

    half_broker = FakeBroker(equity=10_000.0)
    half = _orch(data, half_broker, half_path)
    half.tick(now=T0, sizing_equity=5_000.0)

    assert half_broker.buys[0][1] == full_broker.buys[0][1] / 2
