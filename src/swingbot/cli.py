from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from swingbot.backtest import run_backtest
from swingbot.data.historical import load_csv
from swingbot.profile import StrategyProfile


def run_from_files(csv_path: str, profile_path: str, starting_equity: float = 1000.0) -> dict:
    df = load_csv(csv_path)
    with open(profile_path) as f:
        profile = StrategyProfile.from_dict(json.load(f))
    _, metrics = run_backtest(df, profile, starting_equity=starting_equity)
    return asdict(metrics)


def main() -> None:
    ap = argparse.ArgumentParser(description="swingbot backtest")
    ap.add_argument("--csv", required=True, help="OHLCV CSV path")
    ap.add_argument("--profile", required=True, help="strategy profile JSON path")
    ap.add_argument("--equity", type=float, default=1000.0)
    args = ap.parse_args()
    result = run_from_files(args.csv, args.profile, args.equity)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
