from swingbot.selftest.uiprobe import UIProbe, ROUTES


class FakePage:
    def __init__(self):
        self._handlers = {}

    def on(self, event, handler):
        self._handlers.setdefault(event, []).append(handler)

    def emit(self, event, *args):
        for h in self._handlers.get(event, []):
            h(*args)

    def goto(self, url, **kwargs):
        pass

    def screenshot(self, **kwargs):
        pass


class _ConsoleMsgError:
    type = "error"
    text = "Uncaught TypeError"


class _ConsoleMsgWarning:
    type = "warning"
    text = "Deprecated API"


class _Resp500:
    status = 500
    url = "http://localhost:8000/api/brain"


class _Resp404:
    status = 404
    url = "http://localhost:8000/api/missing"


def _make_probe():
    return UIProbe("http://localhost:8000", "/tmp/shots")


def _fire_during_goto(page, event, obj):
    def patched_goto(url, **kw):
        page.emit(event, obj)
    page.goto = patched_goto


def test_console_error_becomes_warn_finding():
    probe = _make_probe()
    page = FakePage()
    _fire_during_goto(page, "console", _ConsoleMsgError())
    result = probe.probe_route("/", page)
    assert any(f.severity == "warn" and f.kind == "console" for f in result)


def test_console_warning_becomes_info_finding():
    probe = _make_probe()
    page = FakePage()
    _fire_during_goto(page, "console", _ConsoleMsgWarning())
    result = probe.probe_route("/", page)
    assert any(f.severity == "info" and f.kind == "console" for f in result)


def test_pageerror_becomes_fatal_finding():
    probe = _make_probe()
    page = FakePage()
    _fire_during_goto(page, "pageerror", Exception("uncaught!"))
    result = probe.probe_route("/brain", page)
    assert any(f.severity == "fatal" and f.kind == "exception" for f in result)


def test_5xx_response_becomes_fatal_network_finding():
    probe = _make_probe()
    page = FakePage()
    _fire_during_goto(page, "response", _Resp500())
    result = probe.probe_route("/", page)
    assert any(f.severity == "fatal" and f.kind == "network" for f in result)


def test_4xx_response_becomes_warn_network_finding():
    probe = _make_probe()
    page = FakePage()
    _fire_during_goto(page, "response", _Resp404())
    result = probe.probe_route("/", page)
    assert any(f.severity == "warn" and f.kind == "network" for f in result)


def test_navigation_exception_becomes_fatal_finding():
    probe = _make_probe()
    page = FakePage()

    def raises_goto(url, **kw):
        raise ConnectionRefusedError("refused")

    page.goto = raises_goto
    result = probe.probe_route("/", page)
    assert any(f.severity == "fatal" and f.kind == "exception" for f in result)


def test_screenshot_path_set_on_finding():
    probe = _make_probe()
    page = FakePage()
    _fire_during_goto(page, "pageerror", Exception("oops"))
    result = probe.probe_route("/discover", page)
    assert all(f.screenshot_path != "" for f in result)
    assert all("discover" in f.screenshot_path for f in result)


def test_run_visits_all_routes():
    probe = _make_probe()
    visited = []
    original = probe.probe_route
    probe.probe_route = lambda route, page: visited.append(route) or []
    probe.run(FakePage)
    assert set(visited) == set(ROUTES)


def test_routes_are_dashboard_discover_brain():
    assert ROUTES == ["/", "/discover", "/brain"]
