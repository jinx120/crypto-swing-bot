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


class FakeBroker:
    """Models the Alpaca paper crypto BUY pending_new stall + instant SELL fill."""
    def __init__(self, buy_stalls: bool = False):
        self.buy_stalls = buy_stalls
        self._position = None
        self.orders = {}

    def submit_market_buy(self, symbol, qty, **kw):
        oid = f"buy-{len(self.orders)}"
        status = "pending_new" if self.buy_stalls else "filled"
        self.orders[oid] = {"id": oid, "status": status, "filled_avg_price": 100.0,
                            "filled_qty": 0.0 if self.buy_stalls else qty}
        if not self.buy_stalls:
            self._position = {"symbol": symbol, "qty": qty, "avg_entry_price": 100.0}
        return self.orders[oid]

    def submit_market_sell(self, symbol, qty, **kw):
        oid = f"sell-{len(self.orders)}"
        self.orders[oid] = {"id": oid, "status": "filled", "filled_avg_price": 105.0,
                            "filled_qty": qty}
        self._position = None
        return self.orders[oid]

    def get_order(self, order_id, **kw):
        return self.orders.get(order_id)

    def get_position(self, symbol):
        return self._position

    def equity(self, mark_price):
        return 10_000.0
