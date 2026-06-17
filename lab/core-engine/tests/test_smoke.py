def test_package_imports():
    import core_engine  # noqa: F401


def test_swingbot_reuse_available():
    # The experiment reuses proven v1 plumbing by import.
    from swingbot.broker.base import Broker  # noqa: F401
    from swingbot.exits import exit_decision  # noqa: F401
