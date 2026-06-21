from __future__ import annotations

import json
from urllib import request


class AdvisorClient:
    def __init__(self, model: str, url: str | None = None):
        self.model = model
        self.url = (url or "http://localhost:11434").rstrip("/")

    def review(self, digest: dict) -> dict:
        prompt = self._prompt(digest)
        try:
            reply = self._raw_reply(prompt)
            block = self._first_json_object(reply)
            parsed = json.loads(block)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _raw_reply(self, prompt: str) -> str:
        payload = json.dumps(
            {"model": self.model, "prompt": prompt, "stream": False}
        ).encode("utf-8")
        req = request.Request(
            f"{self.url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        return str(data.get("response", ""))

    @staticmethod
    def _prompt(digest: dict) -> str:
        return (
            "Review this trading performance digest and return only a JSON object "
            "of bounded configuration changes by symbol. Do not suggest trades.\n"
            f"{json.dumps(digest, sort_keys=True)}"
        )

    @staticmethod
    def _first_json_object(text: str) -> str:
        start = text.find("{")
        if start < 0:
            raise ValueError("no JSON object found")
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start:index + 1]
        raise ValueError("unterminated JSON object")
