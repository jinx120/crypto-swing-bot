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


from swingbot.selftest import DriftFinding, SessionStep, SessionTrace
from swingbot.selftest.report import update_roadmap_next_action


def test_report_includes_sessions_and_drift_sections(tmp_path):
    t = SessionTrace(session="s1-tabs", ok=False, duration_s=1.2,
                     steps=[SessionStep(desc="x", action="goto", ok=False,
                                        detail="boom")])
    d = DriftFinding(session="s1-tabs", step="x", expected="renders",
                     observed="boom", doc_ref="frontend/src/guide.md §y",
                     kind="drift")
    rp, dl = str(tmp_path / "r.md"), str(tmp_path / "d.md")
    write_report(_summary(), [], rp, dl, traces=[t], drift=[d])
    body = open(rp).read()
    assert "## Usage Sessions" in body and "s1-tabs" in body
    assert "## Drift Findings" in body and "frontend/src/guide.md" in body
    assert "drift:1" in open(dl).read()


def test_devlog_inserts_at_top_not_bottom(tmp_path):
    dl = tmp_path / "DEVLOG.md"
    dl.write_text("# Devlog\n\nRunning log of platform improvements. "
                  "Newest first.\n\n## Old entry\nold\n")
    write_report(_summary(), [], str(tmp_path / "r.md"), str(dl))
    content = dl.read_text()
    assert content.index("GREEN") < content.index("## Old entry")
    assert content.startswith("# Devlog")


def test_roadmap_writer_inserts_and_replaces_pointer(tmp_path):
    rm = tmp_path / "ROADMAP_STATUS.md"
    rm.write_text("# Roadmap\n\n## ▶ NEXT ACTION\n\nDo the thing.\n\n---\n\nrest\n")
    update_roadmap_next_action(str(rm), 3)
    one = rm.read_text()
    assert "3 drift finding(s)" in one and "Do the thing." in one
    update_roadmap_next_action(str(rm), 5)
    two = rm.read_text()
    assert "5 drift finding(s)" in two and "3 drift finding(s)" not in two
