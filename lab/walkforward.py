"""Walk-forward validation for candidate trading signals.

Method: split history into rolling (train, test) window pairs. Inside each
window, pick the best parameter combination on the TRAIN slice only, then trade
that frozen combination through the TEST slice. Concatenating the test slices
gives a single out-of-sample record with no in-sample parameter fitting in it.

Every backtest runs through the validated `run_backtest_fast` (bit-for-bit equal
to production `run_backtest`), so the exits, sizing and broker are the real ones.
"""
from __future__ import annotations

import dataclasses
import statistics
from dataclasses import dataclass

import pandas as pd

from lab.research_data import split_extras
from lab.strategy_backtest import run_backtest_fast
from swingbot.backtest import _warmup_bars
from swingbot.profile import StrategyProfile


@dataclass(frozen=True)
class Window:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def generate_windows(first_ts, last_ts, train_days: int = 365,
                     test_days: int = 90, step_days: int = 90) -> list[Window]:
    """Rolling train/test splits covering [first_ts, last_ts].

    A window is emitted only if its full test period fits inside the data, so a
    truncated final window can never inflate or deflate the out-of-sample record.
    """
    if train_days <= 0 or test_days <= 0 or step_days <= 0:
        raise ValueError("train_days, test_days and step_days must all be > 0")
    first, last = pd.Timestamp(first_ts), pd.Timestamp(last_ts)
    train_len = pd.Timedelta(days=train_days)
    test_len = pd.Timedelta(days=test_days)
    step = pd.Timedelta(days=step_days)

    windows: list[Window] = []
    train_start = first
    while True:
        train_end = train_start + train_len
        test_end = train_end + test_len
        if test_end > last:
            return windows
        windows.append(Window(train_start, train_end, train_end, test_end))
        train_start = train_start + step


def apply_combo(profile: StrategyProfile, combo: dict) -> StrategyProfile:
    """Return a COPY of `profile` with a parameter combination applied.

    Dotted keys ("ema_trend.fast") set a param inside profile.signals; bare keys
    ("entry_threshold") set a top-level profile field. The input profile and its
    nested signal dicts are never mutated, so a combo loop stays independent.
    """
    signals = {name: dict(params) for name, params in profile.signals.items()}
    top: dict = {}
    for key, value in combo.items():
        if "." in key:
            signal_name, param = key.split(".", 1)
            if signal_name not in signals:
                raise KeyError(f"combo targets unknown signal {signal_name!r}")
            signals[signal_name][param] = value
        else:
            top[key] = value
    return dataclasses.replace(profile, signals=signals, **top)


def with_cost(profile: StrategyProfile, round_trip: float) -> StrategyProfile:
    """Set the total round-trip cost, charged symmetrically as fees."""
    return dataclasses.replace(profile, fee_rate=round_trip / 2.0, slippage_rate=0.0)


@dataclass(frozen=True)
class WindowResult:
    window: Window
    combo: dict
    train_pf: float
    trades: list
    net_pnl: float
    n_eligible_combos: int = 0


@dataclass(frozen=True)
class WalkForwardResult:
    label: str
    symbol: str
    windows: list[WindowResult]
    oos_trades: list

    @property
    def median_eligible_combos(self) -> float:
        """Median count of grid combos that cleared min_train_trades per window.

        A low value means selection was starved - the harness had almost nothing
        to choose between - which invalidates a verdict rather than supporting one.
        The filter culls the combos that trade LEAST, so under starvation the
        surviving set skews toward whichever parameters trade most frequently.
        """
        if not self.windows:
            return 0.0
        return float(statistics.median(w.n_eligible_combos for w in self.windows))


@dataclass(frozen=True)
class Verdict:
    label: str
    symbol: str
    decision: str          # "PROMOTE" | "REJECT"
    reason: str
    n_trades: int
    net_return_pct: float
    profit_factor: float
    positive_window_frac: float


def profit_factor(trades) -> float:
    gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss = -sum(t.pnl for t in trades if t.pnl < 0)
    if gross_loss > 0:
        return gross_profit / gross_loss
    return float("inf") if gross_profit > 0 else 0.0


def breakeven_cost(pf_by_cost: dict[float, float]) -> float | None:
    """Round-trip cost at which profit factor crosses 1.0, as a rate.

    Returns the largest swept cost `c` such that PF >= 1.0 at `c` AND at every
    swept tier below `c` - the FIRST downward crossing. Deliberately not "the
    highest tier with PF >= 1.0": on a noisy curve a single tier rebounding above
    1.0 further out would overstate the cost the signal actually survives.

    Returns None when PF is already below 1.0 at the cheapest swept tier, i.e.
    there is no gross edge to charge cost against.
    """
    survived = None
    for cost in sorted(pf_by_cost):
        if pf_by_cost[cost] < 1.0:
            break
        survived = cost
    return survived


