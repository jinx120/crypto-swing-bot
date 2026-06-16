from __future__ import annotations

# Bump when the managed definitions below change in a way that should re-seed.
MANAGED_VERSION = 1

# Every name the reconciler is allowed to create/own. Anything NOT in this set
# is a user profile and must never be deleted or overwritten.
MANAGED_PROFILE_NAMES = {"btc_trend", "eth_trend", "paper_probe"}

# UI/labeling metadata so the dashboard can distinguish strategies from the probe.
MANAGED_LABELS = {
    "btc_trend": {"kind": "strategy", "label": "BTC Trend (EMA)"},
    "eth_trend": {"kind": "strategy", "label": "ETH Trend (EMA)"},
    "paper_probe": {"kind": "probe", "label": "proof-of-life probe"},
}


def _trend_profile(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "benchmark_symbol": "BTC/USD",
        "timeframe": "15m",
        "htf_timeframe": "4h",
        "signals": {"ema_trend": {"weight": 1.0, "fast": 12, "slow": 26, "band": 0.01}},
        "entry_threshold": 0.5,
        "regime_ma_period": 50,
        "allowed_regimes": ["uptrend", "neutral"],
        "atr_period": 14,
        "stop_atr_mult": 1.5,
        "take_profit_atr_mult": 2.0,
        "max_hold_bars": 32,
        "risk_per_trade": 0.01,
        "max_position_frac": 0.25,
    }


def _probe_profile() -> dict:
    # Deterministic, market-independent. Allows every regime so the regime gate
    # cannot block a bounded paper entry through the normal pipeline.
    return {
        "symbol": "BTC/USD",
        "benchmark_symbol": "BTC/USD",
        "timeframe": "15m",
        "htf_timeframe": "4h",
        "signals": {"paper_probe": {"weight": 1.0}},
        "entry_threshold": 0.5,
        "regime_ma_period": 50,
        "allowed_regimes": ["uptrend", "neutral", "downtrend"],
        "atr_period": 14,
        "stop_atr_mult": 1.5,
        "take_profit_atr_mult": 2.0,
        "max_hold_bars": 8,
        "risk_per_trade": 0.002,
        "max_position_frac": 0.02,
    }


def managed_definitions(enable_probe: bool) -> dict[str, dict]:
    """Return name -> profile dict for managed profiles."""
    defs: dict[str, dict] = {
        "btc_trend": _trend_profile("BTC/USD"),
        "eth_trend": _trend_profile("ETH/USD"),
    }
    if enable_probe:
        defs["paper_probe"] = _probe_profile()
    return defs
