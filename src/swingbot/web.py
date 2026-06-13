from __future__ import annotations

import os
import pathlib
import threading
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from swingbot.data.market import timeframe_seconds
from swingbot import presets as presets_mod
import swingbot.discovery as discovery_mod
from swingbot.strategy_search import backtest_profile, search as run_strategy_search
from swingbot.universe import fallback_universe
from swingbot.broker.alpaca import AlpacaBroker

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
    brain_model: str | None = None
    brain_ollama_url: str | None = None
    brain_confidence_threshold: float | None = None
    brain_timeout_s: int | None = None
    brain_autonomous_mode: bool | None = None
    brain_auto_recommend: bool | None = None


class WatchlistBody(BaseModel):
    symbols: list[str]


class BuildBody(BaseModel):
    symbol: str
    risk: str = "balanced"
    style: str = "swing"
    ai: bool = False


class BacktestBody(BaseModel):
    profile: dict


class DiscoveryRefreshBody(BaseModel):
    window: str = "full"
    scope: str = "universe"
    max_symbols: int = 50


class DiscoveryArmBody(BaseModel):
    symbol: str
    archetype: str
    window: str | None = None


class WebhookBody(BaseModel):
    url: str


def create_app(controller, profiles, creds, token: str, store=None, market=None,
               backfiller=None, discovery=None, discovery_cache_path=None,
               brain=None, agent_dir=None, poller=None) -> FastAPI:
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

    def require_token(x_token: str | None = Header(default=None)):
        if x_token != token:
            raise HTTPException(status_code=401, detail="bad or missing token")

    # ---- read ----
    @app.get("/api/state")
    def state():
        return controller.status()

    @app.get("/api/journal")
    def journal(strategy: str | None = None):
        return controller.journal(strategy)

    @app.get("/api/metrics")
    def metrics(strategy: str | None = None):
        return controller.metrics(strategy)

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
        # TODO(Phase3): serialize onto the loop thread or lock before reload() while the supervisor is running
        controller.reload()
        return {"ok": True}

    @app.post("/api/strategies/disarm")
    def disarm(body: NameBody, _=Depends(require_token)):
        if body.name not in profiles.list_armed():
            raise HTTPException(status_code=404, detail=f"strategy {body.name!r} is not armed")
        controller.flatten(body.name)
        profiles.disarm(body.name)
        # TODO(Phase3): serialize onto the loop thread or lock before reload() while the supervisor is running
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
        # TODO(Phase3): serialize onto the loop thread or lock before reload() while the supervisor is running
        controller.reload()
        return profiles.get_portfolio_settings()

    # ---- universe / watchlist ----
    _universe_cache: dict = {}

    def _resolve_universe():
        if _universe_cache.get("symbols"):
            return _universe_cache["symbols"]
        symbols = fallback_universe()
        try:
            cr = creds.get() if creds is not None else None
            if cr is not None:
                broker = AlpacaBroker(cr.key_id, cr.secret_key, paper=True)
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
        profiles.set_watchlist(body.symbols)
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

    # ---- presets / strategy build (unchanged behavior) ----
    def _require_market_ready():
        if market is None or (creds is not None and creds.get() is None):
            raise HTTPException(status_code=400, detail="set Alpaca credentials in Settings first")

    @app.get("/api/presets")
    def list_presets():
        return [{"key": a.key, "name": a.name, "description": a.description,
                 "signals": a.signals, "profile": presets_mod.archetype_profile(a)}
                for a in presets_mod.ARCHETYPES]

    @app.post("/api/strategy/backtest")
    def strategy_backtest(body: BacktestBody, _=Depends(require_token)):
        _require_market_ready()
        try:
            m = backtest_profile(market, body.profile)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"metrics": {k: getattr(m, k, None) for k in
                ("n_trades", "win_rate", "expectancy", "profit_factor", "max_drawdown")}}

    @app.post("/api/strategy/build")
    def strategy_build(body: BuildBody, _=Depends(require_token)):
        _require_market_ready()
        try:
            return run_strategy_search(market, body.symbol, body.risk, body.style, body.ai)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

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
        try:
            controller.start()
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        if hasattr(controller, "mark_desired"):
            controller.mark_desired(True)   # persist desire only after a successful start
        return {"ok": True}

    @app.post("/api/control/stop")
    def control_stop(_=Depends(require_token)):
        if hasattr(controller, "mark_desired"):
            controller.mark_desired(False)  # clear desire first, then stop
        controller.stop()
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

    # ---- discovery (auto-strategy sweep) ----
    @app.get("/api/discovery")
    def get_discovery():
        return app.state.discovery

    @app.get("/api/discovery/windows")
    def discovery_windows():
        cov: dict = {}
        if store is not None:
            syms = store.symbols()
            pick = next((s for s in syms if s["symbol"] == "BTC/USD"),
                        syms[0] if syms else None)
            if pick:
                cov = store.coverage(pick["symbol"], pick["timeframe"])
        return discovery_mod.windows_for(cov)

    @app.post("/api/discovery/refresh")
    def discovery_refresh(body: DiscoveryRefreshBody, _=Depends(require_token)):
        if discovery is None:
            raise HTTPException(status_code=503,
                                detail="discovery is not configured on this server")
        if app.state.discovery.get("status") == "computing":
            return {"started": False, "status": "computing"}
        if body.scope == "watchlist":
            symbols = profiles.get_watchlist() if profiles is not None else []
        else:
            symbols = _resolve_universe()
        app.state.discovery = {**app.state.discovery, "status": "computing", "error": None}

        def job():
            try:
                rows = discovery.sweep(symbols, window_key=body.window,
                                       max_symbols=body.max_symbols)
                result = {"status": "idle", "error": None, "computed_at": int(time.time()),
                          "window": body.window, "scope": body.scope, "rows": rows}
                app.state.discovery = result
                if discovery_cache_path:
                    discovery_mod.save_cache(discovery_cache_path, result)
                if (brain is not None and profiles is not None
                        and profiles.get_portfolio_settings().get("brain_auto_recommend")):
                    brain.recommend(source="auto-after-discovery")
            except Exception as e:   # a sweep failure must never touch live trading
                app.state.discovery = {**app.state.discovery, "status": "idle",
                                       "error": str(e)}
                print(f"[discovery] {e}")

        threading.Thread(target=job, daemon=True).start()
        return {"started": True}

    @app.post("/api/discovery/arm")
    def discovery_arm(body: DiscoveryArmBody, _=Depends(require_token)):
        arch = next((a for a in presets_mod.ARCHETYPES if a.key == body.archetype), None)
        if arch is None:
            raise HTTPException(status_code=400,
                                detail=f"unknown archetype {body.archetype!r}")
        profile = presets_mod.archetype_profile(arch, body.symbol, "swing")
        name = f"disc-{body.symbol.replace('/', '').lower()}-{body.archetype}"
        try:
            profiles.save(name, profile)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        profiles.arm(name)
        profiles.set_live_eligible(name, True)
        controller.reload()
        return {"ok": True, "name": name}

    # ---- decision brain ----
    def _require_brain():
        if brain is None:
            raise HTTPException(status_code=503, detail="decision brain is not configured")

    @app.post("/api/brain/recommend")
    def brain_recommend(_=Depends(require_token)):
        _require_brain()
        threading.Thread(target=lambda: brain.recommend(source="manual"),
                         daemon=True).start()
        return {"started": True}

    @app.get("/api/brain/proposals")
    def brain_proposals():
        if brain is None:
            return []
        from dataclasses import asdict
        return [asdict(p) for p in brain.proposals.all()]

    @app.post("/api/brain/proposals/{pid}/apply")
    def brain_apply(pid: str, _=Depends(require_token)):
        _require_brain()
        return brain.apply(pid, source="manual")

    @app.post("/api/brain/proposals/{pid}/dismiss")
    def brain_dismiss(pid: str, _=Depends(require_token)):
        _require_brain()
        brain.proposals.mark(pid, "dismissed")
        return {"ok": True}

    @app.get("/api/brain/issues")
    def brain_issues():
        return brain.issues.all() if brain is not None else []

    @app.post("/api/brain/summary")
    def brain_summary(_=Depends(require_token)):
        _require_brain()
        return brain.daily_summary()

    @app.put("/api/brain/webhook")
    def brain_set_webhook(body: WebhookBody, _=Depends(require_token)):
        if profiles is not None:
            profiles.set_discord_webhook(body.url)
        return {"configured": bool(body.url)}

    @app.get("/api/brain/webhook")
    def brain_get_webhook():
        configured = bool(profiles and profiles.get_discord_webhook())
        return {"configured": configured}            # never returns the URL

    # ---- usage agent (read-only) ----
    def _agent_store():
        from swingbot.selftest.agentstore import AgentRunStore
        return AgentRunStore(agent_dir) if agent_dir else None

    @app.get("/api/agent/runs")
    def agent_runs():
        s = _agent_store()
        if s is None:
            return []
        return [{"ts": r.get("ts"), "green": r.get("green"),
                 "duration_s": r.get("duration_s"),
                 "sessions": [{"session": t.get("session"), "ok": t.get("ok")}
                              for t in r.get("traces", [])],
                 "drift_count": len(r.get("drift", []))}
                for r in s.all()]

    @app.get("/api/agent/runs/latest")
    def agent_latest():
        s = _agent_store()
        return (s.latest() if s else None) or {}

    @app.get("/api/agent/artifacts/{name}")
    def agent_artifact(name: str):
        s = _agent_store()
        if s is None:
            raise HTTPException(status_code=404, detail="agent not configured")
        shots = os.path.realpath(s.screenshot_dir)
        path = os.path.realpath(os.path.join(shots, name))
        if not path.startswith(shots + os.sep) or not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="no such artifact")
        return FileResponse(path)

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

    app.state.discovery = {"status": "idle", "computed_at": None, "window": None,
                           "scope": None, "error": None, "rows": []}
    if discovery_cache_path:
        cached = discovery_mod.load_cache(discovery_cache_path)
        if cached:
            app.state.discovery = cached

    app.state.controller = controller
    app.state.profiles = profiles
    app.state.creds = creds
    app.state.token = token

    if os.path.isdir(_DIST):
        app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")

    return app
