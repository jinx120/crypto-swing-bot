from __future__ import annotations

import os
from dataclasses import dataclass


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader: sets KEY=VALUE lines into os.environ.
    Does NOT override variables already present in the environment.
    Ignores blanks and #-comments. Strips surrounding single/double quotes.
    """
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


@dataclass(frozen=True)
class AlpacaCredentials:
    key_id: str
    secret_key: str
    base_url: str
    paper: bool


def load_alpaca_credentials() -> AlpacaCredentials:
    key_id = os.environ.get("ALPACA_API_KEY_ID")
    secret_key = os.environ.get("ALPACA_API_SECRET_KEY")
    base_url = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    if not key_id:
        raise ValueError("ALPACA_API_KEY_ID is not set (check your .env)")
    if not secret_key:
        raise ValueError("ALPACA_API_SECRET_KEY is not set (check your .env)")
    paper = "paper" in base_url
    return AlpacaCredentials(key_id=key_id, secret_key=secret_key,
                             base_url=base_url, paper=paper)
