# Self-test Report

**Run:** 2026-06-13 03:12:01 UTC  |  **Status:** 🟢 GREEN  |  **Duration:** 45.29s

## Deterministic Checks

| Check | Status | Duration | Output |
|-------|--------|----------|--------|
| pytest | ✅ | 14.35s | warnings.warn(  # deprecated in 14.0 - 2024-11-09  .venv/lib/python3.12/site-packages/fastapi/testclient.py:1   /home/re |
| ruff | ✅ | 0.04s | All checks passed! |
| npm-build | ✅ | 3.4s | > swingbot-frontend@0.1.0 build > vite build  vite v5.4.21 building for production... transforming... ✓ 61 modules trans |

## UI Probe Findings

_No UI findings._

## Usage Sessions

| Session | Status | Steps | Duration |
|---------|--------|-------|----------|
| s1-tabs | ✅ | 7/7 | 1.55s |
| s6-guide | ✅ | 6/6 | 1.14s |
| s2-strategy-flow | ✅ | 7/7 | 0.85s |
| s3-watchlist | ✅ | 5/5 | 0.84s |
| s4-settings | ✅ | 4/4 | 0.03s |
| s5-brain-inbox | ✅ | 10/10 | 0.82s |

## Drift Findings

_No drift — observed behavior matches the docs._

## Git Diff Stat

```
docs/ROADMAP_STATUS.md | 6 +++---
 1 file changed, 3 insertions(+), 3 deletions(-)
```
