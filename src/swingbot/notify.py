from __future__ import annotations

import json
import urllib.request


def _urllib_post(url: str, payload: dict, timeout: float) -> None:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=timeout).close()


class DiscordNotifier:
    """Posts compact messages to a Discord webhook. Failure-tolerant: a missing
    webhook or a transport error never raises (returns False)."""

    def __init__(self, webhook_getter, transport=None, timeout_s: float = 5.0):
        self._webhook_getter = webhook_getter
        self._transport = transport or _urllib_post
        self.timeout_s = timeout_s

    def send(self, event_type: str, payload: dict) -> bool:
        url = self._webhook_getter()
        if not url:
            return False
        content = f"**[swingbot:{event_type}]** " + json.dumps(payload, default=str)[:1800]
        try:
            self._transport(url, {"content": content}, self.timeout_s)
            return True
        except Exception:                            # webhook must never touch trading
            return False
