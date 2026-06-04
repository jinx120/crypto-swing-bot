from swingbot.selftest import CheckResult, UIFinding, HealthSummary


def test_check_result_fields():
    c = CheckResult(name="pytest", ok=True, duration_s=1.5, key_output="5 passed")
    assert c.name == "pytest" and c.ok is True and c.duration_s == 1.5


def test_ui_finding_fields():
    f = UIFinding(route="/", severity="fatal", kind="exception",
                  detail="err", screenshot_path="/tmp/x.png")
    assert f.route == "/" and f.severity == "fatal"


def test_health_summary_fields():
    s = HealthSummary(green=True, checks=[], ui_findings=[],
                      started_at=1000.0, duration_s=1.5, diffstat="")
    assert s.green is True and s.checks == []
