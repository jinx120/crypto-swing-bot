import pandas as pd
import pytest
from swingbot.types import SignalResult


class FakeKronos:
    def __init__(self, score: float):
        self._score = score

    def evaluate(self, ctx):
        return SignalResult(name="kronos", score=self._score, meta={})


@pytest.fixture
def uptrend_window():
    # 60 ascending 5-min bars; v1 signals consume open/high/low/close/volume.
    closes = [100 + i * 0.5 for i in range(60)]
    return pd.DataFrame({
        "open": closes, "high": [c + 0.3 for c in closes],
        "low": [c - 0.3 for c in closes], "close": closes,
        "volume": [10.0] * 60,
    })
