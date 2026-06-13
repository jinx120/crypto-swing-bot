from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
from swingbot.orchestrator import Orchestrator
from swingbot.profile import StrategyProfile
from swingbot.risk import RiskManager
from swingbot.state import StateStore
from swingbot.journal import TradeJournal

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _series(closes):
    closes = np.array(closes, dtype=float); n = len(closes)
    return pd.DataFrame({"ts": pd.date_range(end=T0, periods=n, freq="15min", tz="UTC"),
                         "open": closes, "high": closes * 1.002, "low": closes * 0.998,
                         "close": closes, "volume": np.full(n, 100.0)})


class FakeData:
    def __init__(self, c, p): self._c=c; self._p=p
    def set_price(self, p): self._p=p
    def get_candles(self,*a,**k): return self._c
    def get_latest_price(self,*a,**k): return self._p


class FakeBroker:
    def __init__(self): self.position=None; self.buys=[]; self.sells=[]
    def get_account(self): return {"equity":1000.0,"cash":1000.0,"buying_power":1000.0}
    def get_position(self,s): return self.position
    def submit_market_buy(self,s,q): self.position={"symbol":s,"qty":q,"avg_entry_price":100.0,"market_value":q*100}; self.buys.append((s,q)); return "b"
    def submit_market_sell(self,s,q): self.position=None; self.sells.append((s,q)); return "s"
    def cancel_all(self): pass


def _profile():
    return StrategyProfile.from_dict({"symbol":"TRX/USD","timeframe":"15m",
        "signals":{"oversold":{"weight":0.6,"oversold_level":45,"period":14},
                   "vwap":{"weight":0.4,"window":20,"max_dist":0.05}},
        "entry_threshold":0.25,"regime_ma_period":50,"atr_period":14,
        "stop_atr_mult":2.0,"take_profit_atr_mult":2.0,"max_hold_bars":32,"risk_per_trade":0.02})


def _orch(data, broker, tmp_path):
    p=_profile(); st=StateStore(str(tmp_path/"s.db"))
    return Orchestrator(profile=p,data=data,broker=broker,state=st,
                        risk=RiskManager(p,st.load_risk_state()),journal=TradeJournal())


def _dip():
    return _series(list(np.linspace(100,130,80))+list(np.linspace(130,118,6)))


def test_paused_blocks_new_entries(tmp_path):
    data=FakeData(_dip(), float(_dip()["close"].iloc[-1])); broker=FakeBroker()
    orch=_orch(data,broker,tmp_path); orch.paused=True
    orch.tick(now=T0)
    assert broker.buys == []


def test_flatten_closes_open_position(tmp_path):
    data=FakeData(_dip(), float(_dip()["close"].iloc[-1])); broker=FakeBroker()
    orch=_orch(data,broker,tmp_path)
    orch.tick(now=T0)
    assert orch.state.load_position() is not None
    orch.flatten(now=T0 + timedelta(minutes=1))
    assert len(broker.sells) == 1
    assert orch.state.load_position() is None
    assert len(orch.journal.trades) == 1
