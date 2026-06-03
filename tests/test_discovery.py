from types import SimpleNamespace

import pandas as pd

import swingbot.discovery as ds
from swingbot.discovery import good_history, windows_for, _apply_window, MIN_TRADES
from swingbot.discovery import DiscoveryEngine


def test_good_history_requires_trades_expectancy_profit_factor():
    assert good_history({"n_trades": 25, "expectancy": 0.5, "profit_factor": 1.3})
    assert not good_history({"n_trades": 5, "expectancy": 0.5, "profit_factor": 1.3})   # too few
    assert not good_history({"n_trades": 25, "expectancy": -0.1, "profit_factor": 1.3}) # losing
    assert not good_history({"n_trades": 25, "expectancy": 0.5, "profit_factor": 0.9})  # pf<=1
    assert not good_history({"n_trades": None, "expectancy": None, "profit_factor": None})
    assert MIN_TRADES == 20


def test_windows_for_only_offers_covered_windows():
    day = 86400
    short = windows_for({"min_ts": 1_700_000_000, "max_ts": 1_700_000_000 + 10 * day})
    assert [w["key"] for w in short] == ["full"]                 # 10 days -> full only
    deep = windows_for({"min_ts": 1_700_000_000, "max_ts": 1_700_000_000 + 400 * day})
    assert [w["key"] for w in deep] == ["full", "last_1y", "last_90d", "last_30d"]
    assert windows_for({}) == [{"key": "full", "label": "Full history", "days": None}]


def test_apply_window_slices_trailing_days():
    ts = pd.date_range("2024-01-01", periods=200, freq="D", tz="UTC")
    df = pd.DataFrame({"ts": ts, "close": range(200)})
    full = _apply_window(df, "full")
    last30 = _apply_window(df, "last_30d")
    assert len(full) == 200
    assert 29 <= len(last30) <= 31                               # ~30 trailing days
    assert last30["ts"].iloc[-1] == df["ts"].iloc[-1]


def _bars(n=300, start=100.0, up=True):
    out, p, t0 = [], start, 1_700_000_000
    for i in range(n):
        p *= (1.001 if i % 3 else 0.999) if up else (0.999 if i % 3 else 1.001)
        out.append({"time": t0 + i * 900, "open": p, "high": p * 1.01,
                    "low": p * 0.99, "close": p * 1.002, "volume": 1000 + i})
    return out


class FakeMarket:
    def __init__(self, bars):
        self._bars = bars
    def get(self, symbol, timeframe, limit=500, max_age=None):
        return self._bars[-limit:]


def _fake_metrics(expectancy, n_trades=25, pf=1.5, win_rate=0.6):
    return SimpleNamespace(n_trades=n_trades, win_rate=win_rate, expectancy=expectancy,
                           profit_factor=pf, max_drawdown=0.1, avg_win=1.0, avg_loss=-0.5,
                           total_return=0.2)


def test_sweep_ranks_rows_by_expectancy(monkeypatch):
    # each archetype gets a deterministic expectancy keyed off its entry_threshold
    monkeypatch.setattr(ds, "run_backtest",
                        lambda df, profile, benchmark_df=None: ([], _fake_metrics(1.0 - profile.entry_threshold)))
    rows = DiscoveryEngine(FakeMarket(_bars())).sweep(["BTC/USD", "ETH/USD"], window_key="full")
    exps = [r["metrics"]["expectancy"] for r in rows if r["metrics"]]
    assert exps == sorted(exps, reverse=True)                       # ranked desc
    assert {r["symbol"] for r in rows} == {"BTC/USD", "ETH/USD"}
    assert all(r["error"] is None for r in rows)


def test_sweep_eligibility_needs_good_history_and_regime(monkeypatch):
    monkeypatch.setattr(ds, "run_backtest",
                        lambda df, profile, benchmark_df=None: ([], _fake_metrics(0.8)))
    up = DiscoveryEngine(FakeMarket(_bars(up=True))).sweep(["BTC/USD"], window_key="full")
    down = DiscoveryEngine(FakeMarket(_bars(up=False))).sweep(["BTC/USD"], window_key="full")
    assert any(r["eligible_now"] for r in up)        # good history + uptrend regime
    assert all(not r["eligible_now"] for r in down)  # downtrend blocks eligibility
    assert all(isinstance(r["fires_now"], bool) for r in up)


def test_sweep_isolates_per_symbol_errors(monkeypatch):
    monkeypatch.setattr(ds, "run_backtest",
                        lambda df, profile, benchmark_df=None: ([], _fake_metrics(0.5)))
    short = FakeMarket(_bars(n=10))                  # <30 bars -> InsufficientData on load
    rows = DiscoveryEngine(short).sweep(["BTC/USD"], window_key="full")
    assert len(rows) == 1 and rows[0]["metrics"] is None and rows[0]["error"]


def test_sweep_respects_max_symbols(monkeypatch):
    monkeypatch.setattr(ds, "run_backtest",
                        lambda df, profile, benchmark_df=None: ([], _fake_metrics(0.5)))
    rows = DiscoveryEngine(FakeMarket(_bars())).sweep(
        ["BTC/USD", "ETH/USD", "SOL/USD"], window_key="full", max_symbols=1)
    assert {r["symbol"] for r in rows} == {"BTC/USD"}
