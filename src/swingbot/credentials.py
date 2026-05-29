from __future__ import annotations

import json
import os

from swingbot.config import AlpacaCredentials


class CredentialStore:
    """Alpaca credentials in a chmod-600 local JSON file. Secret is never exposed
    via status(); only get() (server-internal) returns it."""

    def __init__(self, path: str):
        self.path = path

    def set(self, key_id: str, secret_key: str, base_url: str) -> None:
        payload = {"key_id": key_id, "secret_key": secret_key, "base_url": base_url}
        with open(self.path, "w") as f:
            json.dump(payload, f)
        os.chmod(self.path, 0o600)

    def _load(self) -> dict | None:
        if not os.path.exists(self.path):
            return None
        with open(self.path) as f:
            return json.load(f)

    def status(self) -> dict:
        d = self._load()
        if not d:
            return {"key_id": None, "has_secret": False, "paper": True}
        return {
            "key_id": d.get("key_id"),
            "has_secret": bool(d.get("secret_key")),
            "paper": "paper" in d.get("base_url", "paper"),
        }

    def get(self) -> AlpacaCredentials | None:
        d = self._load()
        if not d or not d.get("key_id") or not d.get("secret_key"):
            return None
        base_url = d.get("base_url", "https://paper-api.alpaca.markets")
        return AlpacaCredentials(key_id=d["key_id"], secret_key=d["secret_key"],
                                 base_url=base_url, paper="paper" in base_url)
