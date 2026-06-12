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
           ".brain-title", "text=Alpaca credentials",
           "text=Last usage-agent run", ".guide"]


def _ctx():
    return SessionContext(base_url="http://x:8000", screenshot_dir="/tmp/shots")


def test_s1_all_tabs_render_ok():
    trace = TabNavigationSession().run(FakePage(_ALL_S1), _ctx())
    assert trace.session == "s1-tabs" and trace.ok
    assert len(trace.steps) == 7
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
    assert not trace.ok and len(trace.steps) == 7


def test_s6_flags_missing_affordance():
    # Everything present except the "Arm" button.
    present = ["text=Save profile", "text=Save credentials", "text=Start bot",
               "text=HALT", "text=Flatten"]
    trace = GuideReconciliationSession().run(FakePage(present), _ctx())
    assert trace.session == "s6-guide" and not trace.ok
    bad = [s for s in trace.steps if not s.ok]
    assert len(bad) == 1
    assert "Arm" in bad[0].detail
    assert bad[0].expectation_key == "s6.affordance-exists"


def test_registries_partition_by_tier():
    assert [s.name for s in LIVE_SESSIONS] == ["s1-tabs", "s6-guide"]
    assert all(s.tier == "live" for s in LIVE_SESSIONS)
    assert all(s.tier == "ephemeral" for s in EPHEMERAL_SESSIONS)


from swingbot.selftest.sessions import (  # noqa: E402
    BrainInboxSession, GuidedStrategyFlowSession, SettingsPersistenceSession,
    WatchlistRoundTripSession,
)


