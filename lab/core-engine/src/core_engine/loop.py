from __future__ import annotations
import time
from datetime import datetime, timezone
from swingbot.exits import exit_decision
from core_engine.config import LOOP_SECONDS, SYMBOL
from core_engine.contracts import Action, JournalEvent
from core_engine.brain import decide
from core_engine.risk_gate import build_order_intent
from core_engine.executor import Executor
from core_engine.market import build_context, refresh_candles, latest_price, latest_atr


class Engine:
    def __init__(self, *, store, fetcher, broker, journal, risk, runtime_state,
                 profile, kronos):
        self._store = store
        self._fetcher = fetcher
        self._broker = broker
        self._journal = journal
        self._risk = risk
        self._rt = runtime_state
        self._profile = profile
        self._kronos = kronos
        self._exec = Executor(broker)
        self.position = None

    def _log(self, kind, reason, **payload):
        self._journal.log(JournalEvent(ts=datetime.now(timezone.utc), kind=kind,
                                       symbol=SYMBOL, reason=reason, payload=payload))

    def tick(self, now: datetime) -> None:
        try:
            refresh_candles(self._store, self._fetcher)
            self.position = self._exec.reconcile(
                self.position, profile=self._profile, atr=latest_atr(self._store), now=now
            )

            if self.position is not None:
                price = latest_price(self._store)
                ex = exit_decision(self.position.stop, self.position.tp,
                                   self.position.max_hold_until, price, price, price, now)
                if ex is not None:
                    reason, ref = ex
                    pnl = self._exec.exit(self.position, ref, str(reason))
                    if pnl is None:
                        self._log("exit", "exit order unfilled", reason=str(reason))
                    else:
                        self._log("pnl", f"closed: {reason}", realized=pnl, won=pnl > 0)
                        self.position = None
                return

            ctx = build_context(self._store)
            d = decide(ctx, has_position=False, profile=self._profile, kronos=self._kronos)
            self._log("decision", d.reason, action=d.action.value,
                      confidence=d.confidence)
            if d.action is not Action.ENTER_LONG:
                return

            price = latest_price(self._store)
            equity = self._broker.equity(price)
            self._risk.start_day(now, equity)
            intent = build_order_intent(d, symbol=SYMBOL, now=now, equity=equity,
                                        entry_price=price, atr=latest_atr(self._store),
                                        risk=self._risk, profile=self._profile)
            if intent is None:
                self._log("decision", "risk gate vetoed entry")
                return
            pos = self._exec.enter(intent, now)
            if pos is None:
                self._log("order", "entry pending / unfilled", qty=intent.qty)
            else:
                self.position = pos
                self._log("order", "entry filled", open=True, qty=pos.qty,
                          entry=pos.entry_price)
        except Exception as exc:
            self._log("error", f"tick failed: {type(exc).__name__}: {exc}")

    def run_forever(self) -> None:
        while True:
            if self._rt.get_running_desired():
                self.tick(datetime.now(timezone.utc))
            time.sleep(LOOP_SECONDS)
