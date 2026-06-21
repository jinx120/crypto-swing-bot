from __future__ import annotations


def build_digest(strategies: dict[str, dict]) -> dict:
    out: dict[str, dict] = {}
    for symbol, stats in strategies.items():
        trades = int(stats.get("trades", 0))
        wins = int(stats.get("wins", 0))
        out[symbol] = {
            "trades": trades,
            "win_rate": (wins / trades) if trades else 0.0,
            "avg_win": float(stats.get("avg_win", 0.0)),
            "avg_loss": float(stats.get("avg_loss", 0.0)),
            "drawdown": float(stats.get("drawdown", 0.0)),
            "params": dict(stats.get("params", {})),
            "weight": float(stats.get("weight", 0.0)),
            "equity_curve": list(stats.get("equity_curve", []))[-50:],
        }
    return out
