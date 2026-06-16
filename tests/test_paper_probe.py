import pandas as pd

from swingbot.probe_marker import ProbeMarkerStore, probe_should_fire
from swingbot.signals.paper_probe import PaperProbeSignal
from swingbot.types import MarketContext


def _ctx():
    df = pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=5, freq="15min", tz="UTC"),
        "open": [1.0] * 5,
        "high": [1.0] * 5,
        "low": [1.0] * 5,
        "close": [1.0] * 5,
        "volume": [1.0] * 5,
    })
    return MarketContext(candles=df)


def test_probe_signal_always_fires_deterministically():
    sig = PaperProbeSignal(weight=1.0)
    r = sig.evaluate(_ctx())
    assert r.name == "paper_probe"
    assert r.score == 1.0
    assert r.meta["probe"] is True


def test_marker_persists_completion(tmp_path):
    db = str(tmp_path / "probe.db")
    store = ProbeMarkerStore(db)
    assert store.is_complete("paper_probe") is False
    store.mark_complete("paper_probe")
    assert store.is_complete("paper_probe") is True
    assert ProbeMarkerStore(db).is_complete("paper_probe") is True


def test_should_fire_requires_enabled_paper_and_not_complete(tmp_path):
    store = ProbeMarkerStore(str(tmp_path / "probe.db"))
    assert probe_should_fire(store, enabled=True, mode="paper") is True
    assert probe_should_fire(store, enabled=False, mode="paper") is False
    assert probe_should_fire(store, enabled=True, mode="live") is False
    store.mark_complete("paper_probe")
    assert probe_should_fire(store, enabled=True, mode="paper") is False
