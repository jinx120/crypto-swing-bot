from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from swingbot.profiles import ProfileStore
from swingbot.supervisor import PortfolioSupervisor
from swingbot.telemetry import CycleRecord
from swingbot.types import DecisionCode
from swingbot.web import create_app
from tests.test_supervisor import FakeBroker, FakeMarket, T0, _bars, _profile, _supervisor


class HealthController:
    def readiness(self):
        return {"ready": False, "checks": {"credentials": {"ok": False, "detail": "missing"}}}

    def trading_health(self):
        return {"status": "inactive", "reliability": {"completed_cycles": 0}}


def _client(controller=None):
    return TestClient(create_app(
        controller=controller or HealthController(),
        profiles=None,
        creds=None,
        token="t",
    ))


def _lifecycle(desired, actual):
    return {
        "mode": "paper",
        "running_flag": actual,
        "thread_alive": actual,
        "running_actual": actual,
        "running_desired": desired,
        "running_desired_error": None if desired is not None else "unreadable",
        "paused": False,
        "halted": False,
        "startup_error": None,
    }


def _cycle(cycle_id="c1", *, ingest="ok", reconcile="ok", persist="ok"):
    return CycleRecord(
        cycle_id=cycle_id,
        strategy="btc",
        started_at=T0,
        completed_at=T0 + timedelta(seconds=1),
        bar_ts=T0 - timedelta(minutes=15),
        ingest=ingest,
        reconcile=reconcile,
        manage="skipped",
        decide="ok",
        persist=persist,
        decision_code=DecisionCode.SIGNAL_BELOW_THRESHOLD,
        decision_reason="score below threshold",
        decision_details={"score": 0.2},
    )


def test_live_route_always_returns_process_liveness():
    response = _client().get("/api/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "live"
    assert datetime.fromisoformat(response.json()["served_at"]).tzinfo is not None


def test_ready_and_trading_routes_delegate_without_token():
    client = _client()

    ready = client.get("/api/health/ready")
    trading = client.get("/api/health/trading")

    assert ready.status_code == 200 and ready.json()["ready"] is False
    assert trading.status_code == 200 and trading.json()["status"] == "inactive"


def test_readiness_names_missing_credentials_and_no_armed_strategy(tmp_path):
    profiles = ProfileStore(str(tmp_path / "profiles.db"))
    sup = PortfolioSupervisor(
        profiles=profiles,
        creds=None,
        state_db=str(tmp_path / "state.db"),
        market=FakeMarket({}),
        broker=FakeBroker(),
    )

    result = sup.readiness()

    assert result["ready"] is False
    assert result["checks"]["credentials"]["ok"] is False
    assert result["checks"]["armed_strategies"]["ok"] is False


def test_readiness_fails_on_latest_critical_stage_failure(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD"])
    sup._telemetry.record(_cycle(ingest="failed"))
    sup.lifecycle_state = lambda: _lifecycle(True, True)
    sup.creds = type("Creds", (), {"get": lambda self: object()})()

    result = sup.readiness()

    assert result["ready"] is False
    assert result["checks"]["latest_critical_stages"]["ok"] is False


def test_trading_is_inactive_when_running_is_not_desired(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD"])
    sup.lifecycle_state = lambda: _lifecycle(False, False)

    assert sup.trading_health()["status"] == "inactive"


def test_trading_is_immediately_unhealthy_when_desired_but_not_running(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD"])
    sup._telemetry.record(_cycle())
    sup.lifecycle_state = lambda: _lifecycle(True, False)

    result = sup.trading_health()

    assert result["status"] == "unhealthy"
    assert result["reliability"]["cycle_completion_ratio"] == 1.0


def test_trading_is_unhealthy_when_desire_is_unreadable(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD"])
    sup.lifecycle_state = lambda: _lifecycle(None, False)

    assert sup.trading_health()["status"] == "unhealthy"


def test_active_trading_includes_latest_cycles_decisions_counts_and_window(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD"])
    sup._telemetry.record(_cycle())
    sup.lifecycle_state = lambda: _lifecycle(True, True)

    result = sup.trading_health()

    assert result["status"] == "active"
    assert result["last_cycle"]["cycle_id"] == "c1"
    assert result["last_decisions_by_strategy"]["btc"]["decision_code"] == (
        DecisionCode.SIGNAL_BELOW_THRESHOLD.value
    )
    assert result["reliability"]["completed_cycles"] == 1
    assert result["reliability"]["window_started_at"] is not None
    assert result["reliability"]["window_completed_at"] is not None


def test_trading_stage_denominators_exclude_skipped_and_ratios_have_counts(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD"])
    sup._telemetry.record(_cycle())
    sup.lifecycle_state = lambda: _lifecycle(True, True)

    reliability = sup.trading_health()["reliability"]

    assert reliability["stages"]["manage"]["samples"] == 0
    assert reliability["stages"]["manage"]["ratio"] is None
    for stage in reliability["stages"].values():
        assert {"ok", "failed", "skipped", "samples", "ratio"} <= set(stage)
    assert not any("percent" in key.lower() for key in reliability)
