from datetime import datetime, timezone
import numpy as np
import pytest

from swingbot.supervisor import PortfolioSupervisor, _bars_to_df
from swingbot.profiles import ProfileStore
from swingbot.state import StateStore
from swingbot.types import OpenPosition, Regime, Side
from swingbot.types import BrokerOrder, OrderSide, OrderStatus

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _bars(symbol_base=100.0, n=120):
    dip_len = min(6, n)
    base = list(np.linspace(symbol_base, symbol_base * 1.3, n - dip_len))
    dip = list(np.linspace(symbol_base * 1.3, symbol_base * 1.20, dip_len))
    closes = base + dip
    t0 = int(T0.timestamp()) - (n - 1) * 900
    return [{"time": t0 + i * 900, "open": c, "high": c * 1.002, "low": c * 0.998,
             "close": c, "volume": 100.0} for i, c in enumerate(closes)]


class FakeMarket:
    """Stands in for MarketData: serves preloaded bars, records refresh calls."""
    def __init__(self, bars_by_symbol):
        self.bars = bars_by_symbol
        self.refresh_calls = []
    def get(self, symbol, timeframe, limit=500, max_age=None):
        return self.bars.get(symbol, [])[-limit:]
    def refresh_many(self, symbols, timeframe, lookback=None):
        self.refresh_calls.append((tuple(sorted(symbols)), timeframe)); return 0
    def _provider(self):
        return None


class FakeBroker:
    def __init__(self, equity=1000.0):
        self._equity = equity
        self.positions = {}
        self.order = None
        self.buys = []
        self.sells = []
    def get_account(self): return {"equity": self._equity, "cash": self._equity,
                                   "buying_power": self._equity}
    def get_position(self, s): return self.positions.get(s)
    def get_order(self, order_id=None, client_order_id=None): return self.order
    def submit_market_buy(self, s, q, client_order_id):
        self.positions[s] = {"symbol": s, "qty": q, "avg_entry_price": 100.0, "market_value": q * 100}
        self.buys.append((s, q))
        self.order = BrokerOrder(f"b-{s}", s, OrderSide.BUY, OrderStatus.FILLED,
                                 q, q, 100.0, client_order_id)
        return self.order
    def submit_market_sell(self, s, q, client_order_id):
        self.positions.pop(s, None); self.sells.append((s, q))
        self.order = BrokerOrder(f"s-{s}", s, OrderSide.SELL, OrderStatus.FILLED,
                                 q, q, 99.0, client_order_id)
        return self.order
    def cancel_all(self): pass


def _profile(symbol):
    return {"symbol": symbol, "timeframe": "15m",
            "signals": {"oversold": {"weight": 0.6, "oversold_level": 45, "period": 14},
                        "vwap": {"weight": 0.4, "window": 20, "max_dist": 0.05}},
            "entry_threshold": 0.25, "regime_ma_period": 50, "atr_period": 14,
            "stop_atr_mult": 2.0, "take_profit_atr_mult": 2.0, "max_hold_bars": 32,
            "risk_per_trade": 0.02}


def _supervisor(tmp_path, symbols):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    for sym in symbols:
        name = sym.split("/")[0].lower()
        profiles.save(name, _profile(sym)); profiles.arm(name)
    market = FakeMarket({sym: _bars(100.0 + i * 10) for i, sym in enumerate(symbols)})
    broker = FakeBroker()
    sup = PortfolioSupervisor(profiles=profiles, creds=None,
                              state_db=str(tmp_path / "s.db"), market=market,
                              broker=broker, mode="paper")
    sup.build()
    return sup, broker, market


@pytest.fixture
def built_supervisor_two_strats(tmp_path):
    def build(
        *,
        enabled,
        mode="soft",
        targets=None,
        equity=10_000.0,
    ):
        profiles = ProfileStore(str(tmp_path / "p.db"))
        profiles.save("a", _profile("BTC/USD"))
        profiles.save("b", _profile("ETH/USD"))
        profiles.arm("a")
        profiles.arm("b")
        profiles.set_rebalance_settings({"enabled": enabled, "mode": mode})
        if targets is not None:
            profiles.set_rebalance_targets(targets)
        market = FakeMarket({"BTC/USD": _bars(100.0), "ETH/USD": _bars(110.0)})
        broker = FakeBroker(equity=equity)
        sup = PortfolioSupervisor(
            profiles=profiles,
            creds=None,
            state_db=str(tmp_path / "s.db"),
            market=market,
            broker=broker,
            mode="paper",
        )
        sup.build()
        return sup

    return build


