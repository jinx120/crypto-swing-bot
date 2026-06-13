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


def test_lifespan_allows_no_poller():
    events = []
    app = create_app(
        RecordingController(events), profiles=None, creds=None, token="t")
    with TestClient(app):
        pass
    assert events == ["controller:stop"]
