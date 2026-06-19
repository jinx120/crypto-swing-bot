from __future__ import annotations

from fastapi import APIRouter


def build_auto_router(service) -> APIRouter:
    router = APIRouter()

    @router.get("/api/backtest/ema")
    def backtest_ema():
        return service.backtest()["ema"]

    @router.get("/api/backtest/kronos")
    def backtest_kronos():
        return service.backtest()["kronos"]

    @router.get("/api/live/position")
    def live_position():
        return service.position()

    @router.get("/api/live/trades")
    def live_trades(limit: int = 50):
        return service.trades(limit)

    @router.get("/api/live/journal")
    def live_journal(limit: int = 50):
        return service.journal(limit)

    @router.get("/api/live/candles")
    def live_candles(limit: int = 200):
        return service.candles(limit)

    return router
