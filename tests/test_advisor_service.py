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
