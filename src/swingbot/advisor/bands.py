from __future__ import annotations

_TUNABLE = ("threshold_pct", "tp_pct", "sl_pct", "weight")

BANDS = {
    "cautious": {
        "threshold_pct": (0.005, 0.015),
        "tp_pct": (0.008, 0.025),
        "sl_pct": (0.005, 0.012),
        "weight": (0.0, 1.0),
    },
    "balanced": {
        "threshold_pct": (0.004, 0.020),
        "tp_pct": (0.008, 0.050),
        "sl_pct": (0.005, 0.020),
        "weight": (0.0, 1.0),
    },
    "aggressive": {
        "threshold_pct": (0.003, 0.030),
        "tp_pct": (0.010, 0.080),
        "sl_pct": (0.008, 0.030),
        "weight": (0.0, 1.0),
    },
}
