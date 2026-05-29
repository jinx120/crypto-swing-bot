from swingbot.profile import StrategyProfile
from swingbot.types import Regime


def test_from_dict_populates_defaults_and_overrides():
    p = StrategyProfile.from_dict({
        "symbol": "TRX/USD",
        "benchmark_symbol": "BTC/USD",
        "timeframe": "15m",
        "signals": {"oversold": {"weight": 0.4, "oversold_level": 30},
                    "vwap": {"weight": 0.3, "max_dist": 0.03},
                    "relative_strength": {"weight": 0.3, "band": 0.02, "lookback": 96}},
        "entry_threshold": 0.6,
    })
    assert p.symbol == "TRX/USD"
    assert p.entry_threshold == 0.6
    assert p.risk_per_trade == 0.01          # default
    assert p.atr_period == 14                 # default
    assert p.stop_atr_mult == 1.5            # default
    assert p.take_profit_atr_mult == 2.0     # default
    assert p.max_hold_bars == 32              # default (8h / 15m)
    assert Regime.UPTREND in p.allowed_regimes
    assert Regime.DOWNTREND not in p.allowed_regimes
    assert p.signals["oversold"]["weight"] == 0.4
