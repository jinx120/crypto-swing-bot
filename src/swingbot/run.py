from __future__ import annotations

import argparse
import json

from swingbot.broker.alpaca import AlpacaBroker
from swingbot.config import load_alpaca_credentials, load_dotenv
from swingbot.data.alpaca import AlpacaData
from swingbot.journal import TradeJournal
from swingbot.orchestrator import Orchestrator
from swingbot.profile import StrategyProfile
from swingbot.risk import RiskManager
from swingbot.state import StateStore


def build_orchestrator(profile_path: str, db_path: str = "swingbot.db") -> Orchestrator:
    load_dotenv()
    creds = load_alpaca_credentials()
    with open(profile_path) as f:
        profile = StrategyProfile.from_dict(json.load(f))
    data = AlpacaData(creds.key_id, creds.secret_key)
    broker = AlpacaBroker(creds.key_id, creds.secret_key, paper=creds.paper)
    state = StateStore(db_path)
    risk = RiskManager(profile, state.load_risk_state())
    return Orchestrator(profile=profile, data=data, broker=broker, state=state,
                        risk=risk, journal=TradeJournal())


def main() -> None:
    ap = argparse.ArgumentParser(description="swingbot live/paper runner")
    ap.add_argument("--profile", required=True, help="strategy profile JSON path")
    ap.add_argument("--db", default="swingbot.db", help="SQLite state DB path")
    args = ap.parse_args()
    orch = build_orchestrator(args.profile, db_path=args.db)
    creds = load_alpaca_credentials()
    mode = "PAPER" if creds.paper else "LIVE"
    print(f"[swingbot] starting in {mode} mode for {orch.profile.symbol}")
    orch.run()


if __name__ == "__main__":
    main()
