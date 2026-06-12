from swingbot.selftest.sessions import (
    EPHEMERAL_SESSIONS, LIVE_SESSIONS, GuideReconciliationSession,
    SessionContext, TabNavigationSession,
)


class FakeLocator:
    def __init__(self, n):
        self._n = n

    def count(self):
        return self._n


class FakePage:
    """present_selectors: selectors that exist; everything else is missing."""

    def __init__(self, present_selectors=None, fail_goto=False):
        self.present = set(present_selectors or [])
        self.fail_goto = fail_goto
        self.gotos = []

    def on(self, event, handler):
        pass

    def goto(self, url, **kw):
        self.gotos.append(url)
        if self.fail_goto:
            raise ConnectionRefusedError("refused")

    def wait_for_selector(self, sel, timeout=0):
        if sel not in self.present:
            raise TimeoutError(f"no {sel}")

    def locator(self, sel):
        return FakeLocator(1 if sel in self.present else 0)

    def screenshot(self, **kw):
        pass


_ALL_S1 = ["text=Watchlist", "text=Save profile", ".discover-controls",
           ".brain-title", "text=Alpaca credentials", ".guide"]


def _ctx():
    return SessionContext(base_url="http://x:8000", screenshot_dir="/tmp/shots")


def test_s1_all_tabs_render_ok():
    trace = TabNavigationSession().run(FakePage(_ALL_S1), _ctx())
    assert trace.session == "s1-tabs" and trace.ok
    assert len(trace.steps) == 6
    assert all(s.ok for s in trace.steps)


def test_s1_missing_element_fails_step_with_expectation_key():
    present = [s for s in _ALL_S1 if s != ".brain-title"]
    trace = TabNavigationSession().run(FakePage(present), _ctx())
    assert not trace.ok
    bad = [s for s in trace.steps if not s.ok]
    assert len(bad) == 1
    assert bad[0].expectation_key == "s1.tab-renders"
    assert "/#/brain" in bad[0].detail


def test_s1_goto_failure_is_failed_step_not_crash():
    trace = TabNavigationSession().run(FakePage(fail_goto=True), _ctx())
    assert not trace.ok and len(trace.steps) == 6


def test_s6_flags_missing_affordance():
    # Everything present except the stale "Set active" button.
    present = ["text=Save profile", "text=Save credentials", "text=Start bot",
               "text=HALT", "text=Flatten"]
    trace = GuideReconciliationSession().run(FakePage(present), _ctx())
    assert trace.session == "s6-guide" and not trace.ok
    bad = [s for s in trace.steps if not s.ok]
    assert len(bad) == 1
    assert "Set active" in bad[0].detail
    assert bad[0].expectation_key == "s6.affordance-exists"


def test_registries_partition_by_tier():
    assert [s.name for s in LIVE_SESSIONS] == ["s1-tabs", "s6-guide"]
    assert all(s.tier == "live" for s in LIVE_SESSIONS)
    assert all(s.tier == "ephemeral" for s in EPHEMERAL_SESSIONS)
