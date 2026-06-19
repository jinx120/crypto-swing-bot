import json
import sqlite3

from swingbot.autodash.queries import recent_events


def _make_journal(path, rows):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
              "ts TEXT, kind TEXT, symbol TEXT, reason TEXT, payload TEXT)")
    for ts, kind, sym, reason, payload in rows:
        c.execute("INSERT INTO events (ts, kind, symbol, reason, payload) "
                  "VALUES (?,?,?,?,?)",
                  (ts, kind, sym, reason, json.dumps(payload)))
    c.commit()
    c.close()


def test_recent_events_newest_first_and_parsed(tmp_path):
    p = str(tmp_path / "journal.db")
    _make_journal(p, [
        ("2026-06-17T17:01:00+00:00", "decision", "BTC/USD", "hold", {"action": "hold"}),
        ("2026-06-17T17:06:00+00:00", "order", "BTC/USD", "entry filled",
         {"open": True, "qty": 0.01}),
    ])
    out = recent_events(p, limit=10)
    assert [e["kind"] for e in out] == ["order", "decision"]
    assert out[0]["payload"]["open"] is True


def test_recent_events_missing_db_returns_empty(tmp_path):
    assert recent_events(str(tmp_path / "nope.db")) == []


from swingbot.autodash.queries import recent_trades


def test_recent_trades_maps_pnl_events(tmp_path):
    p = str(tmp_path / "journal.db")
    _make_journal(p, [
        ("2026-06-17T18:00:00+00:00", "decision", "BTC/USD", "hold", {}),
        ("2026-06-17T18:30:00+00:00", "pnl", "BTC/USD", "closed: take_profit",
         {"realized": 12.5, "won": True}),
        ("2026-06-17T19:00:00+00:00", "pnl", "BTC/USD", "closed: stop_loss",
         {"realized": -8.0, "won": False}),
    ])
    out = recent_trades(p, limit=10)
    assert len(out) == 2                       # decision event excluded
    assert out[0]["pnl"] == -8.0 and out[0]["won"] is False
    assert out[1]["pnl"] == 12.5 and out[1]["reason"] == "closed: take_profit"


from swingbot.autodash.queries import recent_candles


def _make_candles(path, bars):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE bars (symbol TEXT, timeframe TEXT, ts INTEGER, "
              "open REAL, high REAL, low REAL, close REAL, volume REAL, "
              "PRIMARY KEY (symbol, timeframe, ts))")
    c.executemany("INSERT INTO bars VALUES (?,?,?,?,?,?,?,?)", bars)
    c.commit()
    c.close()


def test_recent_candles_oldest_first_chart_shape(tmp_path):
    p = str(tmp_path / "candles.db")
    _make_candles(p, [
        ("BTC/USD", "5m", 1781265600, 100, 101, 99, 100.5, 1.0),
        ("BTC/USD", "5m", 1781265900, 100.5, 102, 100, 101.5, 2.0),
    ])
    out = recent_candles(p, "BTC/USD", "5m", limit=10)
    assert [c["time"] for c in out] == [1781265600, 1781265900]
    assert set(out[0]) == {"time", "open", "high", "low", "close", "volume"}


from swingbot.autodash.queries import live_position


def _make_state(path, kv):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE runtime_state (key TEXT PRIMARY KEY, value TEXT)")
    for k, v in kv.items():
        c.execute("INSERT INTO runtime_state VALUES (?,?)", (k, v))
    c.commit()
    c.close()


def test_live_position_reads_persisted_state(tmp_path):
    sp = str(tmp_path / "state.db")
    jp = str(tmp_path / "journal.db")
    _make_state(sp, {"running_desired": "1", "open_position": json.dumps(
        {"symbol": "BTC/USD", "entry_price": 65000.0, "qty": 0.01,
         "stop": 64000.0, "tp": 67000.0, "entry_ts": "2026-06-17T18:00:00+00:00"})})
    _make_journal(jp, [])
    pos = live_position(sp, jp)
    assert pos["entry_price"] == 65000.0 and pos["qty"] == 0.01


def test_live_position_falls_back_to_journal_order(tmp_path):
    sp = str(tmp_path / "state.db")
    jp = str(tmp_path / "journal.db")
    _make_state(sp, {"running_desired": "1"})       # no open_position key
    _make_journal(jp, [
        ("2026-06-17T18:00:00+00:00", "order", "BTC/USD", "entry filled",
         {"open": True, "qty": 0.02, "entry": 64000.0}),
    ])
    pos = live_position(sp, jp)
    assert pos["entry_price"] == 64000.0 and pos["qty"] == 0.02


def test_live_position_none_when_closed_after_open(tmp_path):
    sp = str(tmp_path / "state.db")
    jp = str(tmp_path / "journal.db")
    _make_state(sp, {"running_desired": "1"})
    _make_journal(jp, [
        ("2026-06-17T18:00:00+00:00", "order", "BTC/USD", "entry filled",
         {"open": True, "qty": 0.02, "entry": 64000.0}),
        ("2026-06-17T18:30:00+00:00", "pnl", "BTC/USD", "closed: tp",
         {"realized": 5.0, "won": True}),
    ])
    assert live_position(sp, jp) is None
