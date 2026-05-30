from __future__ import annotations

from swingbot.signals.kronos_adapter import KronosAdapter
from swingbot.types import MarketContext, SignalResult


class KronosForecastSignal:
    """Kronos-based forecast signal. Satisfies the Signal protocol.

    In tests, inject a pre-built KronosAdapter via _adapter=.
    In production (build_signals), omit _adapter and the signal
    calls KronosAdapter.from_profile() to load the real model.
    """

    name = "kronos_forecast"

    def __init__(
        self,
        weight: float,
        pred_len: int = 4,
        threshold_pct: float = 0.02,
        min_history: int = 50,
        neutral_on_error: bool = True,
        _adapter: KronosAdapter | None = None,
    ) -> None:
        self.weight = weight
        self.threshold_pct = threshold_pct
        self.min_history = min_history
        self.neutral_on_error = neutral_on_error
        self.adapter = _adapter or KronosAdapter.from_profile({"pred_len": pred_len})

    def evaluate(self, ctx: MarketContext) -> SignalResult:
        if len(ctx.candles) < self.min_history:
            return SignalResult(self.name, 0.0, {"error": "insufficient_history"})

        forecast = self.adapter.forecast(ctx.candles)
        if forecast is None:
            fallback = 0.5 if self.neutral_on_error else 0.0
            return SignalResult(self.name, fallback, {"error": "no_forecast"})

        current_close = float(ctx.candles["close"].iloc[-1])
        forecast_close = float(forecast["close"].iloc[-1])
        pct_change = (forecast_close - current_close) / current_close
        score = max(0.0, min(1.0, pct_change / self.threshold_pct))
        return SignalResult(
            self.name,
            score,
            {"pct_change": pct_change, "forecast_close": forecast_close},
        )
