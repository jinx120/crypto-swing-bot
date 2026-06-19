from datetime import datetime, timezone

from core_engine.contracts import EnginePosition


class _RecordingStore:
    def __init__(self): self.calls = []
    def set(self, pos): self.calls.append(("set", pos))
    def clear(self): self.calls.append(("clear", None))


def _engine_with(monkeypatch, position_store):
    from core_engine import loop as loop_mod
    from core_engine.contracts import Action, Decision

    eng = loop_mod.Engine.__new__(loop_mod.Engine)
    # Minimal hand-wired engine: only the attributes tick() touches.
    eng._journal = type("J", (), {"log": lambda self, e: None})()
    eng._position_store = position_store
    # Additional attributes accessed by tick() before monkeypatched functions
    # consume the arguments (Python evaluates args before the call).
    eng._store = None
    eng._fetcher = None
    eng._profile = None
    eng._kronos = None
    return eng, loop_mod, Action, Decision


def test_clear_called_when_no_position_and_hold(monkeypatch):
    store = _RecordingStore()
    eng, loop_mod, Action, Decision = _engine_with(monkeypatch, store)
    # Stub the engine collaborators so tick() reaches the HOLD return path.
    monkeypatch.setattr(loop_mod, "refresh_candles", lambda *a, **k: 0)
    monkeypatch.setattr(loop_mod, "latest_atr", lambda *a, **k: 0.01)
    eng._exec = type("E", (), {"reconcile": lambda self, *a, **k: None})()
    monkeypatch.setattr(loop_mod, "build_context", lambda *a, **k: object())
    monkeypatch.setattr(loop_mod, "decide",
                        lambda *a, **k: Decision(Action.HOLD, 0.0, "hold", {}))
    eng.position = None
    eng.tick(datetime.now(timezone.utc))
    assert ("clear", None) in store.calls
