from datetime import datetime, timezone

from swingbot.state import StateStore, StrategyStateView
from swingbot.portfolio_risk import PortfolioRiskState
from swingbot.types import OpenPosition, Regime, Side


def _pos(symbol, now):
    return OpenPosition(symbol=symbol, entry_ts=now, entry_price=0.1, qty=10.0,
                        stop=0.09, tp=0.12, max_hold_until=now,
                        score_at_entry=0.5, regime_at_entry=Regime.UPTREND, side=Side.LONG)


def test_positions_are_keyed_by_strategy(tmp_path):
    s = StateStore(str(tmp_path / "s.db"))
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    s.save_position(_pos("BTC/USD", now), strategy="btc")
    s.save_position(_pos("ETH/USD", now), strategy="eth")
    assert s.load_position("btc").symbol == "BTC/USD"
    assert s.load_position("eth").symbol == "ETH/USD"
    assert set(s.load_all_positions()) == {"btc", "eth"}
    s.clear_position("btc")
    assert s.load_position("btc") is None
    assert set(s.load_all_positions()) == {"eth"}


def test_portfolio_risk_state_roundtrip(tmp_path):
    s = StateStore(str(tmp_path / "s.db"))
    s.save_portfolio_risk_state(PortfolioRiskState(
        kill_switch_active=True, kill_switch_reason="cap", day="2026-01-01",
        realized_pnl_today=-12.0, day_start_equity=1000.0))
    out = s.load_portfolio_risk_state()
    assert out.kill_switch_active is True and out.realized_pnl_today == -12.0


def test_strategy_state_view_binds_key(tmp_path):
    s = StateStore(str(tmp_path / "s.db"))
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    view = StrategyStateView(s, "btc")
    view.save_position(_pos("BTC/USD", now))           # no-arg interface
    assert view.load_position().symbol == "BTC/USD"
    assert s.load_position("btc").symbol == "BTC/USD"   # written under the bound key
    view.clear_position()
    assert view.load_position() is None
