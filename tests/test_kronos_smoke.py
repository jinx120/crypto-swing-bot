from __future__ import annotations

import os
import sys

import pandas as pd
import pytest

SMOKE = bool(os.environ.get("KRONOS_SMOKE_TEST"))


@pytest.mark.skipif(not SMOKE, reason="set KRONOS_SMOKE_TEST=1 to run real model")
def test_real_predictor_returns_correct_shape():
    """Load the real Kronos model and verify predict() output shape.

    Before running:
        pip install -e '.[kronos]'
        KRONOS_SMOKE_TEST=1 pytest tests/test_kronos_smoke.py -v

    Verify the KronosPredictor() constructor args against the Kronos README
    at https://github.com/shiyu-coder/Kronos before using in production.
    """
    from swingbot.signals.kronos_adapter import KronosAdapter, _load_kronos

    _, _, KronosPredictor = _load_kronos()
    predictor = KronosPredictor()  # adjust constructor per Kronos README

    n = 100
    candles = pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open":   [100.0 + i * 0.1 for i in range(n)],
        "high":   [101.0 + i * 0.1 for i in range(n)],
        "low":    [99.0  + i * 0.1 for i in range(n)],
        "close":  [100.5 + i * 0.1 for i in range(n)],
        "volume": [1000.0] * n,
    })

    pred_len = 4
    adapter = KronosAdapter(predictor=predictor, pred_len=pred_len, timeout_s=120.0)
    result = adapter.forecast(candles)

    assert result is not None, "Real Kronos predictor returned None"
    assert len(result) == pred_len, f"Expected {pred_len} rows, got {len(result)}"
    for col in ("open", "high", "low", "close"):
        assert col in result.columns, f"Missing column {col!r} in forecast"
    assert result["close"].notna().all(), "Forecast close contains NaN"


@pytest.mark.skipif(not SMOKE, reason="set KRONOS_SMOKE_TEST=1 to run real model")
def test_missing_kronos_import_gives_helpful_error():
    """ImportError message includes the pip install command."""
    original = sys.modules.pop("kronos", None)
    original_model = sys.modules.pop("kronos.model", None)
    try:
        import importlib
        from swingbot.signals import kronos_adapter
        importlib.reload(kronos_adapter)
        with pytest.raises(ImportError, match="pip install"):
            kronos_adapter._load_kronos()
    finally:
        if original is not None:
            sys.modules["kronos"] = original
        if original_model is not None:
            sys.modules["kronos.model"] = original_model
