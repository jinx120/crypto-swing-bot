import pytest
from fastapi.testclient import TestClient

from swingbot.web import create_app


class RecordingController:
    def __init__(self, events, stop_error=None):
        self.events = events
        self.stop_error = stop_error

    def status(self):
        return {}

    def journal(self, strategy=None):
        return []

    def metrics(self, strategy=None):
        return {}

    def stop(self):
        self.events.append("controller:stop")
        if self.stop_error is not None:
            raise self.stop_error


class RecordingPoller:
    def __init__(self, events):
        self.events = events

    def start(self):
        self.events.append("poller:start")

    def stop(self):
        self.events.append("poller:stop")


def test_lifespan_starts_poller_then_stops_controller_before_poller():
    events = []
    app = create_app(
        RecordingController(events), profiles=None, creds=None, token="t",
        poller=RecordingPoller(events))

    with TestClient(app) as client:
        assert events == ["poller:start"]
        assert client.get("/api/state").status_code == 200

    assert events == ["poller:start", "controller:stop", "poller:stop"]


def test_lifespan_stops_poller_even_when_controller_stop_raises():
    events = []
    app = create_app(
        RecordingController(events, RuntimeError("stop failed")),
        profiles=None, creds=None, token="t", poller=RecordingPoller(events))

    with pytest.raises(RuntimeError, match="stop failed"):
        with TestClient(app):
            pass

    assert events == ["poller:start", "controller:stop", "poller:stop"]


class FailingStartPoller:
    def __init__(self, events):
        self.events = events

    def start(self):
        self.events.append("poller:start")
        raise RuntimeError("poller boom")

    def stop(self):
        self.events.append("poller:stop")


def test_lifespan_cleans_up_when_poller_start_raises():
    events = []
    app = create_app(
        RecordingController(events), profiles=None, creds=None, token="t",
        poller=FailingStartPoller(events))

    # A startup failure must not bypass cleanup: both components still stop.
    with pytest.raises(RuntimeError, match="poller boom"):
        with TestClient(app):
            pass

    assert events == ["poller:start", "controller:stop", "poller:stop"]


def test_lifespan_allows_no_poller():
    events = []
    app = create_app(
        RecordingController(events), profiles=None, creds=None, token="t")
    with TestClient(app):
        pass
    assert events == ["controller:stop"]


class AutoStartController(RecordingController):
    def __init__(self, events, raise_error=None):
        super().__init__(events)
        self.raise_error = raise_error

    def auto_start_if_desired(self):
        self.events.append("controller:auto_start")
        if self.raise_error is not None:
            raise self.raise_error


def test_lifespan_auto_starts_after_poller():
    events = []
    app = create_app(
        AutoStartController(events), profiles=None, creds=None, token="t",
        poller=RecordingPoller(events))
    with TestClient(app):
        assert events[:2] == ["poller:start", "controller:auto_start"]


def test_lifespan_survives_auto_start_failure():
    events = []
    app = create_app(
        AutoStartController(events, RuntimeError("auto boom")),
        profiles=None, creds=None, token="t", poller=RecordingPoller(events))
    # The web app must still boot and serve even though auto-start raised.
    with TestClient(app) as client:
        assert client.get("/api/state").status_code == 200
    assert "controller:auto_start" in events
    assert events[-1] == "poller:stop"
