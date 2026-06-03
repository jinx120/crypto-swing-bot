from swingbot.notify import DiscordNotifier


def test_sends_when_webhook_configured():
    sent = []
    n = DiscordNotifier(lambda: "http://hook", transport=lambda u, p, t: sent.append((u, p)))
    assert n.send("proposals_ready", {"count": 3}) is True
    assert sent and sent[0][0] == "http://hook" and "proposals_ready" in sent[0][1]["content"]


def test_noop_when_no_webhook():
    sent = []
    n = DiscordNotifier(lambda: None, transport=lambda u, p, t: sent.append(1))
    assert n.send("proposals_ready", {"count": 3}) is False
    assert sent == []


def test_transport_failure_is_swallowed():
    def boom(u, p, t):
        raise OSError("discord down")
    n = DiscordNotifier(lambda: "http://hook", transport=boom)
    assert n.send("blocked_or_error", {"error": "x"}) is False   # never raises
