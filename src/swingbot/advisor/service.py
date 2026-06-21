from __future__ import annotations

from datetime import datetime, timezone

from swingbot.advisor.schema import validate_proposal


class AdvisorService:
    def __init__(
        self,
        *,
        client,
        journal,
        profiles,
        get_digest,
        get_dial,
        broker=None,
    ):
        self.client = client
        self.journal = journal
        self.profiles = profiles
        self.get_digest = get_digest
        self.get_dial = get_dial
        self.broker = broker

    def run_review(self) -> dict:
        raw = self.client.review(self.get_digest())
        applied, dropped = validate_proposal(raw, self.get_dial())
        entries: list[dict] = []
        saved: dict[str, dict] = {}
        ts = datetime.now(timezone.utc).isoformat()

        for symbol, changes in applied.items():
            name = self._profile_name_for_symbol(symbol)
            if name is None:
                dropped.append(f"{symbol}: no matching profile")
                continue
            profile = self.profiles.get(name)
            if profile is None:
                dropped.append(f"{symbol}: no matching profile")
                continue

            changed: dict = {}
            rationale = str(changes.get("rationale", ""))
            for key, value in changes.items():
                if key in ("rationale", "enable", "disable"):
                    continue
                before = profile.get(key)
                if before == value:
                    continue
                profile[key] = value
                changed[key] = value
                entries.append(
                    {
                        "symbol": symbol,
                        "param": key,
                        "before": before,
                        "after": value,
                        "rationale": rationale,
                        "ts": ts,
                    }
                )

            if changed:
                self.profiles.save(name, profile)
                saved[symbol] = {**changed}

        batch_id = self.journal.record(entries) if entries else ""
        return {"applied": saved, "dropped": dropped, "batch_id": batch_id}

    def _profile_name_for_symbol(self, symbol: str) -> str | None:
        for name in self.profiles.list():
            profile = self.profiles.get(name) or {}
            if profile.get("symbol") == symbol:
                return name
        return None
