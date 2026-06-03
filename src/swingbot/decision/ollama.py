from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass


@dataclass
class OllamaResult:
    ok: bool
    data: dict | None = None
    error: str | None = None


def _urllib_transport(url: str, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


class OllamaClient:
    """Calls Ollama /api/generate with a JSON schema. Never raises: all failures
    (connection, timeout, non-JSON) return OllamaResult(ok=False)."""

    def __init__(self, url: str, model: str, timeout_s: float, transport=None):
        self.url = url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self._transport = transport or _urllib_transport

    def generate_json(self, prompt: str, schema: dict) -> OllamaResult:
        payload = {"model": self.model, "prompt": prompt, "stream": False,
                   "format": schema, "options": {"temperature": 0}}
        try:
            raw = self._transport(f"{self.url}/api/generate", payload, self.timeout_s)
        except Exception as e:                       # network / timeout / HTTP error
            return OllamaResult(ok=False, error=f"ollama transport: {e}")
        try:
            data = json.loads(raw["response"])
        except Exception as e:                       # missing key / invalid JSON body
            return OllamaResult(ok=False, error=f"ollama json: {e}")
        if not isinstance(data, dict):
            return OllamaResult(ok=False, error="ollama json: top-level not an object")
        return OllamaResult(ok=True, data=data)
