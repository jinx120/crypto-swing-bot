from swingbot.selftest.checks import run_checks


def test_all_pass_when_rc_zero():
    results = run_checks("/fake/root", lambda cmd, cwd: (0, "ok"))
    assert len(results) == 3
    assert all(r.ok for r in results)


def test_nonzero_rc_yields_not_ok():
    def fake_runner(cmd, cwd):
        return (1, "FAILED") if "ruff" in " ".join(cmd) else (0, "ok")
    results = run_checks("/fake/root", fake_runner)
    ruff = next(r for r in results if r.name == "ruff")
    assert ruff.ok is False


def test_output_truncated_to_500_chars():
    results = run_checks("/fake/root", lambda cmd, cwd: (0, "x" * 600))
    assert all(len(r.key_output) <= 500 for r in results)


def test_tail_of_output_is_kept():
    results = run_checks("/fake/root", lambda cmd, cwd: (0, "a" * 600 + "TAIL"))
    assert all(r.key_output.endswith("TAIL") for r in results)


def test_npm_build_runs_in_frontend_subdir():
    seen = []
    def fake_runner(cmd, cwd):
        seen.append((cmd, cwd))
        return 0, ""
    run_checks("/root", fake_runner)
    npm_cwd = next(cwd for cmd, cwd in seen if "npm" in " ".join(cmd))
    assert npm_cwd.endswith("frontend")


def test_result_names_are_pytest_ruff_npm():
    results = run_checks("/fake/root", lambda cmd, cwd: (0, ""))
    assert [r.name for r in results] == ["pytest", "ruff", "npm-build"]
