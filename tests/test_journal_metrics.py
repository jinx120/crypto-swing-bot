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
