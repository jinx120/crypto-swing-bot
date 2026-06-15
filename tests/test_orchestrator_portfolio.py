from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd

from swingbot.orchestrator import Orchestrator
from swingbot.portfolio_risk import PortfolioDecision
from swingbot.profile import StrategyProfile
from swingbot.risk import RiskManager
from swingbot.state import StateStore
from swingbot.journal import TradeJournal
from swingbot.types import BrokerOrder, OrderSide, OrderStatus

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _series(closes):
    closes = np.array(closes, dtype=float); n = len(closes)
    return pd.DataFrame({"ts": pd.date_range(end=T0, periods=n, freq="15min", tz="UTC"),
                         "open": closes, "high": closes * 1.002, "low": closes * 0.998,
                         "close": closes, "volume": np.full(n, 100.0)})


class FakeData:
    def __init__(self, c, p): self._c = c; self._p = p
    def get_candles(self, *a, **k): return self._c
    def get_latest_price(self, *a, **k): return self._p


class FakeBroker:
    def __init__(self): self.position = None; self.order = None; self.buys = []; self.sells = []
    def get_account(self): return {"equity": 1000.0, "cash": 1000.0, "buying_power": 1000.0}
    def get_position(self, s): return self.position
    def get_order(self, order_id=None, client_order_id=None): return self.order
    def submit_market_buy(self, s, q, client_order_id):
        self.position = {"symbol": s, "qty": q, "avg_entry_price": 100.0, "market_value": q * 100}
        self.buys.append((s, q))
        self.order = BrokerOrder("b", s, OrderSide.BUY, OrderStatus.FILLED,
                                 q, q, 100.0, client_order_id)
        return self.order
    def submit_market_sell(self, s, q, client_order_id):
        self.position = None; self.sells.append((s, q))
        self.order = BrokerOrder("s", s, OrderSide.SELL, OrderStatus.FILLED,
                                 q, q, 99.0, client_order_id)
        return self.order
    def cancel_all(self): pass


def _profile():
    return StrategyProfile.from_dict({"symbol": "TRX/USD", "timeframe": "15m",
        "signals": {"oversold": {"weight": 0.6, "oversold_level": 45, "period": 14},
                    "vwap": {"weight": 0.4, "window": 20, "max_dist": 0.05}},
        "entry_threshold": 0.25, "regime_ma_period": 50, "atr_period": 14,
        "stop_atr_mult": 2.0, "take_profit_atr_mult": 2.0, "max_hold_bars": 32, "risk_per_trade": 0.02})


def _dip():
    return _series(list(np.linspace(100, 130, 80)) + list(np.linspace(130, 118, 6)))


def test_portfolio_gate_blocks_entry(tmp_path):
    df = _dip(); data = FakeData(df, float(df["close"].iloc[-1])); broker = FakeBroker()
    p = _profile(); st = StateStore(str(tmp_path / "s.db"))
    seen = {}
    def gate(symbol, value):
        seen["symbol"] = symbol; seen["value"] = value
        return PortfolioDecision(False, "blocked")
    orch = Orchestrator(profile=p, data=data, broker=broker, state=st,
                        risk=RiskManager(p, st.load_risk_state()), journal=TradeJournal(),
                        portfolio_gate=gate)
    orch.tick(now=T0)
    assert broker.buys == []                       # gate vetoed the entry
    assert seen["symbol"] == "TRX/USD" and seen["value"] > 0


def test_portfolio_gate_allows_and_notifies_on_close(tmp_path):
    df = _dip(); data = FakeData(df, float(df["close"].iloc[-1])); broker = FakeBroker()
    p = _profile(); st = StateStore(str(tmp_path / "s.db"))
    closed = []
    orch = Orchestrator(profile=p, data=data, broker=broker, state=st,
                        risk=RiskManager(p, st.load_risk_state()), journal=TradeJournal(),
                        portfolio_gate=lambda s, v: PortfolioDecision(True),
                        portfolio_on_close=lambda pnl, now: closed.append(pnl))
    orch.tick(now=T0)
    assert len(broker.buys) == 1
    orch.reconcile(now=T0)
    pos = orch.state.load_position()
    data._p = pos.stop * 0.99                       # force a stop-out
    orch.tick(now=T0 + timedelta(minutes=1))
    orch.reconcile(now=T0 + timedelta(minutes=1))
    assert len(closed) == 1                          # portfolio_on_close fired with the pnl


def test_flatten_notifies_on_close(tmp_path):
    df = _dip(); data = FakeData(df, float(df["close"].iloc[-1])); broker = FakeBroker()
    p = _profile(); st = StateStore(str(tmp_path / "s.db"))
    closed = []
    orch = Orchestrator(profile=p, data=data, broker=broker, state=st,
                        risk=RiskManager(p, st.load_risk_state()), journal=TradeJournal(),
                        portfolio_gate=lambda s, v: PortfolioDecision(True),
                        portfolio_on_close=lambda pnl, now: closed.append(pnl))
    orch.tick(now=T0)
    assert len(broker.buys) == 1                  # a position was opened
    orch.reconcile(now=T0)
    orch.flatten(now=T0 + timedelta(minutes=1))   # manual close
    orch.reconcile(now=T0 + timedelta(minutes=1))
    assert orch.state.load_position() is None      # position cleared
    assert len(closed) == 1                          # hook fired via flatten
