from datetime import datetime, timezone

from swingbot.profiles import ProfileStore
from swingbot.supervisor import PortfolioSupervisor
from tests.test_supervisor import FakeMarket, FakeBroker, _profile, _bars

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _sup(tmp_path, symbols):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    for sym in symbols:
        name = sym.split("/")[0].lower()
        profiles.save(name, _profile(sym)); profiles.arm(name)
    market = FakeMarket({sym: _bars(100.0 + i * 10) for i, sym in enumerate(symbols)})
    sup = PortfolioSupervisor(profiles=profiles, creds=None,
                              state_db=str(tmp_path / "s.db"), market=market,
                              broker=FakeBroker(), mode="paper")
    sup.build()
    return sup


def test_journal_and_metrics_aggregate(tmp_path):
    sup = _sup(tmp_path, ["BTC/USD", "ETH/USD"])
    sup.tick_all(now=T0)
    assert isinstance(sup.journal(), list)
    assert "n_trades" in sup.metrics()
    assert isinstance(sup.journal(strategy="btc"), list)


def test_halt_and_reset_portfolio_kill_switch(tmp_path):
    sup = _sup(tmp_path, ["BTC/USD"])
    sup.tick_all(now=T0)
    sup.halt()
    assert sup.status()["portfolio"]["kill_switch"]["active"] is True
    sup.reset()
    assert sup.status()["portfolio"]["kill_switch"]["active"] is False


def test_flatten_one_and_all(tmp_path):
    sup = _sup(tmp_path, ["BTC/USD", "ETH/USD"])
    sup.tick_all(now=T0)
    sup.flatten("btc")
    assert sup._store.load_position("btc") is None
    sup.flatten()
    assert sup._store.load_all_positions() == {}


def test_set_mode_live_blocked_without_graduation(tmp_path):
    sup = _sup(tmp_path, ["BTC/USD"])
    sup.tick_all(now=T0)
    ok, reason = sup.set_mode("live")
    assert ok is False and "blocked" in reason.lower()


def test_reload_picks_up_newly_armed(tmp_path):
    sup = _sup(tmp_path, ["BTC/USD"])
    sup.profiles.save("eth", _profile("ETH/USD")); sup.profiles.arm("eth")
    sup.reload()
    names = {s["name"] for s in sup.status()["strategies"]}
    assert names == {"btc", "eth"}


def test_reload_is_noop_when_idle_and_unbuilt(tmp_path):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    profiles.save("btc", _profile("BTC/USD")); profiles.arm("btc")
    market = FakeMarket({"BTC/USD": _bars(100.0)})
    sup = PortfolioSupervisor(profiles=profiles, creds=None,
                              state_db=str(tmp_path / "s.db"), market=market,
                              broker=None, mode="paper")
    sup.reload()                      # must NOT raise (no creds, never built)
    assert sup._store is None
    assert sup.status()["strategies"] == []
