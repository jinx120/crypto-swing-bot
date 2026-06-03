from __future__ import annotations

import os
import secrets

import uvicorn

from swingbot.credentials import CredentialStore
from swingbot.data.backfill import ArchiveConfig, Backfiller
from swingbot.data.ccxt_provider import CcxtProvider
from swingbot.data.market import MarketData
from swingbot.data.poller import CandlePoller
from swingbot.data.store import CandleStore
from swingbot.discovery import DiscoveryEngine
from swingbot.profiles import ProfileStore
from swingbot.supervisor import PortfolioSupervisor
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
    store = CandleStore(os.path.join(DATA_DIR, "candles.db"))
    archive_cfg = ArchiveConfig()
    archive_provider = CcxtProvider(exchange_id=archive_cfg.exchange,
                                    quote_map=archive_cfg.quote_map,
                                    symbol_overrides=archive_cfg.symbol_overrides)
    backfiller = Backfiller(store, provider=archive_provider)
    market = MarketData(store, creds)
    supervisor = PortfolioSupervisor(
        profiles=profiles, creds=creds,
        state_db=os.path.join(DATA_DIR, "swingbot.db"), market=market)
    poller = CandlePoller(market, profiles)        # keeps all armed symbols warm for charts
    poller.start()
    discovery = DiscoveryEngine(market)
    app = create_app(controller=supervisor, profiles=profiles, creds=creds,
                     token=token, store=store, market=market, backfiller=backfiller,
                     discovery=discovery,
                     discovery_cache_path=os.path.join(DATA_DIR, "discovery.json"))
    app.state.archive_config = archive_cfg
    print(f"[swingbot-web] token: {token}")
    print(f"[swingbot-web] http://{HOST}:8000")
    uvicorn.run(app, host=HOST, port=8000)


if __name__ == "__main__":
    main()
