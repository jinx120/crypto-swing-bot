def test_advisor_client_parses_json():
    from swingbot.advisor.client import AdvisorClient

    client = AdvisorClient(model="gemma-4-e2b-it-qat-q4")
    client._raw_reply = lambda prompt: 'noise {"BTC/USD": {"tp_pct": 0.02}} trailing'

    assert client.review({"BTC/USD": {"win_rate": 0.6}}) == {"BTC/USD": {"tp_pct": 0.02}}


def test_advisor_client_bad_reply_returns_empty():
    from swingbot.advisor.client import AdvisorClient

    client = AdvisorClient(model="x")
    client._raw_reply = lambda prompt: "the model rambled with no json"

    assert client.review({}) == {}


def _profile(symbol="BTC/USD"):
    return {
        "symbol": symbol,
        "timeframe": "15m",
        "signals": {"kronos": {"weight": 1.0, "threshold_pct": 0.0075}},
        "entry_threshold": 1.0,
        "bracket_mode": "pct",
        "tp_pct": 0.015,
        "sl_pct": 0.01,
        "max_position_frac": 0.25,
    }


class FakeClient:
    def __init__(self, proposal):
        self.proposal = proposal

    def review(self, digest):
        return self.proposal


class SpyBroker:
    def __init__(self):
        self.calls = []

    def submit_market_buy(self, *args, **kwargs):
        self.calls.append(("submit_market_buy", args, kwargs))

    def submit_market_sell(self, *args, **kwargs):
        self.calls.append(("submit_market_sell", args, kwargs))


def test_run_review_applies_in_band_and_journals(tmp_path):
    from swingbot.advisor.journal import TuningJournal
    from swingbot.advisor.service import AdvisorService
    from swingbot.profiles import ProfileStore

    profiles = ProfileStore(str(tmp_path / "profiles.db"))
    profiles.save("btc", _profile())
    spy_broker = SpyBroker()

    service = AdvisorService(
        client=FakeClient({"BTC/USD": {"tp_pct": 0.02, "rationale": "winners run"}}),
        journal=TuningJournal(str(tmp_path / "tuning.db")),
        profiles=profiles,
        get_digest=lambda: {"BTC/USD": {}},
        get_dial=lambda: "balanced",
        broker=spy_broker,
    )

    out = service.run_review()

    assert out["applied"]["BTC/USD"]["tp_pct"] == 0.02
    assert profiles.get("btc")["tp_pct"] == 0.02
    assert len(service.journal.list_entries()) == 1
    assert out["batch_id"]
    assert spy_broker.calls == []


def test_run_review_clamps_out_of_band_and_logs_drop(tmp_path):
    from swingbot.advisor.journal import TuningJournal
    from swingbot.advisor.service import AdvisorService
    from swingbot.profiles import ProfileStore

    profiles = ProfileStore(str(tmp_path / "profiles.db"))
    profiles.save("btc", _profile())

    service = AdvisorService(
        client=FakeClient({"BTC/USD": {"tp_pct": 0.99, "rationale": "too high"}}),
        journal=TuningJournal(str(tmp_path / "tuning.db")),
        profiles=profiles,
        get_digest=lambda: {"BTC/USD": {}},
        get_dial=lambda: "balanced",
    )

    out = service.run_review()

    assert profiles.get("btc")["tp_pct"] == 0.05
    assert out["applied"]["BTC/USD"]["tp_pct"] == 0.05
    assert any("clamped" in item for item in out["dropped"])
