from datetime import datetime, timezone
import numpy as np

from swingbot.supervisor import PortfolioSupervisor, _bars_to_df
from swingbot.profiles import ProfileStore

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _bars(symbol_base=100.0, n=120):
    dip_len = min(6, n)
    base = list(np.linspace(symbol_base, symbol_base * 1.3, n - dip_len))
    dip = list(np.linspace(symbol_base * 1.3, symbol_base * 1.20, dip_len))
    closes = base + dip
    t0 = 1_700_000_000
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
    def __init__(self): self.positions = {}; self.buys = []; self.sells = []
    def get_account(self): return {"equity": 1000.0, "cash": 1000.0, "buying_power": 1000.0}
    def get_position(self, s): return self.positions.get(s)
    def submit_market_buy(self, s, q):
        self.positions[s] = {"symbol": s, "qty": q, "avg_entry_price": 100.0, "market_value": q * 100}
        self.buys.append((s, q)); return "b"
    def submit_market_sell(self, s, q): self.positions.pop(s, None); self.sells.append((s, q)); return "s"
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


def test_supervisor_status_lists_strategies(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD", "ETH/USD"])
    sup.tick_all(now=T0)
    st = sup.status()
    assert "portfolio" in st and isinstance(st["strategies"], list)
    names = {s["name"] for s in st["strategies"]}
    assert names == {"btc", "eth"}
    assert st["portfolio"]["open_positions"] == 2


def test_max_concurrent_caps_open_positions(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD", "ETH/USD"])
    sup.profiles.set_portfolio_settings({"max_concurrent": 1})
    sup.build()                                   # rebuild with new settings
    sup.tick_all(now=T0)
    assert len(broker.positions) == 1             # portfolio cap allowed only one entry
