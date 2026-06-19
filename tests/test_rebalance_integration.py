from datetime import timedelta

from swingbot.profiles import ProfileStore
from swingbot.supervisor import PortfolioSupervisor
from swingbot.types import BrokerOrder, OpenPosition, OrderSide, OrderStatus, Regime, Side

from datetime import datetime, timezone

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _low_vol_bars(symbol_base=100.0, n=120, slope=0.001):
    t0 = int(T0.timestamp()) - (n - 1) * 900
    closes = [symbol_base * (1.0 + slope * i) for i in range(n)]
    return [
        {
            "time": t0 + i * 900,
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": 100.0,
        }
        for i, close in enumerate(closes)
    ]


class FakeMarket:
    def __init__(self, bars_by_symbol):
        self.bars = bars_by_symbol

    def get(self, symbol, timeframe, limit=500, max_age=None):
        return self.bars.get(symbol, [])[-limit:]

    def refresh_many(self, symbols, timeframe, lookback=None):
        return 0

    def _provider(self):
        return None


class FakeBroker:
    def __init__(self, equity=1000.0):
        self._equity = equity
        self.positions = {}
        self.order = None
        self.buys = []
        self.sells = []

    def get_account(self):
        return {
            "equity": self._equity,
            "cash": self._equity,
            "buying_power": self._equity,
        }

    def get_position(self, symbol):
        return self.positions.get(symbol)

    def get_order(self, order_id=None, client_order_id=None):
        return self.order

    def submit_market_buy(self, symbol, qty, client_order_id):
        self.positions[symbol] = {
            "symbol": symbol,
            "qty": qty,
            "avg_entry_price": 100.0,
            "market_value": qty * 100.0,
        }
        self.buys.append((symbol, qty))
        self.order = BrokerOrder(
            f"b-{symbol}",
            symbol,
            OrderSide.BUY,
            OrderStatus.FILLED,
            qty,
            qty,
            100.0,
            client_order_id,
        )
        return self.order

    def submit_market_sell(self, symbol, qty, client_order_id):
        self.sells.append((symbol, qty))
        self.order = BrokerOrder(
            f"s-{symbol}",
            symbol,
            OrderSide.SELL,
            OrderStatus.FILLED,
            qty,
            qty,
            99.0,
            client_order_id,
        )
        return self.order

    def cancel_all(self):
        pass


def _profile(symbol):
    return {
        "symbol": symbol,
        "timeframe": "15m",
        "signals": {
            "oversold": {"weight": 0.6, "oversold_level": 45, "period": 14},
            "vwap": {"weight": 0.4, "window": 20, "max_dist": 0.05},
        },
        "entry_threshold": 0.25,
        "regime_ma_period": 50,
        "atr_period": 14,
        "stop_atr_mult": 2.0,
        "take_profit_atr_mult": 2.0,
        "max_hold_bars": 32,
        "risk_per_trade": 0.02,
    }


def _build_supervisor(tmp_path, *, enabled, mode="soft", equity=10_000.0):
    tmp_path.mkdir(parents=True, exist_ok=True)
    profiles = ProfileStore(str(tmp_path / "p.db"))
    profiles.save("a", _profile("BTC/USD"))
    profiles.save("b", _profile("ETH/USD"))
    profiles.arm("a")
    profiles.arm("b")
    profiles.set_rebalance_settings(
        {
            "enabled": enabled,
            "mode": mode,
            "vol_skip_threshold": 1.0,
            "fee_rate": 0.0,
            "benefit_factor": 0.0,
        }
    )
    profiles.set_rebalance_targets({"a": 0.3, "b": 0.3})
    broker = FakeBroker(equity=equity)
    market = FakeMarket(
        {
            "BTC/USD": _low_vol_bars(100.0, slope=0.001),
            "ETH/USD": _low_vol_bars(100.0, slope=0.0),
        }
    )
    sup = PortfolioSupervisor(
        profiles=profiles,
        creds=None,
        state_db=str(tmp_path / "s.db"),
        market=market,
        broker=broker,
        mode="paper",
    )
    sup.build()
    sup._latest_prices.update({"BTC/USD": 100.0, "ETH/USD": 100.0})
    return sup, broker


def _seed_position(sup, broker, name, symbol, value, price=100.0):
    qty = value / price
    sup._store.save_position(
        OpenPosition(
            symbol=symbol,
            entry_ts=T0,
            entry_price=price,
            qty=qty,
            stop=price * 0.9,
            tp=price * 2.0,
            max_hold_until=T0 + timedelta(days=1),
            score_at_entry=0.7,
            regime_at_entry=Regime.UPTREND,
            side=Side.LONG,
        ),
        strategy=name,
    )
    broker.positions[symbol] = {
        "symbol": symbol,
        "qty": qty,
        "avg_entry_price": price,
        "market_value": value,
    }


def test_end_to_end_soft_then_hard(tmp_path):
    off, off_broker = _build_supervisor(tmp_path / "off", enabled=False)
    off_seen = {}
    for name, strategy in off._strategies.items():
        strategy["orch"].tick = lambda now=None, sizing_equity=None, _n=name: (
            off_seen.__setitem__(_n, sizing_equity)
        )
    off.tick_all(now=T0)
    assert off_seen == {"a": None, "b": None}
    assert off_broker.sells == []
    assert off._telemetry.recent_rebalance(10) == []

    soft, soft_broker = _build_supervisor(tmp_path / "soft", enabled=True, mode="soft")
    soft_seen = {}
    for name, strategy in soft._strategies.items():
        strategy["orch"].tick = lambda now=None, sizing_equity=None, _n=name: (
            soft_seen.__setitem__(_n, sizing_equity)
        )
    soft.tick_all(now=T0)
    assert soft_seen == {"a": 3_000.0, "b": 3_000.0}
    _seed_position(soft, soft_broker, "a", "BTC/USD", 4_000.0)
    decision = soft._make_gate("a")("BTC/USD", 1.0)
    assert decision.approved is False
    assert soft_broker.sells == []

    hard, hard_broker = _build_supervisor(tmp_path / "hard", enabled=True, mode="hard")
    _seed_position(hard, hard_broker, "a", "BTC/USD", 5_000.0)
    hard.tick_all(now=T0)
    assert hard_broker.sells == [("BTC/USD", 15.0)]
    pos = hard._store.load_position("a")
    assert round(pos.qty, 6) == 35.0
    row = hard._telemetry.recent_rebalance(10)[0]
    assert row["ran"] is True and row["mode"] == "hard"
