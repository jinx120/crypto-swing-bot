from __future__ import annotations

from swingbot.metrics import Metrics


def can_go_live(metrics: Metrics, min_trades: int = 30,
                min_expectancy: float = 0.0) -> tuple[bool, str]:
    """Server-side gate: paper results must clear these bars before LIVE."""
    if metrics.n_trades < min_trades:
        return (False, f"need >= {min_trades} paper trades (have {metrics.n_trades})")
    if metrics.expectancy <= min_expectancy:
        return (False, f"expectancy {metrics.expectancy:.4f} must exceed {min_expectancy}")
    return (True, "ok")