class FakeApi:
    """Routes (method, path) -> (status, payload); records every call."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, base_url, token, method, path, body=None):
        self.calls.append((method, path, body))
        for (m, prefix), resp in self.routes.items():
            if m == method and path.startswith(prefix):
                return resp(path, body) if callable(resp) else resp
        return 404, {}


_PRESETS = [{"key": "dip", "name": "Dip buyer", "profile": {
    "symbol": "BTC/USD", "timeframe": "15m",
    "signals": {"oversold": {"weight": 1.0}}}}]


def _s2_routes(backtest=(400, {"detail": "set Alpaca credentials in Settings first"}),
               armed=True):
    return {
        ("GET", "/api/presets"): (200, _PRESETS),
        ("POST", "/api/strategy/backtest"): backtest,
        ("POST", "/api/profiles"): (200, {"ok": True}),
        ("POST", "/api/strategies/arm"): (200, {"ok": True}),
        ("GET", "/api/strategies"): (200, [{"name": "agent-s2-btc", "armed": armed}]),
    }


def test_s2_happy_path():
    api = FakeApi(_s2_routes())
    page = FakePage(["text=BTC/USD"])
    ctx = SessionContext(base_url="http://x:8001", token="t", api_fn=api)
    trace = GuidedStrategyFlowSession().run(page, ctx)
    assert trace.session == "s2-strategy-flow" and trace.ok
    assert ("POST", "/api/strategies/arm", {"name": "agent-s2-btc"}) in api.calls


def test_s2_undocumented_backtest_error_fails_expectation():
    api = FakeApi(_s2_routes(backtest=(500, {"detail": "boom"})))
    page = FakePage(["text=BTC/USD"])
    trace = GuidedStrategyFlowSession().run(
        page, SessionContext(base_url="http://x:8001", token="t", api_fn=api))
    bad = [s for s in trace.steps if not s.ok]
    assert any(s.expectation_key == "s2.backtest-needs-creds" for s in bad)


def test_s2_dashboard_missing_strategy_fails_expectation():
    api = FakeApi(_s2_routes())
    page = FakePage([])      # dashboard never shows the armed symbol
    trace = GuidedStrategyFlowSession().run(
        page, SessionContext(base_url="http://x:8001", token="t", api_fn=api))
    bad = [s for s in trace.steps if not s.ok]
    assert any(s.expectation_key == "s2.dashboard-shows-armed" for s in bad)


def test_s3_watchlist_roundtrip():
    lists = {"symbols": ["BTC/USD"]}

    def put(path, body):
        lists["symbols"] = body["symbols"]
        return 200, dict(lists)

    api = FakeApi({("GET", "/api/watchlist"): lambda p, b: (200, dict(lists)),
                   ("PUT", "/api/watchlist"): put})
    page = FakePage(["text=ETH/USD"])
    trace = WatchlistRoundTripSession().run(
        page, SessionContext(base_url="http://x:8001", token="t", api_fn=api))
    assert trace.ok
    assert lists["symbols"] == ["BTC/USD"]          # restored


def test_s4_settings_persist_and_restore():
    settings = {"max_concurrent": 5}

    def put(path, body):
        settings.update(body)
        return 200, dict(settings)

    api = FakeApi({("GET", "/api/portfolio/settings"): lambda p, b: (200, dict(settings)),
                   ("PUT", "/api/portfolio/settings"): put})
    trace = SettingsPersistenceSession().run(
        FakePage(), SessionContext(base_url="http://x:8001", token="t", api_fn=api))
    assert trace.ok and settings["max_concurrent"] == 5   # restored


def test_s5_brain_inbox_flow():
    seeded = []
    proposals = []

    def seed(rows):
        seeded.extend(rows)
        proposals.clear()
        proposals.extend(rows)

    def apply_(path, body):
        pid = path.split("/")[-2]
        for p in proposals:
            if p["id"] == pid:
                p["status"] = "applied"
        return 200, {"ok": True}

    def dismiss(path, body):
        pid = path.split("/")[-2]
        for p in proposals:
            if p["id"] == pid:
                p["status"] = "dismissed"
        return 200, {"ok": True}

    api = FakeApi({
        ("GET", "/api/presets"): (200, _PRESETS),
        ("GET", "/api/brain/proposals"): lambda p, b: (200, [dict(x) for x in proposals]),
        ("POST", "/api/brain/proposals/agent-s5-arm/apply"): apply_,
        ("POST", "/api/brain/proposals/agent-s5-tune/dismiss"): dismiss,
        ("GET", "/api/strategies"): (200, [{"name": "disc-btcusd-dip", "armed": True}]),
    })
    # Brain page shows the blocked reason and zero Apply buttons.
    page = FakePage(["text=guardrail-test-reason"])
    ctx = SessionContext(base_url="http://x:8001", token="t", api_fn=api,
                         seed_proposals=seed)
    trace = BrainInboxSession().run(page, ctx)
    assert trace.ok, [s.detail for s in trace.steps if not s.ok]
    assert {p["id"] for p in seeded} == {"agent-s5-arm", "agent-s5-tune",
                                         "agent-s5-uifix"}
    assert [s for s in trace.steps if s.expectation_key] == []


def test_s5_apply_button_present_for_ui_fix_is_drift():
    api = FakeApi({
        ("GET", "/api/presets"): (200, _PRESETS),
        ("GET", "/api/brain/proposals"): (200, []),
        ("POST", "/api/brain/proposals/agent-s5-arm/apply"): (200, {"ok": True}),
        ("POST", "/api/brain/proposals/agent-s5-tune/dismiss"): (200, {"ok": True}),
        ("GET", "/api/strategies"): (200, [{"name": "disc-btcusd-dip", "armed": True}]),
    })
    page = FakePage(["text=guardrail-test-reason", "button:has-text(\"Apply\")"])
    ctx = SessionContext(base_url="http://x:8001", token="t", api_fn=api,
                         seed_proposals=lambda rows: None)
    trace = BrainInboxSession().run(page, ctx)
    bad = [s for s in trace.steps if not s.ok]
    assert any(s.expectation_key == "s5.ui-fix-no-apply" for s in bad)


def test_ephemeral_registry_complete():
    assert [s.name for s in EPHEMERAL_SESSIONS] == [
        "s2-strategy-flow", "s3-watchlist", "s4-settings", "s5-brain-inbox"]
