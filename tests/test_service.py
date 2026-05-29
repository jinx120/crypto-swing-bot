from swingbot.service import BotController


def test_botcontroller_protocol_methods_exist():
    for m in ("status", "journal", "metrics", "halt", "reset", "pause",
              "resume", "flatten", "set_mode", "start", "stop"):
        assert hasattr(BotController, m)
