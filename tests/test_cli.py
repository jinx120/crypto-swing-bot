import json

from swingbot.cli import run_from_files


def test_run_from_files_outputs_metrics(tmp_path):
    import numpy as np, pandas as pd
    n = 130
    closes = np.linspace(100, 130, n)
    pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open": closes, "high": closes * 1.002, "low": closes * 0.998,
        "close": closes, "volume": np.full(n, 100.0),
    }).to_csv(tmp_path / "trx.csv", index=False)

    profile = {
        "symbol": "TRX/USD",
        "signals": {"oversold": {"weight": 1.0, "oversold_level": 45, "period": 14}},
        "entry_threshold": 0.2, "regime_ma_period": 20, "fee_rate": 0.0,
        "slippage_rate": 0.0,
    }
    (tmp_path / "profile.json").write_text(json.dumps(profile))

    result = run_from_files(str(tmp_path / "trx.csv"), str(tmp_path / "profile.json"),
                            starting_equity=1000.0)
    assert "n_trades" in result
    assert "expectancy" in result
    assert isinstance(result["n_trades"], int)
