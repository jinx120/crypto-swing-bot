from __future__ import annotations

import threading
import time
import traceback
from datetime import datetime, timezone

import pandas as pd

from swingbot.broker.alpaca import AlpacaBroker
from swingbot.data.market import MarketData, timeframe_seconds
from swingbot.journal import TradeJournal
from swingbot.orchestrator import Orchestrator
from swingbot.portfolio_risk import PortfolioRiskManager, PortfolioSettings
from swingbot.profile import StrategyProfile
from swingbot.profiles import ProfileStore
from swingbot.risk import RiskManager
from swingbot.snapshot import signal_snapshot
from swingbot.state import StateStore, StrategyStateView
from swingbot.types import MarketContext

_CANON = ["ts", "open", "high", "low", "close", "volume"]


def _bars_to_df(bars: list[dict]) -> pd.DataFrame:
    """Convert cache bars ({time epoch, o,h,l,c,v}) to the engine's candle DataFrame."""
    if not bars:
        return pd.DataFrame(columns=_CANON)
    df = pd.DataFrame(bars).rename(columns={"time": "ts"})
    df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df[_CANON].sort_values("ts").reset_index(drop=True)


class CachedProvider:
    """MarketDataProvider over the candle cache; never calls Alpaca directly.
    Latest prices come from a dict the supervisor refreshes each cycle."""

    def __init__(self, market, latest_prices: dict, timeframes: dict):
        self.market = market
        self.latest = latest_prices          # symbol -> float
        self.timeframes = timeframes          # symbol -> timeframe (price fallback)

    def get_candles(self, symbol: str, timeframe: str, lookback: int) -> pd.DataFrame:
        bars = self.market.get(symbol, timeframe, lookback,
                               max_age=timeframe_seconds(timeframe))
        return _bars_to_df(bars)

    def get_latest_price(self, symbol: str) -> float:
        p = self.latest.get(symbol)
        if p is not None:
            return p
        tf = self.timeframes.get(symbol, "15m")
        bars = self.market.get(symbol, tf, 1, max_age=timeframe_seconds(tf))
        if bars:
            return float(bars[-1]["close"])
        raise RuntimeError(f"no price available for {symbol}")


