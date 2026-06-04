import tempfile
from swingbot.selftest import CheckResult, UIFinding, HealthSummary
from swingbot.selftest.report import write_report
from swingbot.decision.proposals import make_proposal


def _summary(green=True):
    return HealthSummary(
        green=green,
        checks=[
            CheckResult("pytest",    green, 1.5, "288 passed" if green else "1 failed"),
            CheckResult("ruff",      True,  0.1, "All checks passed."),
            CheckResult("npm-build", True,  0.2, "built"),
        ],
        ui_findings=[] if green else [
            UIFinding("/", "fatal", "exception", "page crashed", "/tmp/index.png")
        ],
        started_at=1717497131.0,
        duration_s=2.1,
        diffstat=" src/swingbot/selftest/__init__.py | 15 +++",
    )


def test_green_report_contains_status_and_check_names():
    s = _summary(green=True)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as rf, \
         tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as df:
        rp, dp = rf.name, df.name
    write_report(s, [], rp, dp)
    content = open(rp).read()
    assert "GREEN" in content
    assert "pytest" in content and "ruff" in content and "npm-build" in content
    assert "288 passed" in content


def test_red_report_shows_red_in_report_and_devlog():
    s = _summary(green=False)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as rf, \
         tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as df:
        rp, dp = rf.name, df.name
    write_report(s, [], rp, dp)
    assert "RED" in open(rp).read()
    assert "RED" in open(dp).read()


def test_devlog_line_appended_not_overwritten():
    s = _summary(green=True)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as rf, \
         tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as df:
        rp, dp = rf.name, df.name
    open(dp, "w").write("EXISTING LINE\n")
    write_report(s, [], rp, dp)
    devlog = open(dp).read()
    assert "EXISTING LINE" in devlog
    assert "GREEN" in devlog


def test_devlog_contains_check_status_icons():
    s = _summary(green=True)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as rf, \
         tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as df:
        rp, dp = rf.name, df.name
    write_report(s, [], rp, dp)
    devlog = open(dp).read()
    assert "pytest✓" in devlog


def test_proposals_shown_in_report():
    s = _summary(green=True)
    p = make_proposal("ui_fix", {"route": "/", "issue": "console error"}, "Fix it", 0.8, now=1)
    p.guardrail_status = "approved"
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as rf, \
         tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as df:
        rp, dp = rf.name, df.name
    write_report(s, [p], rp, dp)
    content = open(rp).read()
    assert "ui_fix" in content
    assert "Proposals" in content


def test_diffstat_included_in_report():
    s = _summary(green=True)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as rf, \
         tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as df:
        rp, dp = rf.name, df.name
    write_report(s, [], rp, dp)
    assert "selftest/__init__.py" in open(rp).read()
