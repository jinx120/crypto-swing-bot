# tests/test_supervisor_reconnect.py
from swingbot.supervisor import PortfolioSupervisor


class _Creds:
    """make_broker returns a fresh sentinel each call; lets us prove reconnect rebuilt."""
    def __init__(self): self.calls = 0
    def get(self):
        return None
    def make_broker(self, mode=None):
        self.calls += 1
        return ("broker", self.calls)


def _sup(tmp_path, creds):
    return PortfolioSupervisor(
        profiles=_Profiles(), creds=creds,
        state_db=str(tmp_path / "s.db"), market=_Market())


class _Profiles:
    def list_armed(self): return []
    def get_portfolio_settings(self): return {}
    def get_rebalance_settings(self): return {}
    def get_rebalance_targets(self): return {}
    def get(self, name): return None


class _Market:
    pass


def test_build_uses_make_broker(tmp_path):
    creds = _Creds()
    sup = _sup(tmp_path, creds)
    sup.build()
    assert sup._broker == ("broker", 1)


def test_reconnect_rebuilds_broker_when_idle(tmp_path):
    creds = _Creds()
    sup = _sup(tmp_path, creds)
    sup.build()
    assert creds.calls == 1
    ok, msg = sup.reconnect()
    assert ok is True
    assert creds.calls == 2          # broker was rebuilt with fresh creds
    assert sup._broker == ("broker", 2)


def test_reconnect_reports_failure_when_unconfigured(tmp_path):
    class _NoCreds(_Creds):
        def make_broker(self, mode=None): return None
    sup = _sup(tmp_path, _NoCreds())
    ok, msg = sup.reconnect()
    assert ok is False
    assert "credentials" in msg.lower() or "reconnect" in msg.lower()
