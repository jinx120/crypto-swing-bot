from __future__ import annotations

from datetime import timedelta

import pandas as pd

from swingbot.broker.simulated import SimulatedBroker
from swingbot.confluence import ConfluenceEngine, build_signals
from swingbot.exits import bracket_levels
from swingbot.indicators import atr
from swingbot.journal import Trade, TradeJournal
from swingbot.metrics import Metrics, compute_metrics
from swingbot.profile import StrategyProfile
from swingbot.regime import RegimeFilter
from swingbot.sizing import position_size
from swingbot.types import MarketContext


def precompute_forecasts(
    df: pd.DataFrame,
    adapter,
    warmup: int,
) -> dict:
    """Run Kronos inference for every bar from warmup to end of df.

    Returns a dict mapping last-candle ts → forecast DataFrame (or None).
    Bypasses the adapter's single-entry live cache by calling _run_with_timeout directly.
    """
    cache = {}
    for i in range(warmup, len(df) - 1):  # mirrors run_backtest entry loop range
        candles_slice = df.iloc[: i + 1]
        ts_key = candles_slice["ts"].iloc[-1]
        cache[ts_key] = adapter._run_with_timeout(candles_slice)
    return cache


def _maybe_precompute_kronos(
    signals: list,
    df: pd.DataFrame,
    warmup: int,
) -> None:
    """If any signal is a KronosForecastSignal, pre-populate its adapter's cache."""
    from swingbot.signals.kronos_forecast import KronosForecastSignal
    for signal in signals:
        if isinstance(signal, KronosForecastSignal):
            cache = precompute_forecasts(df, signal.adapter, warmup)
            signal.adapter.set_precomputed(cache)


def _warmup_bars(profile: StrategyProfile) -> int:
    needs = [profile.regime_ma_period, profile.atr_period]
    for params in profile.signals.values():
        for key in ("period", "window", "lookback"):
            if key in params:
                needs.append(params[key])
    return max(needs) + 2


def run_backtest(
    df: pd.DataFrame,
    profile: StrategyProfile,
    benchmark_df: pd.DataFrame | None = None,
    starting_equity: float = 1000.0,
) -> tuple[list[Trade], Metrics]:
    """Replay candles through the real strategy. Lookahead-safe:
    decide on the last CLOSED bar i, enter at bar i+1's open."""
    if len(df) < 2:
        raise ValueError("run_backtest needs at least 2 candles")
    broker = SimulatedBroker(starting_equity, profile.fee_rate, profile.slippage_rate)
    journal = TradeJournal()
    engine = ConfluenceEngine(build_signals(profile), profile)
    regime = RegimeFilter(profile)
    atr_series = atr(df, profile.atr_period)

    warmup = _warmup_bars(profile)
    bar_delta = df["ts"].iloc[1] - df["ts"].iloc[0]
    max_hold = bar_delta * profile.max_hold_bars

    _maybe_precompute_kronos(engine.signals, df, warmup)

    for i in range(warmup, len(df) - 1):
        current = df.iloc[i]

        # 1) manage an open position on this bar first
        trade = broker.update(current.to_dict())
        if trade is not None:
            journal.record(trade)

        # 2) if flat, evaluate entry on the closed bar, act on next bar's open
        if broker.position is None:
            ctx = MarketContext(
                candles=df.iloc[: i + 1],
                benchmark=benchmark_df.iloc[: i + 1] if benchmark_df is not None else None,
            )
            reg = regime.evaluate(ctx)
            if regime.permits_entry(reg.regime):
                conf = engine.evaluate(ctx)
                if conf.passed:
                    entry_bar = df.iloc[i + 1]
                    entry_price = float(entry_bar["open"])
                    a = float(atr_series.iloc[i])
                    if a > 0:
                        stop, tp = bracket_levels(
                            entry_price, a, profile.stop_atr_mult, profile.take_profit_atr_mult
                        )
                        qty = position_size(
                            broker.equity(float(current["close"])),
                            profile.risk_per_trade,
                            entry_price - stop,
                            entry_price,
                            profile.max_position_frac,
                        )
                        broker.open_long(
                            ts=entry_bar["ts"], price=entry_price, qty=qty,
                            stop=stop, tp=tp,
                            max_hold_until=entry_bar["ts"] + max_hold,
                            score_at_entry=conf.score, regime_at_entry=reg.regime,
                        )

    # close any still-open position at the last bar's close
    last = df.iloc[-1]
    final = broker.force_close(last["ts"], float(last["close"]))
    if final is not None:
        journal.record(final)

    return journal.trades, compute_metrics(journal.trades)
