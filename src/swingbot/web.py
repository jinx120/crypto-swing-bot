from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel


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

    app.state.controller = controller
    app.state.profiles = profiles
    app.state.creds = creds
    app.state.token = token
    return app