class PortfolioSupervisor:
    """Runs one Orchestrator per armed strategy in a single loop under a shared
    PortfolioRiskManager. The only component that talks to the broker/data upstream.

    Single-writer invariant: tick_all/build/status/pause/resume must all be called
    from ONE thread. The shared StateStore (check_same_thread=False, no internal
    lock) and the in-memory PortfolioRiskManager are not synchronized; the start()
    loop is the sole writer. Phase 2 must serialize any web/request-thread calls
    onto this thread (or add locking) before invoking these methods concurrently.
    """

    def __init__(self, profiles: ProfileStore, creds, state_db: str,
                 market: MarketData | None = None, broker=None, mode: str = "paper"):
        self.profiles = profiles
        self.creds = creds
        self.state_db = state_db
        self.market = market
        self.mode = mode
        self._broker = broker
        self.paused = False
        self._running = False
        self._thread: threading.Thread | None = None
        self._latest_prices: dict = {}
        self._timeframes: dict = {}
        self._strategies: dict = {}          # name -> {profile, orch, view, journal, snapshot}
        self._portfolio_risk: PortfolioRiskManager | None = None
        self._store: StateStore | None = None
        self._summary: dict = {}

    # ---- construction ----
    def build(self) -> None:
        if self.market is None:
            raise RuntimeError("market must be provided (webmain wires MarketData)")
        if self._broker is None:
            c = self.creds.get() if self.creds else None
            if c is None:
                raise RuntimeError("Alpaca credentials not set")
            self._broker = AlpacaBroker(c.key_id, c.secret_key, paper=(self.mode == "paper"))

        self._store = StateStore(self.state_db)
        settings = PortfolioSettings(**self.profiles.get_portfolio_settings())
        self._portfolio_risk = PortfolioRiskManager(
            settings, self._store.load_portfolio_risk_state())

        provider = CachedProvider(self.market, self._latest_prices, self._timeframes)
        self._timeframes.clear()
        self._latest_prices.clear()
        self._strategies = {}
        for name in self.profiles.list_armed():
            pdict = self.profiles.get(name)
            if pdict is None:
                continue
            profile = StrategyProfile.from_dict(pdict)
            self._timeframes[profile.symbol] = profile.timeframe
            view = StrategyStateView(self._store, name)
            risk = RiskManager(profile, view.load_risk_state())
            orch = Orchestrator(
                profile=profile, data=provider, broker=self._broker, state=view,
                risk=risk, journal=TradeJournal(),
                portfolio_gate=self._make_gate(profile),
                portfolio_on_close=self._make_on_close())
            self._strategies[name] = {"profile": profile, "orch": orch,
                                      "view": view, "snapshot": {}}

    def _make_gate(self, profile: StrategyProfile):
        def gate(symbol: str, prospective_value: float):
            positions = self._store.load_all_positions()
            deployed = 0.0
            for pos in positions.values():
                price = self._latest_prices.get(pos.symbol, pos.entry_price)
                deployed += pos.qty * price
            equity = self._broker.get_account()["equity"]
            return self._portfolio_risk.check_can_enter(
                equity=equity, open_position_count=len(positions),
                deployed_value=deployed, prospective_value=prospective_value)
        return gate

    def _make_on_close(self):
        def on_close(pnl: float, now: datetime):
            self._portfolio_risk.on_trade_closed(pnl, now)
            self._store.save_portfolio_risk_state(self._portfolio_risk.state)
        return on_close

    # ---- the loop ----
    def tick_all(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        self._warm(now)
        acct = self._broker.get_account()
        self._portfolio_risk.start_day(now, acct["equity"])
        for name in sorted(self._strategies):                 # deterministic priority
            s = self._strategies[name]
            if self.paused:
                s["orch"].paused = True
            try:
                s["orch"].tick(now)
            except Exception as e:                            # one bad strategy never aborts the cycle
                print(f"[supervisor] {name} tick error: {e}")
            s["snapshot"] = self._snapshot(s["profile"])
        self._store.save_portfolio_risk_state(self._portfolio_risk.state)
        self._summary = self._build_summary(acct)

    def _warm(self, now: datetime) -> None:
        by_tf: dict = {}
        for s in self._strategies.values():
            by_tf.setdefault(s["profile"].timeframe, set()).add(s["profile"].symbol)
        for tf, syms in by_tf.items():
            try:
                self.market.refresh_many(sorted(syms), tf)
            except Exception as e:
                print(f"[supervisor] warm {tf} error: {e}")
        prov = self.market._provider()
        all_syms = sorted({s["profile"].symbol for s in self._strategies.values()})
        if prov is not None and all_syms and hasattr(prov, "get_latest_prices"):
            try:
                self._latest_prices.update(prov.get_latest_prices(all_syms))
            except Exception as e:
                print(f"[supervisor] latest-price error: {e}")

    def _snapshot(self, profile: StrategyProfile) -> dict:
        try:
            cdf = _bars_to_df(self.market.get(
                profile.symbol, profile.timeframe, profile.regime_ma_period + 5,
                max_age=timeframe_seconds(profile.timeframe)))
            bench = None
            if "relative_strength" in profile.signals:
                bench = _bars_to_df(self.market.get(
                    profile.benchmark_symbol, profile.timeframe, profile.regime_ma_period + 5,
                    max_age=timeframe_seconds(profile.timeframe)))
            return signal_snapshot(profile, MarketContext(candles=cdf, benchmark=bench))
        except Exception as e:
            return {"error": str(e)}

    def _build_summary(self, acct: dict) -> dict:
        positions = self._store.load_all_positions()
        deployed = 0.0
        for pos in positions.values():
            price = self._latest_prices.get(pos.symbol, pos.entry_price)
            deployed += pos.qty * price
        prs = self._portfolio_risk.state
        equity = acct["equity"]
        return {
            "mode": self.mode, "running": self._running, "paused": self.paused,
            "equity": equity, "deployed": deployed,
            "deployed_frac": (deployed / equity) if equity else 0.0,
            "open_positions": len(positions), "day_pnl": prs.realized_pnl_today,
            "kill_switch": {"active": prs.kill_switch_active, "reason": prs.kill_switch_reason},
        }

    # ---- status + control surface (consumed by Phase 2 web layer) ----
    def status(self) -> dict:
        strategies = []
        for name in sorted(self._strategies):
            s = self._strategies[name]
            pos = s["view"].load_position()
            rs = s["orch"].risk.state
            strategies.append({
                "name": name, "symbol": s["profile"].symbol,
                "running": self._running,
                "live_eligible": self.profiles.is_live_eligible(name),
                "snapshot": s["snapshot"],
                "position": _pos_dict(pos),
                "risk": {"kill_switch": {"active": rs.kill_switch_active,
                                         "reason": rs.kill_switch_reason},
                         "consecutive_losses": rs.consecutive_losses},
            })
        return {"portfolio": self._summary or {"mode": self.mode, "running": self._running},
                "strategies": strategies}

    # ---- lifecycle ----
    def start(self) -> None:
        if self._running:
            return
        self.build()
        for s in self._strategies.values():
            s["orch"].reconcile(datetime.now(timezone.utc))
        self._running = True

        def loop():
            while self._running:
                try:
                    self.tick_all()
                except Exception as e:
                    print(f"[supervisor] cycle error: {e}")
                    traceback.print_exc()
                time.sleep(self._poll_seconds())

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False
        for s in self._strategies.values():
            s["orch"].paused = False

    def _poll_seconds(self) -> int:
        return min((s["profile"].poll_seconds for s in self._strategies.values()),
                   default=60)


def _pos_dict(pos):
    if pos is None:
        return None
    return {"symbol": pos.symbol, "entry_price": pos.entry_price, "qty": pos.qty,
            "stop": pos.stop, "tp": pos.tp,
            "max_hold_until": pos.max_hold_until.isoformat(),
            "entry_ts": pos.entry_ts.isoformat()}
