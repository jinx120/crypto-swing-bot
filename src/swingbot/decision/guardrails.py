from __future__ import annotations

from swingbot.decision.proposals import Proposal

TUNE_BOUNDS = {
    "entry_threshold": (0.3, 0.95),
    "stop_atr_mult": (0.5, 4.0),
    "take_profit_atr_mult": (1.0, 6.0),
    "risk_per_trade": (0.0025, 0.03),
    "max_position_frac": (0.05, 0.5),
}
SETTINGS_BOUNDS = {
    "max_concurrent": (1, 20),
    "max_total_deployed_frac": (0.0, 0.90),
    "portfolio_daily_loss_limit_pct": (0.0, 0.20),
}
_OPEN = "approved", ""


def _block(reason: str):
    return "blocked", reason


def evaluate(p: Proposal, ctx: dict, eligible_rows: list[dict], backtest_ok) -> tuple[str, str]:
    """Pure pre-apply gate. Returns (status, reason). backtest_ok(symbol, archetype, params)
    -> bool is only consulted for `tune`."""
    if p.action == "arm":
        sym, arch = p.target.get("symbol"), p.target.get("archetype")
        if not any(r.get("symbol") == sym and r.get("archetype") == arch for r in eligible_rows):
            return _block(f"{sym}/{arch} is not a currently-eligible candidate")
        if ctx.get("kill_switch"):
            return _block("portfolio kill switch active")
        if ctx.get("open_position_count", 0) >= ctx.get("max_concurrent", 5):
            return _block("max concurrent positions reached")
        if ctx.get("deployed_frac", 0.0) >= ctx.get("max_total_deployed_frac", 0.80):
            return _block("deployed-capital cap reached")
        return _OPEN

    if p.action == "disarm":
        if p.target.get("name") not in (ctx.get("armed") or []):
            return _block(f"{p.target.get('name')!r} is not armed")
        return _OPEN

    if p.action == "tune":
        params = p.target.get("params") or {}
        if not params:
            return _block("tune has no params")
        for field, val in params.items():
            if field not in TUNE_BOUNDS:
                return _block(f"non-tunable field {field!r}")
            lo, hi = TUNE_BOUNDS[field]
            if not isinstance(val, (int, float)) or not (lo <= val <= hi):
                return _block(f"{field}={val} out of bounds [{lo}, {hi}]")
        if not backtest_ok(p.target.get("symbol"), p.target.get("archetype"), params):
            return _block("tuned profile fails good_history backtest")
        return _OPEN

    if p.action == "portfolio_settings":
        if not p.target:
            return _block("no settings to change")
        for field, val in p.target.items():
            if field not in SETTINGS_BOUNDS:
                return _block(f"unknown setting {field!r}")
            lo, hi = SETTINGS_BOUNDS[field]
            if not isinstance(val, (int, float)) or not (lo <= val <= hi):
                return _block(f"{field}={val} out of bounds [{lo}, {hi}]")
        return _OPEN

    return _block(f"unknown action {p.action!r}")