def test_bars_to_df_shape():
    df = _bars_to_df(_bars(100.0, 5))
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume"]
    assert str(df["ts"].dt.tz) == "UTC"


def test_supervisor_ticks_all_armed_and_warms_once(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD", "ETH/USD"])
    sup.tick_all(now=T0)
    # one batched warm per timeframe (both symbols share 15m)
    assert market.refresh_calls == [(("BTC/USD", "ETH/USD"), "15m")]
    # both armed strategies were evaluated and (given the dip) opened positions
    assert set(broker.positions) == {"BTC/USD", "ETH/USD"}
    assert set(sup._store.load_all_pending_orders()) == {"btc", "eth"}


def test_supervisor_status_lists_strategies(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD", "ETH/USD"])
    sup.tick_all(now=T0)
    st = sup.status()
    assert "portfolio" in st and isinstance(st["strategies"], list)
    names = {s["name"] for s in st["strategies"]}
    assert names == {"btc", "eth"}
    assert st["portfolio"]["open_positions"] == 0  # fills promote on the next reconcile cycle


def test_max_concurrent_caps_open_positions(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD", "ETH/USD"])
    sup.profiles.set_portfolio_settings({"max_concurrent": 1})
    sup.build()                                   # rebuild with new settings
    sup.tick_all(now=T0)
    assert len(broker.positions) == 1             # portfolio cap allowed only one entry
    assert len(sup._store.load_all_pending_orders()) == 1


def test_soft_sizing_passes_allocated_equity(built_supervisor_two_strats):
    sup = built_supervisor_two_strats(
        enabled=True,
        mode="soft",
        targets={"a": 0.3, "b": 0.3},
        equity=10_000.0,
    )
    captured = {}
    for name, strategy in sup._strategies.items():
        strategy["orch"].tick = lambda now=None, sizing_equity=None, _n=name: (
            captured.__setitem__(_n, sizing_equity)
        )
    sup.tick_all(now=T0)
    assert captured["a"] == 3_000.0
    assert captured["b"] == 3_000.0


def test_soft_sizing_disabled_passes_none(built_supervisor_two_strats):
    sup = built_supervisor_two_strats(enabled=False, targets={}, equity=10_000.0)
    captured = {}
    for name, strategy in sup._strategies.items():
        strategy["orch"].tick = lambda now=None, sizing_equity=None, _n=name: (
            captured.__setitem__(_n, sizing_equity)
        )
    sup.tick_all(now=T0)
    assert captured["a"] is None and captured["b"] is None


def test_soft_cap_blocks_strategy_above_allocated_equity(tmp_path):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    profiles.save("a", _profile("BTC/USD"))
    profiles.arm("a")
    profiles.set_rebalance_settings({"enabled": True, "mode": "soft"})
    profiles.set_rebalance_targets({"a": 0.3})
    market = FakeMarket({"BTC/USD": _bars(100.0)})
    broker = FakeBroker(equity=10_000.0)
    sup = PortfolioSupervisor(
        profiles=profiles,
        creds=None,
        state_db=str(tmp_path / "s.db"),
        market=market,
        broker=broker,
        mode="paper",
    )
    sup.build()
    state = StateStore(str(tmp_path / "s.db"))
    state.save_position(
        OpenPosition(
            symbol="BTC/USD",
            entry_ts=T0,
            entry_price=100.0,
            qty=40.0,
            stop=90.0,
            tp=120.0,
            max_hold_until=T0,
            score_at_entry=0.7,
            regime_at_entry=Regime.UPTREND,
            side=Side.LONG,
        ),
        strategy="a",
    )
    decision = sup._make_gate("a")("BTC/USD", 1.0)
    assert decision.approved is False
    assert "rebalance soft cap" in decision.reason
