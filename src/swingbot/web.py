from __future__ import annotations

import os
import pathlib
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from swingbot.data.market import timeframe_seconds
from swingbot.universe import fallback_universe
from swingbot.kronos_preset import kronos_bracket_profile
from swingbot.profiles import ProfileStore
from swingbot.supervisor import LifecycleError
from swingbot.rebalance import RebalanceSettings

_DIST = str(pathlib.Path(__file__).parent.parent.parent / "frontend" / "dist")


class ProfileBody(BaseModel):
    name: str
    profile: dict


class NameBody(BaseModel):
    name: str


class CredBody(BaseModel):
    key_id: str
    secret_key: str
    base_url: str = "https://paper-api.alpaca.markets"


class BrokerCredBody(BaseModel):
    values: dict


class BrokerTestBody(BaseModel):
    values: dict | None = None
    mode: str | None = None


class ActiveBrokerBody(BaseModel):
    broker_id: str


class ModeBody(BaseModel):
    mode: str


class LiveEligibleBody(BaseModel):
    name: str
    eligible: bool


class PortfolioSettingsBody(BaseModel):
    max_concurrent: int | None = None
    max_total_deployed_frac: float | None = None
    portfolio_daily_loss_limit_pct: float | None = None
    default_symbol: str | None = None


class WatchlistBody(BaseModel):
    symbols: list[str]


def _kronos_profile_name(symbol: str) -> str:
    return f"kronos-{symbol.replace('/', '-').lower()}"


class DataSourceBody(BaseModel):
    data_source: str


class RiskDialBody(BaseModel):
    risk_dial: str


class AdvisorRevertBody(BaseModel):
    batch_id: str


