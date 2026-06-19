from __future__ import annotations

import json
import os
import sqlite3


def _connect(db_path: str) -> sqlite3.Connection | None:
    if not os.path.exists(db_path):
        return None
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def recent_events(journal_db: str, limit: int = 50) -> list[dict]:
    conn = _connect(journal_db)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT ts, kind, symbol, reason, payload FROM events "
            "ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    out = []
    for ts, kind, symbol, reason, payload in rows:
        try:
            parsed = json.loads(payload) if payload else {}
        except (ValueError, TypeError):
            parsed = {}
        out.append({"ts": ts, "kind": kind, "symbol": symbol,
                    "reason": reason, "payload": parsed})
    return out


def recent_trades(journal_db: str, limit: int = 50) -> list[dict]:
    conn = _connect(journal_db)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT ts, reason, payload FROM events WHERE kind='pnl' "
            "ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    out = []
    for ts, reason, payload in rows:
        try:
            parsed = json.loads(payload) if payload else {}
        except (ValueError, TypeError):
            parsed = {}
        out.append({"ts": ts, "pnl": float(parsed.get("realized", 0.0)),
                    "won": bool(parsed.get("won", False)), "reason": reason})
    return out


def recent_candles(candle_db: str, symbol: str, timeframe: str,
                   limit: int = 200) -> list[dict]:
    conn = _connect(candle_db)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT ts, open, high, low, close, volume FROM bars "
            "WHERE symbol=? AND timeframe=? ORDER BY ts DESC LIMIT ?",
            (symbol, timeframe, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    rows.reverse()
    return [{"time": int(ts), "open": o, "high": h, "low": lo,
             "close": c, "volume": v} for ts, o, h, lo, c, v in rows]


def _state_value(state_db: str, key: str) -> str | None:
    conn = _connect(state_db)
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT value FROM runtime_state WHERE key=?", (key,)
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
    return row[0] if row else None


def _position_from_journal(journal_db: str) -> dict | None:
    conn = _connect(journal_db)
    if conn is None:
        return None
    try:
        rows = conn.execute(
            "SELECT kind, payload FROM events WHERE kind IN ('order','pnl') "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
    if not rows:
        return None
    kind, payload = rows
    if kind != "order":
        return None                       # most recent lifecycle event closed it
    try:
        p = json.loads(payload) if payload else {}
    except (ValueError, TypeError):
        p = {}
    if not p.get("open"):
        return None
    return {"symbol": p.get("symbol", "BTC/USD"),
            "entry_price": float(p.get("entry", 0.0)),
            "qty": float(p.get("qty", 0.0)),
            "stop": p.get("stop"), "tp": p.get("tp"),
            "entry_ts": p.get("entry_ts")}


def live_position(state_db: str, journal_db: str) -> dict | None:
    raw = _state_value(state_db, "open_position")
    if raw:
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            parsed = None
        if parsed:
            return parsed
    return _position_from_journal(journal_db)
