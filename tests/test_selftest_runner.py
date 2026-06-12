import os
import tempfile
from swingbot.selftest import SessionStep, SessionTrace, UIFinding
from swingbot.selftest.runner import SelfTestConfig, run


def _cfg(tmp: str, skip_llm: bool = True) -> SelfTestConfig:
    return SelfTestConfig(
        project_root="/fake/root",
        base_url="http://localhost:8000",
        screenshot_dir=os.path.join(tmp, "shots"),
        report_path=os.path.join(tmp, "report.md"),
        devlog_path=os.path.join(tmp, "DEVLOG.md"),
        ollama_url="http://localhost:11434",
        ollama_model="qwen3.5:9b",
        ollama_timeout_s=5.0,
        proposal_store_path=os.path.join(tmp, "proposals.json"),
        discord_webhook_getter=lambda: None,
        skip_llm=skip_llm,
        agent_dir=os.path.join(tmp, "agent"),
        roadmap_path=os.path.join(tmp, "ROADMAP_STATUS.md"),
        run_sessions=False,            # opt in per test; real default is True
    )


_OK_RUNNER     = lambda cmd, cwd: (0, "ok")
_FAIL_PYTEST   = lambda cmd, cwd: (1, "1 failed") if "pytest" in " ".join(cmd) else (0, "ok")
_NO_FINDINGS   = lambda url, d: []
_FATAL_FINDING = lambda url, d: [UIFinding("/", "fatal", "exception", "crash", "/tmp/x.png")]
_WARN_FINDING  = lambda url, d: [UIFinding("/", "warn",  "console",   "warn",  "/tmp/x.png")]
_NO_LLM        = lambda s, c, st, n: []


def test_all_pass_returns_0():
    with tempfile.TemporaryDirectory() as tmp:
        assert run(_cfg(tmp), runner_fn=_OK_RUNNER, probe_fn=_NO_FINDINGS, llm_fn=_NO_LLM) == 0


def test_failing_check_returns_1():
    with tempfile.TemporaryDirectory() as tmp:
        assert run(_cfg(tmp), runner_fn=_FAIL_PYTEST, probe_fn=_NO_FINDINGS, llm_fn=_NO_LLM) == 1


def test_fatal_ui_finding_returns_1():
    with tempfile.TemporaryDirectory() as tmp:
        assert run(_cfg(tmp), runner_fn=_OK_RUNNER, probe_fn=_FATAL_FINDING, llm_fn=_NO_LLM) == 1


def test_warn_ui_finding_does_not_block_green():
    with tempfile.TemporaryDirectory() as tmp:
        assert run(_cfg(tmp), runner_fn=_OK_RUNNER, probe_fn=_WARN_FINDING, llm_fn=_NO_LLM) == 0


def test_llm_not_called_on_red():
    with tempfile.TemporaryDirectory() as tmp:
        llm_called = [False]
        def fake_llm(s, c, st, n):
            llm_called[0] = True
            return []
        run(_cfg(tmp, skip_llm=False), runner_fn=_FAIL_PYTEST,
            probe_fn=_NO_FINDINGS, llm_fn=fake_llm)
        assert llm_called[0] is False


def test_llm_called_on_green_when_not_skipped():
    with tempfile.TemporaryDirectory() as tmp:
        llm_called = [False]
        def fake_llm(s, c, st, n):
            llm_called[0] = True
            return []
        run(_cfg(tmp, skip_llm=False), runner_fn=_OK_RUNNER,
            probe_fn=_NO_FINDINGS, llm_fn=fake_llm)
        assert llm_called[0] is True


def test_llm_not_called_when_skip_llm_true():
    with tempfile.TemporaryDirectory() as tmp:
        llm_called = [False]
        def fake_llm(s, c, st, n):
            llm_called[0] = True
            return []
        run(_cfg(tmp, skip_llm=True), runner_fn=_OK_RUNNER,
            probe_fn=_NO_FINDINGS, llm_fn=fake_llm)
        assert llm_called[0] is False


def test_report_written_on_green():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        run(cfg, runner_fn=_OK_RUNNER, probe_fn=_NO_FINDINGS, llm_fn=_NO_LLM)
        assert os.path.exists(cfg.report_path)
        assert "GREEN" in open(cfg.report_path).read()


def test_report_written_on_red():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        run(cfg, runner_fn=_FAIL_PYTEST, probe_fn=_NO_FINDINGS, llm_fn=_NO_LLM)
        assert os.path.exists(cfg.report_path)
        assert "RED" in open(cfg.report_path).read()


def test_crash_in_probe_returns_2():
    with tempfile.TemporaryDirectory() as tmp:
        def boom(url, d):
            raise RuntimeError("playwright exploded")
        exit_code = run(_cfg(tmp), runner_fn=_OK_RUNNER, probe_fn=boom, llm_fn=_NO_LLM)
        assert exit_code == 2


def _ok_trace(name="s1-tabs"):
    return SessionTrace(session=name, ok=True,
                        steps=[SessionStep(desc="x", action="goto", ok=True)])


def _drift_trace():
    return SessionTrace(session="s6-guide", ok=False, steps=[SessionStep(
        desc="check", action="assert", ok=False,
        detail="missing", expectation_key="s6.affordance-exists")])


def test_session_infra_failure_is_red():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        cfg.run_sessions = True
        rc = run(cfg, runner_fn=_OK_RUNNER, probe_fn=_NO_FINDINGS,
                 sessions_fn=lambda config: ([], False), llm_fn=_NO_LLM)
        assert rc == 1


def test_drift_only_stays_green_and_stores_proposals():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        cfg.run_sessions = True
        rc = run(cfg, runner_fn=_OK_RUNNER, probe_fn=_NO_FINDINGS,
                 sessions_fn=lambda config: ([_drift_trace()], True), llm_fn=_NO_LLM)
        assert rc == 0
        from swingbot.decision.proposals import ProposalStore
        rows = ProposalStore(cfg.proposal_store_path).all()
        assert any(p.source == "usage-agent" and p.action == "doc_fix" for p in rows)


def test_agent_run_persisted():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        cfg.run_sessions = True
        run(cfg, runner_fn=_OK_RUNNER, probe_fn=_NO_FINDINGS,
            sessions_fn=lambda config: ([_ok_trace()], True), llm_fn=_NO_LLM)
        from swingbot.selftest.agentstore import AgentRunStore
        latest = AgentRunStore(cfg.agent_dir).latest()
        assert latest["green"] is True
        assert latest["traces"][0]["session"] == "s1-tabs"


def test_no_sessions_flag_skips_stage():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        cfg.run_sessions = False
        called = []
        rc = run(cfg, runner_fn=_OK_RUNNER, probe_fn=_NO_FINDINGS,
                 sessions_fn=lambda config: called.append(1) or ([], True),
                 llm_fn=_NO_LLM)
        assert rc == 0 and called == []
