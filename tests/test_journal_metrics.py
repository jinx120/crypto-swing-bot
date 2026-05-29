from datetime import datetime, timezone

from swingbot.journal import Trade, TradeJournal
from swingbot.types import ExitReason, Regime, Side


def _trade(pnl, reason=ExitReason.TAKE_PROFIT):
    return Trade(
        entry_ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        exit_ts=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
        side=Side.LONG, entry_price=100.0, exit_price=100.0 + pnl,
        qty=1.0, pnl=pnl, exit_reason=reason,
        score_at_entry=0.7, regime_at_entry=Regime.UPTREND,
    )


def test_journal_records_and_lists():
    j = TradeJournal()
    j.record(_trade(5.0))
    j.record(_trade(-2.0))
    assert len(j.trades) == 2
    assert j.trades[0].pnl == 5.0


from swingbot.metrics import compute_metrics


def test_metrics_on_known_trades():
    trades = [_trade(10.0), _trade(10.0), _trade(-5.0), _trade(-5.0)]
    m = compute_metrics(trades)
    assert m.n_trades == 4
    assert m.win_rate == 0.5
    assert abs(m.avg_win - 10.0) < 1e-9
    assert abs(m.avg_loss - (-5.0)) < 1e-9
    assert abs(m.expectancy - 2.5) < 1e-9          # (10+10-5-5)/4
    assert abs(m.profit_factor - 2.0) < 1e-9       # 20 / 10
    assert m.max_drawdown <= 0.0

def test_metrics_empty():
    m = compute_metrics([])
    assert m.n_trades == 0
    assert m.expectancy == 0.0
    assert m.profit_factor == 0.0
