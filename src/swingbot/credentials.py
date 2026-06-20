from __future__ import annotations

import json
import os

from swingbot.broker.adapter import BROKER_REGISTRY, get_adapter
from swingbot.config import AlpacaCredentials

_DEFAULT_BROKER = "alpaca"


class CredentialStore:
    """Versioned multi-broker credential file (chmod 600). Exactly one broker is
    active. Legacy flat {key_id,secret_key,base_url} files migrate transparently
    to v2 on load. Secrets are never exposed via status()/broker_status()."""

    def __init__(self, path: str):
        self.path = path

    # ---- file IO + migration ----
    def _raw(self) -> dict | None:
        if not os.path.exists(self.path):
            return None
        with open(self.path) as f:
            return json.load(f)

    def _load(self) -> dict:
        """Always returns a normalized v2 doc (migrating legacy in memory)."""
        raw = self._raw()
        if not raw:
            return {"version": 2, "active": _DEFAULT_BROKER, "brokers": {}}
        if raw.get("version") == 2 and "brokers" in raw:
            raw.setdefault("active", _DEFAULT_BROKER)
            return raw
        # legacy v1: flat alpaca creds
        broker = {k: raw.get(k) for k in ("key_id", "secret_key", "base_url")
                  if raw.get(k) is not None}
        return {"version": 2, "active": _DEFAULT_BROKER,
                "brokers": {_DEFAULT_BROKER: broker} if broker else {}}

    def _save(self, doc: dict) -> None:
        with open(self.path, "w") as f:
            json.dump(doc, f)
        os.chmod(self.path, 0o600)

    def active(self) -> str:
        return self._load().get("active", _DEFAULT_BROKER)

    # ---- legacy API (operates on the active broker; signatures unchanged) ----
    def set(self, key_id: str, secret_key: str, base_url: str) -> None:
        doc = self._load()
        doc["active"] = _DEFAULT_BROKER
        doc["brokers"][_DEFAULT_BROKER] = {
            "key_id": key_id, "secret_key": secret_key, "base_url": base_url}
        self._save(doc)

    def status(self) -> dict:
        d = self._load()["brokers"].get(self.active())
        if not d:
            return {"key_id": None, "has_secret": False, "paper": True}
        return {
            "key_id": d.get("key_id"),
            "has_secret": bool(d.get("secret_key")),
            "paper": "paper" in d.get("base_url", "paper"),
        }

    def get(self) -> AlpacaCredentials | None:
        d = self._load()["brokers"].get(self.active())
        if not d or not d.get("key_id") or not d.get("secret_key"):
            return None
        base_url = d.get("base_url", "https://paper-api.alpaca.markets")
        return AlpacaCredentials(key_id=d["key_id"], secret_key=d["secret_key"],
                                 base_url=base_url, paper="paper" in base_url)

    # ---- multi-broker management ----
    def set_active(self, broker_id: str) -> None:
        get_adapter(broker_id)                 # raises ValueError if unknown
        doc = self._load()
        doc["active"] = broker_id
        self._save(doc)

    def set_broker(self, broker_id: str, values: dict) -> None:
        adapter = get_adapter(broker_id)
        adapter.validate(values)
        doc = self._load()
        stored = {f.name: values.get(f.name) for f in adapter.fields}
        if "base_url" in values:
            stored["base_url"] = values["base_url"]
        doc["brokers"][broker_id] = stored
        self._save(doc)

    def broker_status(self, broker_id: str) -> dict:
        adapter = get_adapter(broker_id)
        stored = self._load()["brokers"].get(broker_id, {})
        fields = {}
        for f in adapter.fields:
            present = bool(stored.get(f.name))
            fields[f.name] = {"set": present,
                              "value": (stored.get(f.name) if (present and not f.secret)
                                        else None)}
        configured = all(fields[f.name]["set"] for f in adapter.fields)
        return {"broker": broker_id, "configured": configured, "fields": fields}

    def list_brokers(self) -> dict:
        brokers = []
        for bid, adapter in BROKER_REGISTRY.items():
            st = self.broker_status(bid)
            brokers.append({
                "id": bid, "label": adapter.label, "modes": list(adapter.modes),
                "configured": st["configured"],
                "fields": [{"name": f.name, "label": f.label,
                            "secret": f.secret, "help": f.help} for f in adapter.fields],
                "status": st})
        return {"active": self.active(), "brokers": brokers}