def create_app(controller, profiles, creds, token: str, store=None, market=None,
               backfiller=None, poller=None, advisor_journal=None,
               auto_dashboard=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            if poller is not None:
                poller.start()
            if controller is not None and hasattr(controller, "auto_start_if_desired"):
                try:
                    controller.auto_start_if_desired()
                except Exception as e:   # auto-start must never prevent the app from serving
                    print(f"[lifespan] auto-start error: {e}")
            yield
        finally:
            try:
                if controller is not None and hasattr(controller, "stop"):
                    controller.stop()
            finally:
                if poller is not None:
                    poller.stop()

    app = FastAPI(title="swingbot", lifespan=lifespan)

    if auto_dashboard is not None:
        from swingbot.autodash.router import build_auto_router
        app.include_router(build_auto_router(auto_dashboard))

    def require_token(x_token: str | None = Header(default=None)):
        # Auth is opt-in: enforced only when the app is built with a non-empty
        # token. Shipped with no token (single-user paper bot reached from several
        # personal devices) so every endpoint is open and no token is ever needed.
        if token and x_token != token:
            raise HTTPException(status_code=401, detail="bad or missing token")

    # ---- read ----
    @app.get("/api/state")
    def state():
        return controller.status()

    @app.get("/api/journal")
    def journal(strategy: str | None = None):
        return controller.journal(strategy)

    @app.get("/api/decisions")
    def decisions(strategy: str | None = None, limit: int = 50):
        return controller.decisions(strategy, limit)

    @app.get("/api/metrics")
    def metrics(strategy: str | None = None):
        return controller.metrics(strategy)

    @app.get("/api/health/live")
    def health_live():
        return {"status": "live", "served_at": datetime.now(timezone.utc).isoformat()}

    @app.get("/api/health/ready")
    def health_ready():
        return controller.readiness()

    @app.get("/api/health/trading")
    def health_trading():
        return controller.trading_health()

    @app.get("/api/candles")
    def candles(symbol: str | None = None, timeframe: str | None = None, limit: int = 500):
        if symbol is None or timeframe is None:
            armed = profiles.list_armed() if profiles else []
            first = (profiles.get(armed[0]) if armed else None) or {}
            symbol = symbol or first.get("symbol")
            timeframe = timeframe or first.get("timeframe", "15m")
        if not symbol:
            return {"symbol": symbol, "timeframe": timeframe, "candles": []}
        limit = max(1, min(limit, 1500))
        if market is not None:
            bars = market.get(symbol, timeframe, limit, max_age=timeframe_seconds(timeframe))
        elif store is not None:
            bars = store.get(symbol, timeframe, limit)
        else:
            bars = []
        return {"symbol": symbol, "timeframe": timeframe, "candles": bars}

    # ---- strategies / arming ----
    @app.get("/api/strategies")
    def list_strategies():
        flags = {f["name"]: f["live_eligible"] for f in profiles.armed_with_flags()}
        out = []
        for name in profiles.list():
            p = profiles.get(name) or {}
            out.append({"name": name, "symbol": p.get("symbol"),
                        "armed": name in flags, "live_eligible": flags.get(name, False)})
        return out

    @app.post("/api/strategies/arm")
    def arm(body: NameBody, _=Depends(require_token)):
        try:
            profiles.arm(body.name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        controller.reload()
        return {"ok": True}

    @app.post("/api/strategies/disarm")
    def disarm(body: NameBody, _=Depends(require_token)):
        if body.name not in profiles.list_armed():
            raise HTTPException(status_code=404, detail=f"strategy {body.name!r} is not armed")
        controller.flatten(body.name)
        profiles.disarm(body.name)
        controller.reload()
        return {"ok": True}

    @app.post("/api/strategies/live-eligible")
    def live_eligible(body: LiveEligibleBody, _=Depends(require_token)):
        try:
            profiles.set_live_eligible(body.name, body.eligible)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True}

    # ---- portfolio settings ----
    @app.get("/api/portfolio/settings")
    def get_portfolio_settings():
        return profiles.get_portfolio_settings()

    @app.put("/api/portfolio/settings")
    def set_portfolio_settings(body: PortfolioSettingsBody, _=Depends(require_token)):
        patch = {k: v for k, v in body.model_dump().items() if v is not None}
        try:
            profiles.set_portfolio_settings(patch)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        controller.reload()
        return profiles.get_portfolio_settings()

    # ---- rebalance settings ----
    @app.get("/api/rebalance/settings")
    def get_rebalance_settings():
        return {**asdict(RebalanceSettings()), **profiles.get_rebalance_settings()}

    @app.post("/api/rebalance/settings")
    def set_rebalance_settings(body: dict, _=Depends(require_token)):
        profiles.set_rebalance_settings(body)
        controller.reload()
        return {"ok": True}

    @app.get("/api/rebalance/targets")
    def get_rebalance_targets():
        return {"targets": profiles.get_rebalance_targets()}

    @app.post("/api/rebalance/targets")
    def set_rebalance_targets(body: dict, _=Depends(require_token)):
        try:
            profiles.set_rebalance_targets(body.get("targets", {}))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        controller.reload()
        return {"ok": True}

    @app.get("/api/rebalance/status")
    def rebalance_status():
        return controller.rebalance_status()

    @app.post("/api/rebalance/run")
    def rebalance_run(_=Depends(require_token)):
        return controller.run_rebalance_now()

    # ---- data source ----
    @app.get("/api/data-source")
    def get_data_source():
        return {
            "data_source": profiles.get_data_source(),
            "choices": list(ProfileStore._DATA_SOURCES),
        }

    @app.put("/api/data-source")
    def put_data_source(body: DataSourceBody, _=Depends(require_token)):
        try:
            profiles.set_data_source(body.data_source)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if market is not None:
            market.data_source = body.data_source
        controller.reload()
        return {"ok": True, "data_source": body.data_source}

    # ---- advisor / risk dial ----
    @app.get("/api/risk-dial")
    def get_risk_dial():
        return {"risk_dial": profiles.get_risk_dial()}

    @app.put("/api/risk-dial")
    def put_risk_dial(body: RiskDialBody, _=Depends(require_token)):
        try:
            profiles.set_risk_dial(body.risk_dial)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True, "risk_dial": profiles.get_risk_dial()}

    def _advisor_entries():
        return advisor_journal.list_entries() if advisor_journal is not None else []

    @app.get("/api/advisor/notes")
    def advisor_notes():
        return [row for row in _advisor_entries() if row.get("rationale")]

    @app.get("/api/advisor/journal")
    def advisor_journal_rows():
        return _advisor_entries()

    def _apply_inverse_changes(changes: list[dict]) -> None:
        dirty = False
        for change in changes:
            symbol = change["symbol"]
            for name in profiles.list():
                profile = profiles.get(name) or {}
                if profile.get("symbol") != symbol:
                    continue
                profile[change["param"]] = change["value"]
                profiles.save(name, profile)
                dirty = True
                break
        if dirty:
            controller.reload()

    @app.post("/api/advisor/revert")
    def advisor_revert(body: AdvisorRevertBody, _=Depends(require_token)):
        if advisor_journal is None:
            raise HTTPException(status_code=503, detail="advisor journal is not configured")
        changes = advisor_journal.revert(body.batch_id)
        _apply_inverse_changes(changes)
        return {"ok": True, "changes": changes}

    @app.post("/api/advisor/revert-all")
    def advisor_revert_all(_=Depends(require_token)):
        if advisor_journal is None:
            raise HTTPException(status_code=503, detail="advisor journal is not configured")
        changes = advisor_journal.revert_all()
        _apply_inverse_changes(changes)
        return {"ok": True, "changes": changes}

    # ---- universe / watchlist ----
    _universe_cache: dict = {}

    def _resolve_universe():
        if _universe_cache.get("symbols"):
            return _universe_cache["symbols"]
        symbols = fallback_universe()
        try:
            broker = creds.make_broker(mode="paper") if creds is not None else None
            if broker is not None and hasattr(broker, "list_usd_pairs"):
                live = broker.list_usd_pairs()
                if live:
                    symbols = live
                    _universe_cache["symbols"] = live
        except Exception:
            pass  # fall back to static list
        return symbols

    @app.get("/api/universe")
    def universe():
        return {"symbols": _resolve_universe()}

    @app.get("/api/watchlist")
    def get_watchlist():
        return {"symbols": profiles.get_watchlist()}

    @app.put("/api/watchlist")
    def put_watchlist(body: WatchlistBody, _=Depends(require_token)):
        existing = set(profiles.get_watchlist())
        profiles.set_watchlist(body.symbols)
        created = False
        for symbol in profiles.get_watchlist():
            if symbol in existing:
                continue
            name = _kronos_profile_name(symbol)
            profiles.save(name, kronos_bracket_profile(symbol))
            profiles.arm(name)
            created = True
        if created:
            controller.reload()
        return {"symbols": profiles.get_watchlist()}

    # ---- profiles CRUD ----
    @app.get("/api/profiles")
    def list_profiles():
        return profiles.list()

    @app.post("/api/profiles")
    def save_profile(body: ProfileBody, _=Depends(require_token)):
        try:
            profiles.save(body.name, body.profile)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True}

    @app.get("/api/profiles/{name}")
    def get_profile(name: str):
        p = profiles.get(name)
        if p is None:
            raise HTTPException(status_code=404, detail=f"no profile {name!r}")
        return {"name": name, "profile": p}

    @app.delete("/api/profiles/{name}")
    def delete_profile(name: str, _=Depends(require_token)):
        profiles.delete(name)
        return {"ok": True}

    # ---- credentials ----
    @app.get("/api/credentials")
    def cred_status():
        return creds.status()

    @app.put("/api/credentials")
    def set_creds(body: CredBody, _=Depends(require_token)):
        creds.set(body.key_id, body.secret_key, body.base_url)
        return {"ok": True}

    # ---- broker connection manager ----
    @app.get("/api/brokers")
    def list_brokers():
        return creds.list_brokers()

    @app.put("/api/brokers/{broker_id}/credentials")
    def set_broker_credentials(broker_id: str, body: BrokerCredBody,
                               _=Depends(require_token)):
        try:
            creds.set_broker(broker_id, body.values)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True}

    @app.post("/api/brokers/{broker_id}/test")
    def test_broker(broker_id: str, body: BrokerTestBody, _=Depends(require_token)):
        try:
            return creds.test_broker(broker_id, body.values, body.mode)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/brokers/active")
    def set_active_broker(body: ActiveBrokerBody, _=Depends(require_token)):
        try:
            creds.set_active(body.broker_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True, "active": creds.active()}

    @app.post("/api/brokers/reconnect")
    def reconnect_broker(_=Depends(require_token)):
        if not hasattr(controller, "reconnect"):
            raise HTTPException(status_code=503, detail="reconnect not supported")
        ok, detail = controller.reconnect()
        return {"ok": ok, "detail": detail}

    # ---- controls (portfolio-level + per-strategy) ----
    @app.post("/api/control/halt")
    def halt(_=Depends(require_token)):
        controller.halt(); return {"ok": True}

    @app.post("/api/control/reset")
    def control_reset(_=Depends(require_token)):
        controller.reset(); return {"ok": True}

    @app.post("/api/control/pause")
    def control_pause(_=Depends(require_token)):
        controller.pause(); return {"ok": True}

    @app.post("/api/control/resume")
    def control_resume(_=Depends(require_token)):
        controller.resume(); return {"ok": True}

    @app.post("/api/control/start")
    def control_start(_=Depends(require_token)):
        # request_start serializes start + desire persistence under the supervisor
        # lifecycle lock; fall back to bare start() for fakes that lack it.
        try:
            if hasattr(controller, "request_start"):
                controller.request_start()
            else:
                controller.start()
        except LifecycleError as e:
            # Partial/incomplete lifecycle outcome (e.g. started-but-not-persisted,
            # rollback timed out). Report truthfully, never as success.
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            # Pre-condition failures (e.g. duplicate live thread) — bad request.
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True}

    @app.post("/api/control/stop")
    def control_stop(_=Depends(require_token)):
        # request_stop clears desire before stopping, atomically; fall back to
        # bare stop() for fakes that lack it.
        try:
            if hasattr(controller, "request_stop"):
                controller.request_stop()
            else:
                controller.stop()
        except LifecycleError as e:
            raise HTTPException(status_code=500, detail=str(e))
        return {"ok": True}

    @app.get("/api/control/lifecycle")
    def control_lifecycle():
        if hasattr(controller, "lifecycle_state"):
            return controller.lifecycle_state()
        return {}

    @app.post("/api/control/flatten")
    def control_flatten(_=Depends(require_token)):
        controller.flatten(); return {"ok": True}

    @app.post("/api/control/mode")
    def control_mode(body: ModeBody, _=Depends(require_token)):
        ok, reason = controller.set_mode(body.mode)
        return {"ok": ok, "reason": reason}

    @app.post("/api/control/{name}/flatten")
    def control_flatten_one(name: str, _=Depends(require_token)):
        controller.flatten(name); return {"ok": True}

    # ---- archive (deep historical backfill) ----
    @app.get("/api/archive/status")
    def archive_status():
        if store is None:
            return []
        out = []
        for entry in store.symbols():
            cov = store.coverage(entry["symbol"], entry["timeframe"])
            out.append({"symbol": entry["symbol"], "timeframe": entry["timeframe"],
                        **cov})
        return out

    @app.post("/api/archive/backfill")
    def archive_backfill(_=Depends(require_token)):
        if backfiller is None or getattr(app.state, "archive_config", None) is None:
            raise HTTPException(status_code=503,
                                detail="archive backfill is not configured on this server")
        cfg = app.state.archive_config

        def job():
            try:
                backfiller.run(cfg)
            except Exception as e:  # a backfill failure must never touch live trading
                print(f"[archive-backfill] {e}")

        threading.Thread(target=job, daemon=True).start()
        return {"started": True}

    app.state.archive_config = None
    if backfiller is not None:
        from swingbot.data.backfill import ArchiveConfig
        app.state.archive_config = ArchiveConfig()

    app.state.controller = controller
    app.state.profiles = profiles
    app.state.creds = creds
    app.state.token = token

    if os.path.isdir(_DIST):
        app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")

    return app
