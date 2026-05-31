from __future__ import annotations

import os
import pathlib

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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


def create_app(controller, profiles, creds, token: str) -> FastAPI:
    app = FastAPI(title="swingbot")

    def require_token(x_token: str | None = Header(default=None)):
        if x_token != token:
            raise HTTPException(status_code=401, detail="bad or missing token")

    @app.get("/api/state")
    def state():
        return controller.status()

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
