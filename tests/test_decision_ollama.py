from swingbot.decision.ollama import OllamaClient


def test_generate_json_ok_parses_response():
    def fake_transport(url, payload, timeout):
        assert payload["model"] == "qwen2.5"
        assert payload["format"] == {"type": "object"}
        return {"response": '{"proposals": []}'}
    c = OllamaClient("http://x:11434", "qwen2.5", 5.0, transport=fake_transport)
    res = c.generate_json("hi", {"type": "object"})
    assert res.ok and res.data == {"proposals": []} and res.error is None


def test_generate_json_transport_error_is_caught():
    def boom(url, payload, timeout):
        raise OSError("connection refused")
    c = OllamaClient("http://x:11434", "qwen2.5", 5.0, transport=boom)
    res = c.generate_json("hi", {"type": "object"})
    assert res.ok is False and res.data is None and "connection refused" in res.error


def test_generate_json_bad_json_is_caught():
    c = OllamaClient("http://x", "qwen2.5", 5.0,
                     transport=lambda u, p, t: {"response": "not json{"})
    res = c.generate_json("hi", {"type": "object"})
    assert res.ok is False and "json" in res.error.lower()
