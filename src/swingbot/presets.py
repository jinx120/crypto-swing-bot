from __future__ import annotations

from dataclasses import dataclass

from swingbot.profile import StrategyProfile

# risk knob -> sizing / exit / breaker params
RISK = {
    "conservative": dict(risk_per_trade=0.005, stop_atr_mult=1.2, take_profit_atr_mult=2.4,
                         entry_threshold=0.45, daily_loss_limit_pct=0.03, max_consecutive_losses=3),
    "balanced":     dict(risk_per_trade=0.01,  stop_atr_mult=1.5, take_profit_atr_mult=2.0,
                         entry_threshold=0.35, daily_loss_limit_pct=0.05, max_consecutive_losses=4),
    "aggressive":   dict(risk_per_trade=0.02,  stop_atr_mult=2.0, take_profit_atr_mult=3.0,
                         entry_threshold=0.30, daily_loss_limit_pct=0.08, max_consecutive_losses=5),
}

# style knob -> timeframe / horizon / window params
STYLE = {
    "scalp":    dict(timeframe="5m",  max_hold_bars=24, regime_ma_period=50,  vwap_window=48, rs_lookback=48, cooldown_minutes=30),
    "swing":    dict(timeframe="15m", max_hold_bars=32, regime_ma_period=50,  vwap_window=96, rs_lookback=96, cooldown_minutes=60),
    "position": dict(timeframe="1h",  max_hold_bars=24, regime_ma_period=100, vwap_window=96, rs_lookback=96, cooldown_minutes=240),
}


@dataclass
class Archetype:
    key: str
    name: str
    description: str
    signals: list[str]
    risk: str = "balanced"          # implied risk for the preset gallery
    needs_ai: bool = False


ARCHETYPES: list[Archetype] = [
    Archetype("conservative", "Conservative",
              "RSI dip buys gated by a trend filter. Tight risk, picky entries.",
              ["oversold"], risk="conservative"),
    Archetype("balanced", "Balanced",
              "RSI dip + VWAP discount. A steady all-rounder.",
              ["oversold", "vwap"], risk="balanced"),
    Archetype("aggressive", "Aggressive",
              "RSI + VWAP + relative strength. Looser threshold, wider targets.",
              ["oversold", "vwap", "relative_strength"], risk="aggressive"),
    Archetype("ai_kronos", "AI-Kronos",
              "Balanced plus the Kronos AI forecast signal.",
              ["oversold", "vwap", "kronos_forecast"], risk="balanced", needs_ai=True),
    Archetype("ict_fvg", "ICT-FVG",
              "ICT fair-value-gap discount entries: buy the retrace into a "
              "bullish FVG, confirmed by an RSI dip and a VWAP discount, in a "
              "non-bearish regime.",
              ["fvg", "oversold", "vwap"], risk="balanced"),
]


def _profile_for(arch: Archetype, symbol: str, risk: str, style: str) -> dict:
    r = RISK[risk]
    s = STYLE[style]
    signals: dict = {}
    if "fvg" in arch.signals:
        signals["fvg"] = {"weight": 0.5, "lookback": 50, "min_gap_pct": 0.0005}
    if "oversold" in arch.signals:
        signals["oversold"] = {"weight": 0.5, "oversold_level": 45, "period": 14}
    if "vwap" in arch.signals:
        signals["vwap"] = {"weight": 0.3, "window": s["vwap_window"], "max_dist": 0.03}
    if "relative_strength" in arch.signals:
        signals["relative_strength"] = {"weight": 0.2, "band": 0.02, "lookback": s["rs_lookback"]}
    if "kronos_forecast" in arch.signals:
        signals["kronos_forecast"] = {"weight": 0.25, "pred_len": 4, "threshold_pct": 0.02}
    return {
        "symbol": symbol, "benchmark_symbol": "BTC/USD", "timeframe": s["timeframe"],
        "entry_threshold": r["entry_threshold"], "regime_ma_period": s["regime_ma_period"],
        "atr_period": 14, "stop_atr_mult": r["stop_atr_mult"],
        "take_profit_atr_mult": r["take_profit_atr_mult"], "max_hold_bars": s["max_hold_bars"],
        "risk_per_trade": r["risk_per_trade"], "max_position_frac": 0.25,
        "daily_loss_limit_pct": r["daily_loss_limit_pct"],
        "max_consecutive_losses": r["max_consecutive_losses"],
        "cooldown_minutes": s["cooldown_minutes"], "signals": signals,
    }


def archetype_profile(arch: Archetype, symbol: str = "BTC/USD", style: str = "swing") -> dict:
    """A concrete profile for an archetype (for the preset gallery)."""
    return _profile_for(arch, symbol, arch.risk, style)


def build_candidates(symbol: str, risk: str, style: str, ai: bool = False,
                     max_candidates: int = 6, max_ai: int = 3) -> list[dict]:
    """Bounded set of {label, profile} candidates for the backtest search."""
    if risk not in RISK:
        raise ValueError(f"unknown risk {risk!r}; choose from {sorted(RISK)}")
    if style not in STYLE:
        raise ValueError(f"unknown style {style!r}; choose from {sorted(STYLE)}")

    out: list[dict] = []
    if ai:
        arch = next(a for a in ARCHETYPES if a.needs_ai)
        base = _profile_for(arch, symbol, risk, style)
        out.append({"label": "AI-Kronos", "profile": base})
        stricter = dict(base)
        stricter["entry_threshold"] = round(base["entry_threshold"] + 0.1, 3)
        out.append({"label": "AI-Kronos (stricter)", "profile": stricter})
        longer = dict(base)
        sig = dict(base["signals"])
        kf = dict(sig["kronos_forecast"]); kf["pred_len"] = 8
        sig["kronos_forecast"] = kf; longer["signals"] = sig
        out.append({"label": "AI-Kronos (longer horizon)", "profile": longer})
        return out[:max_ai]

    for arch in ARCHETYPES:
        if arch.needs_ai:
            continue
        out.append({"label": arch.name, "profile": _profile_for(arch, symbol, risk, style)})
    bal = next(a for a in ARCHETYPES if a.key == "balanced")
    strict = dict(_profile_for(bal, symbol, risk, style))
    strict["entry_threshold"] = round(strict["entry_threshold"] + 0.1, 3)
    out.append({"label": "Balanced (stricter)", "profile": strict})
    return out[:max_candidates]
