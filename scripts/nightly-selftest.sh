#!/usr/bin/env bash
# Nightly usage-agent / self-test gate run — invoked by cron (see crontab).
#
# Drives the live swingbot container (:8000), spawns an ephemeral app (:8001),
# and runs the Playwright usage sessions S1–S6. Writes docs/SELFTEST_REPORT.md,
# prepends a DEVLOG line, and files any drift findings into the brain inbox
# (visible on the Health tab). See docs/ROADMAP_STATUS.md — Sub-project E.
#
# Exit: 0 green, 1 red (gate/session failure or drift infra), 2 runner crash.
set -uo pipefail

# cron runs with a minimal PATH; the npm-build gate check needs node/npm.
# (If node is upgraded via nvm, update this path to the new version dir.)
export PATH="/home/redji/.nvm/versions/node/v24.16.0/bin:/usr/local/bin:/usr/bin:/bin"

cd /home/redji/crypto-swing-bot || exit 1

echo "===== nightly selftest start $(date -u +%Y-%m-%dT%H:%M:%SZ) ====="
.venv/bin/python -m swingbot.selftest --no-llm
rc=$?
echo "===== nightly selftest exit ${rc} $(date -u +%Y-%m-%dT%H:%M:%SZ) ====="
exit "$rc"
