from __future__ import annotations

import os
import pathlib

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from swingbot.data.market import timeframe_seconds
from swingbot import presets as presets_mod
from swingbot.strategy_search import backtest_profile, search as run_strategy_search

_DIST = str(pathlib.Path(__file__).parent.parent.parent / "frontend" / "dist")


class ProfileBody(BaseModel):
    name: str
    profile: dict


class ActiveBody(BaseModel):
    name: str


class CredBody(BaseModel):
    key_id: str
    secret_key: str
    base_url: str = "https://paper-api.alpaca.markets"


class ModeBody(BaseModel):
    mode: str


class BuildBody(BaseModel):
    symbol: str
    risk: str = "balanced"
    style: str = "swing"
    ai: bool = False


class BacktestBody(BaseModel):
    profile: dict


def create_app(controller, profiles, creds, token: str, store=None, market=None) -> FastAPI:
    app = FastAPI(title="swingbot")

    def require_token(x_token: str | None = Header(default=None)):
        if x_token != token:
            raise HTTPException(status_code=401, detail="bad or missing token")

    @app.get("/api/state")
    def state():
        return controller.status()

    @app.get("/api/candles")
    def candles(symbol: str | None = None, timeframe: str | None = None,
                limit: int = 500):
        """OHLC bars for the chart. Defaults to the active profile's
        symbol/timeframe when not specified. Read-only (no token)."""
        if symbol is None or timeframe is None:
            active = (profiles.get_active() if profiles else None) or {}
            symbol = symbol or active.get("symbol")
            timeframe = timeframe or active.get("timeframe", "15m")
        if not symbol:
            return {"symbol": symbol, "timeframe": timeframe, "candles": []}
        limit = max(1, min(limit, 1500))
        if market is not None:
            bars = market.get(symbol, timeframe, limit,
                              max_age=timeframe_seconds(timeframe))
        elif store is not None:
            bars = store.get(symbol, timeframe, limit)
        else:
            bars = []
        return {"symbol": symbol, "timeframe": timeframe, "candles": bars}

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

    @app.get("/api/journal")
    def journal():
        return controller.journal()

    @app.get("/api/metrics")
    def metrics():
        return controller.metrics()

    @app.post("/api/control/halt")
    def halt(_=Depends(require_token)):
        controller.halt()
        return {"ok": True}

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

    @app.get("/api/profiles/active")
    def active_profile():
        return {"name": profiles.get_active_name(), "profile": profiles.get_active()}

    @app.post("/api/profiles/active")
    def set_active(body: ActiveBody, _=Depends(require_token)):
        try:
            profiles.set_active(body.name)
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

    @app.get("/api/credentials")
    def cred_status():
        return creds.status()

    @app.put("/api/credentials")
    def set_creds(body: CredBody, _=Depends(require_token)):
        creds.set(body.key_id, body.secret_key, body.base_url)
        return {"ok": True}

    @app.post("/api/control/start")
    def control_start(_=Depends(require_token)):
        try:
            controller.start()
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True}

    @app.post("/api/control/stop")
    def control_stop(_=Depends(require_token)):
        controller.stop(); return {"ok": True}

    @app.post("/api/control/reset")
    def control_reset(_=Depends(require_token)):
        controller.reset(); return {"ok": True}

    @app.post("/api/control/pause")
    def control_pause(_=Depends(require_token)):
        controller.pause(); return {"ok": True}

    @app.post("/api/control/resume")
    def control_resume(_=Depends(require_token)):
        controller.resume(); return {"ok": True}

    @app.post("/api/control/flatten")
    def control_flatten(_=Depends(require_token)):
        controller.flatten(); return {"ok": True}

    @app.post("/api/control/mode")
    def control_mode(body: ModeBody, _=Depends(require_token)):
        ok, reason = controller.set_mode(body.mode)
        return {"ok": ok, "reason": reason}

    app.state.controller = controller
    app.state.profiles = profiles
    app.state.creds = creds
    app.state.token = token

    if os.path.isdir(_DIST):
        app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")

    return app
