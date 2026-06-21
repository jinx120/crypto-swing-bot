from __future__ import annotations

from swingbot.advisor.bands import BANDS, _TUNABLE


def validate_proposal(raw: dict, dial: str) -> tuple[dict, list[str]]:
    band = BANDS.get(dial, BANDS["balanced"])
    applied: dict[str, dict] = {}
    dropped: list[str] = []

    for symbol, changes in (raw or {}).items():
        if not isinstance(changes, dict):
            dropped.append(f"{symbol}: not an object")
            continue

        kept: dict = {}
        for key, value in changes.items():
            if key == "rationale":
                kept[key] = str(value)
                continue
            if key in ("enable", "disable") and isinstance(value, bool):
                kept[key] = value
                continue
            if key not in _TUNABLE:
                dropped.append(f"{symbol}.{key}: unknown param")
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                dropped.append(f"{symbol}.{key}: not numeric")
                continue

            lo, hi = band[key]
            clamped = max(lo, min(hi, numeric))
            if clamped != numeric:
                dropped.append(f"{symbol}.{key}: clamped {numeric}->{clamped}")
            kept[key] = clamped

        if any(key in _TUNABLE or key in ("enable", "disable") for key in kept):
            applied[symbol] = kept

    return applied, dropped
