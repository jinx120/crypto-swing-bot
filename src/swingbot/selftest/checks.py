from __future__ import annotations

import os
import time

from swingbot.selftest import CheckResult

_OUTPUT_LIMIT = 500

_CHECKS = [
    ("pytest",    [".venv/bin/python", "-m", "pytest", "-q"],       None),
    ("ruff",      [".venv/bin/python", "-m", "ruff", "check", "."], None),
    ("npm-build", ["npm", "run", "build"],                          "frontend"),
]


def run_checks(project_root: str, runner_fn) -> list[CheckResult]:
    results = []
    for name, cmd, subdir in _CHECKS:
        cwd = os.path.join(project_root, subdir) if subdir else project_root
        t0 = time.monotonic()
        rc, out = runner_fn(cmd, cwd)
        results.append(CheckResult(
            name=name,
            ok=(rc == 0),
            duration_s=round(time.monotonic() - t0, 2),
            key_output=(out or "")[-_OUTPUT_LIMIT:].strip(),
        ))
    return results
