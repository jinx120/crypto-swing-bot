from __future__ import annotations

import os
import secrets

import uvicorn

from swingbot.credentials import CredentialStore
from swingbot.data.market import MarketData
from swingbot.data.poller import CandlePoller
from swingbot.data.store import CandleStore
from swingbot.profiles import ProfileStore
from swingbot.service import BotService
from swingbot.web import create_app

HOST = os.environ.get("SWINGBOT_HOST", "127.0.0.1")
DATA_DIR = os.environ.get("SWINGBOT_DATA_DIR", os.path.expanduser("~/.swingbot"))


def _ensure_token(path: str) -> str:
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    tok = secrets.token_urlsafe(24)
    with open(path, "w") as f:
        f.write(tok)
    os.chmod(path, 0o600)
    return tok


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    token = _ensure_token(os.path.join(DATA_DIR, "token"))
    profiles = ProfileStore(os.path.join(DATA_DIR, "swingbot.db"))
    creds = CredentialStore(os.path.join(DATA_DIR, "credentials.json"))
    service = BotService(profiles=profiles, creds=creds,
                         state_db=os.path.join(DATA_DIR, "swingbot.db"))
    store = CandleStore(os.path.join(DATA_DIR, "candles.db"))
    market = MarketData(store, creds)
    poller = CandlePoller(market, profiles)
    poller.start()
    app = create_app(controller=service, profiles=profiles, creds=creds,
                     token=token, store=store, market=market)
    print(f"[swingbot-web] token: {token}")
    print(f"[swingbot-web] http://{HOST}:8000")
    uvicorn.run(app, host=HOST, port=8000)


if __name__ == "__main__":
    main()
