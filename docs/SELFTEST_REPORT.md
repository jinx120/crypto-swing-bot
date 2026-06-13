# Self-test Report

**Run:** 2026-06-12 20:56:26 UTC  |  **Status:** 🟢 GREEN  |  **Duration:** 43.25s

## Deterministic Checks

| Check | Status | Duration | Output |
|-------|--------|----------|--------|
| pytest | ✅ | 14.02s | warnings.warn(  # deprecated in 14.0 - 2024-11-09  .venv/lib/python3.12/site-packages/fastapi/testclient.py:1   /home/re |
| ruff | ✅ | 0.04s | All checks passed! |
| npm-build | ✅ | 3.17s | > swingbot-frontend@0.1.0 build > vite build  vite v5.4.21 building for production... transforming... ✓ 61 modules trans |

## UI Probe Findings

_No UI findings._

## Usage Sessions

| Session | Status | Steps | Duration |
|---------|--------|-------|----------|
| s1-tabs | ✅ | 7/7 | 1.47s |
| s6-guide | ✅ | 6/6 | 0.98s |
| s2-strategy-flow | ✅ | 7/7 | 0.82s |
| s3-watchlist | ✅ | 5/5 | 0.78s |
| s4-settings | ✅ | 4/4 | 0.02s |
| s5-brain-inbox | ✅ | 10/10 | 0.77s |

## Drift Findings

_No drift — observed behavior matches the docs._

## Git Diff Stat

```
frontend/src/guide.md                 | 37 ++++++++++++++++++++++++++++-------
 frontend/src/pages/Discover.jsx       |  5 ++++-
 src/swingbot/selftest/expectations.py |  5 ++---
 tests/test_selftest_sessions.py       |  4 ++--
 4 files changed, 38 insertions(+), 13 deletions(-)
```
