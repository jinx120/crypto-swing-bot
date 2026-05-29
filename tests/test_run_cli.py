import json

from swingbot.run import build_orchestrator


def test_build_orchestrator_wires_components(tmp_path, monkeypatch):
    import swingbot.run as run_mod

    class _Data:
        def __init__(self, *a, **k): pass
    class _Broker:
        def __init__(self, *a, **k): pass

    monkeypatch.setattr(run_mod, "AlpacaData", _Data)
    monkeypatch.setattr(run_mod, "AlpacaBroker", _Broker)
    monkeypatch.setenv("ALPACA_API_KEY_ID", "kid")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "sec")
    monkeypatch.setenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    profile = {"symbol": "TRX/USD",
               "signals": {"oversold": {"weight": 1.0, "oversold_level": 45}},
               "entry_threshold": 0.2}
    pf = tmp_path / "p.json"
    pf.write_text(json.dumps(profile))

    orch = build_orchestrator(str(pf), db_path=str(tmp_path / "s.db"))
    assert orch.profile.symbol == "TRX/USD"
    assert orch.broker is not None
    assert orch.data is not None
