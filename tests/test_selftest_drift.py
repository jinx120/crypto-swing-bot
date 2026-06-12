from swingbot.selftest import SessionStep, SessionTrace
from swingbot.selftest.drift import findings_to_proposals, reconcile


def _trace(steps):
    return SessionTrace(session="s6-guide", ok=all(s.ok for s in steps),
                        steps=steps)


def _fail(key, detail="observed mismatch", desc="check"):
    return SessionStep(desc=desc, action="assert", ok=False, detail=detail,
                       expectation_key=key, screenshot_path="/shots/x.png")


def test_passing_traces_produce_no_findings():
    t = _trace([SessionStep(desc="ok", action="assert", ok=True)])
    assert reconcile([t]) == []


def test_failed_step_with_doc_biased_expectation_is_drift():
    f = reconcile([_trace([_fail("s6.affordance-exists",
                                 'Guide §"x" names \'Set active\' but missing')])])
    assert len(f) == 1
    d = f[0]
    assert d.kind == "drift" and d.session == "s6-guide"
    assert d.doc_ref.startswith("frontend/src/guide.md")
    assert d.observed.startswith("Guide")
    assert d.screenshot_path == "/shots/x.png"


def test_failed_step_with_ui_biased_expectation_is_drift_too():
    f = reconcile([_trace([_fail("s1.tab-renders")])])
    assert f[0].kind == "drift"


def test_failed_step_without_expectation_key_is_bug():
    f = reconcile([_trace([_fail("", detail="browser crashed")])])
    assert f[0].kind == "bug" and f[0].doc_ref == ""


def test_findings_to_proposals_maps_bias_and_stamps():
    findings = reconcile([_trace([
        _fail("s6.affordance-exists", "guide says X"),     # doc bias
        _fail("s1.tab-renders", "brain tab blank"),        # ui bias
        _fail("", "crash"),                                # bug -> ui_fix
    ])])
    props = findings_to_proposals(findings)
    assert [p.action for p in props] == ["doc_fix", "ui_fix", "ui_fix"]
    for p in props:
        assert p.source == "usage-agent"
        assert p.guardrail_status == "approved"
        assert {"expected", "observed", "doc", "section", "suggestion"} <= set(p.target)


def test_same_finding_twice_dedupes_by_id():
    f = reconcile([_trace([_fail("s6.affordance-exists", "guide says X")])])
    a = findings_to_proposals(f)[0]
    b = findings_to_proposals(f)[0]
    assert a.id == b.id
