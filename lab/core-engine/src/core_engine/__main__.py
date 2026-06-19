from __future__ import annotations
import argparse
import pandas as pd
from swingbot.config import load_alpaca_credentials, load_dotenv
from swingbot.data.store import CandleStore
from swingbot.runtime_state import RuntimeStateStore
from swingbot.risk import RiskManager, RiskState
from core_engine.config import CANDLE_DB, STATE_DB, JOURNAL_DB, PROFILE, SYMBOL, TIMEFRAME
from core_engine.journal import EngineJournal
from core_engine.position_store import PositionStore


def _kronos_or_none():
    """Build the real Kronos signal, or fall back to None when its heavy stack
    (torch + the Kronos repo) is unavailable. The brain treats kronos=None as a
    neutral 0.0 contribution, so the engine stays runnable in the slim image and
    on hosts without Kronos installed."""
    try:
        from swingbot.signals.kronos_forecast import KronosForecastSignal
        return KronosForecastSignal(weight=1.0)
    except Exception as exc:  # ImportError or adapter/model load failure
        print(f"[core_engine] Kronos unavailable ({type(exc).__name__}: {exc}); "
              f"continuing with kronos=None.")
        return None


def _build_engine():
    from swingbot.broker.alpaca import AlpacaBroker
    from swingbot.data.alpaca import AlpacaData
    from core_engine.loop import Engine

    load_dotenv()
    creds = load_alpaca_credentials()
    store = CandleStore(CANDLE_DB)
    journal = EngineJournal(JOURNAL_DB)
    return Engine(store=store,
                  fetcher=AlpacaData(creds.key_id, creds.secret_key),
                  broker=AlpacaBroker(creds.key_id, creds.secret_key, paper=creds.paper),
                  journal=journal, risk=RiskManager(PROFILE, RiskState()),
                  runtime_state=RuntimeStateStore(STATE_DB), profile=PROFILE,
                  kronos=_kronos_or_none(),
                  position_store=PositionStore(STATE_DB))


def _cmd_report():
    r = EngineJournal(JOURNAL_DB).report()
    print(f"Open position: {r.open_position}")
    print(f"Realized P&L:  {r.realized_pnl:.2f}   Unrealized: {r.unrealized_pnl:.2f}")
    print(f"Wins/Losses:   {r.wins}/{r.losses}")
    for t in r.closed[:20]:
        print(f"  {t.get('reason')}: {t.get('realized', 0):.2f}")


def main():
    p = argparse.ArgumentParser(prog="core_engine")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    sub.add_parser("report")
    bt = sub.add_parser("backtest")
    bt.add_argument("--limit", type=int, default=2000)
    args = p.parse_args()

    if args.cmd == "run":
        eng = _build_engine()
        RuntimeStateStore(STATE_DB).set_running_desired(True)
        eng.run_forever()
    elif args.cmd == "report":
        _cmd_report()
    elif args.cmd == "backtest":
        from core_engine.backtest import run_backtest

        rows = CandleStore(CANDLE_DB).get(SYMBOL, TIMEFRAME, limit=args.limit)
        res = run_backtest(pd.DataFrame(rows), profile=PROFILE,
                           kronos=_kronos_or_none())
        print(f"Backtest: trades={len(res.trades)} wins={res.wins} "
              f"losses={res.losses} final_equity={res.final_equity:.2f}")


if __name__ == "__main__":
    main()