def _slice(df: pd.DataFrame, start, end, warmup: int) -> pd.DataFrame:
    """Bars in [start, end] plus `warmup` bars of lead-in for the indicators.

    The lead-in is required (indicators need history) but must not produce
    tradeable bars, so callers filter the returned trades by entry_ts >= start.
    """
    positions = df.index[df["ts"] >= start]
    if len(positions) == 0:
        return df.iloc[0:0]
    first = max(0, int(positions[0]) - warmup)
    window = df.iloc[first:]
    return window[window["ts"] <= end].reset_index(drop=True)


def _run(df: pd.DataFrame, profile, benchmark_df, starting_equity):
    ohlc, extras = split_extras(df)
    trades, _ = run_backtest_fast(
        ohlc, profile, benchmark_df=benchmark_df,
        starting_equity=starting_equity, extras=extras or None)
    return trades


def walk_forward(df: pd.DataFrame, base_profile: StrategyProfile, grid: list[dict], *,
                 round_trip: float, train_days: int = 365, test_days: int = 90,
                 step_days: int = 90, min_train_trades: int = 20,
                 benchmark_df: pd.DataFrame | None = None,
                 starting_equity: float = 1000.0) -> WalkForwardResult:
    """Roll train/test windows, fitting `grid` on train and trading it on test.

    Selection metric on the training slice is profit factor at the SAME cost tier
    the verdict is graded at - selecting on gross performance and grading on net
    would pick parameters that only work at costs we do not pay.
    """
    costed = with_cost(base_profile, round_trip)
    # Warmup must cover the HUNGRIEST combo in the grid, not the base profile: a
    # combo that raises `lookback` needs more lead-in, and slicing to the base
    # profile's warmup would silently feed it a neutral score for hundreds of
    # bars into the test window.
    warmup = max(_warmup_bars(apply_combo(costed, c)) for c in grid) if grid \
        else _warmup_bars(costed)
    windows = generate_windows(df["ts"].iloc[0], df["ts"].iloc[-1],
                               train_days=train_days, test_days=test_days,
                               step_days=step_days)

    results: list[WindowResult] = []
    oos: list = []
    for window in windows:
        train_df = _slice(df, window.train_start, window.train_end, warmup)
        best_combo, best_pf = None, float("-inf")
        n_eligible = 0
        for combo in grid:
            trades = _run(train_df, apply_combo(costed, combo), benchmark_df, starting_equity)
            trades = [t for t in trades if t.entry_ts >= window.train_start]
            if len(trades) < min_train_trades:
                continue
            n_eligible += 1
            pf = profit_factor(trades)
            if pf > best_pf:
                best_combo, best_pf = combo, pf
        if best_combo is None:
            continue  # nothing traded enough on this training slice to choose from

        test_df = _slice(df, window.test_start, window.test_end, warmup)
        test_trades = _run(test_df, apply_combo(costed, best_combo),
                           benchmark_df, starting_equity)
        test_trades = [t for t in test_trades if t.entry_ts >= window.test_start]
        oos.extend(test_trades)
        results.append(WindowResult(
            window=window, combo=best_combo, train_pf=best_pf,
            trades=test_trades, net_pnl=sum(t.pnl for t in test_trades),
            n_eligible_combos=n_eligible))

    return WalkForwardResult(label=base_profile.label or "unlabelled",
                             symbol=base_profile.symbol,
                             windows=results, oos_trades=oos)


def promotion_verdict(result: WalkForwardResult, *, min_trades: int = 30,
                      min_pf: float = 1.10,
                      min_positive_window_frac: float = 0.5) -> Verdict:
    """Grade an out-of-sample record. PROMOTE only if ALL conditions hold.

    A signal must be (a) traded often enough to be more than noise, (b) net
    positive overall, (c) profitable enough to be worth the risk, and (d)
    consistent across windows rather than carried by one lucky quarter.
    """
    trades = result.oos_trades
    n = len(trades)
    notional = sum(t.entry_price * t.qty for t in trades)
    net_pct = (sum(t.pnl for t in trades) / notional * 100.0) if notional else 0.0
    pf = profit_factor(trades)
    positive = sum(1 for w in result.windows if w.net_pnl > 0)
    frac = positive / len(result.windows) if result.windows else 0.0

    reasons = []
    if n < min_trades:
        reasons.append(f"only {n} out-of-sample trades (need >= {min_trades})")
    if net_pct <= 0:
        reasons.append(f"net return {net_pct:.2f}% is not positive")
    if pf < min_pf:
        reasons.append(f"profit factor {pf:.2f} below {min_pf:.2f}")
    if frac < min_positive_window_frac:
        reasons.append(
            f"only {frac:.0%} of windows positive (need >= {min_positive_window_frac:.0%})")

    return Verdict(
        label=result.label, symbol=result.symbol,
        decision="REJECT" if reasons else "PROMOTE",
        reason="; ".join(reasons) if reasons else "passed all walk-forward criteria",
        n_trades=n, net_return_pct=net_pct, profit_factor=pf,
        positive_window_frac=frac)
