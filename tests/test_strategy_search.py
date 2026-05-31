from types import SimpleNamespace

import swingbot.strategy_search as ss
from swingbot.strategy_search import backtest_profile, metrics_dict, search


def _bars(n=200, start=100.0):
    out, p, t0 = [], start, 1_700_000_000
    for i in range(n):
        p *= 1.001 if i % 3 else 0.999
        out.append({"time": t0 + i * 900, "open": p, "high": p * 1.01,
                    "low": p * 0.99, "close": p * 1.002, "volume": 1000 + i})
    return out


class FakeMarket:
    def __init__(self, bars):
        self._bars = bars
    def get(self, symbol, timeframe, limit=500, max_age=None):
        return self._bars[-limit:]


def test_metrics_dict_uses_getattr_defaults():
    m = SimpleNamespace(n_trades=3, win_rate=0.5, expectancy=0.4)
    d = metrics_dict(m)
    assert d["n_trades"] == 3 and d["expectancy"] == 0.4
    assert d["profit_factor"] is None     # absent -> None, never raises


def test_backtest_profile_runs_end_to_end():
    market = FakeMarket(_bars(250))
    profile = {"symbol": "TRX/USD", "timeframe": "15m",
               "signals": {"oversold": {"weight": 1.0, "oversold_level": 45, "period": 14}}}
    m = backtest_profile(market, profile)
    assert m.n_trades >= 0     # valid Metrics regardless of trade count


def test_search_ranks_by_expectancy_and_flags_recommended(monkeypatch):
    market = FakeMarket(_bars(250))

    def fake_bt(_market, profile, lookback=1000):
        et = profile["entry_threshold"]
        return SimpleNamespace(n_trades=10, win_rate=0.5, expectancy=1.0 - et)

    monkeypatch.setattr(ss, "backtest_profile", fake_bt)
    res = search(market, "TRX/USD", "balanced", "swing", ai=False)
    metrics_rows = [r for r in res["results"] if r["metrics"]]
    exps = [r["metrics"]["expectancy"] for r in metrics_rows]
    assert exps == sorted(exps, reverse=True)              # ranked desc
    assert res["results"][0]["recommended"] is True
    assert sum(1 for r in res["results"] if r["recommended"]) == 1


def test_search_captures_candidate_errors(monkeypatch):
    market = FakeMarket(_bars(250))

    def boom(_market, profile, lookback=1000):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(ss, "backtest_profile", boom)
    res = search(market, "TRX/USD", "balanced", "swing", ai=False)
    assert all(r["metrics"] is None and r["error"] == "kaboom" for r in res["results"])
    assert all(r["recommended"] is False for r in res["results"])
