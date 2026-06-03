# Sub-project D — Self-test Gate + LLM Improvement Proposals — Design

**Date:** 2026-06-03
**Status:** Approved (design). Depends on A (UI + Playwright smoke), B1/B2 (archive + discovery),
and C (decision brain) — all DONE.
**Roadmap ref:** `docs/superpowers/specs/2026-06-02-platform-improvement-roadmap-design.md` §D.

## Goal

Add a scheduled **self-test runner** that (1) proves the app is healthy with deterministic checks,
(2) actively drives the **real running website with Playwright** to surface errors and rough edges,
and (3) **only when fully green**, has the local LLM turn those findings plus recent diffs into
**actionable improvement proposals**. Deterministic + UI health **gates** the LLM: a red run never
reaches the model. Green runs feed structured findings to the brain, whose proposals land in the
existing Sub-project C inbox (recommend-only, guardrailed).

Invoked as a standalone CLI — `python -m swingbot.selftest` — scheduled via the `/loop` or
`/schedule` skill. It runs decoupled from the live trading web process.

## Decisions (locked with user)

- **Gate-first, locked from roadmap:** deterministic checks + UI probe must be green before any LLM
  call. Red → write report, Discord ping, **skip the LLM**, exit non-zero.
- **Deterministic checks:** `pytest -q`, `ruff check`, and `cd frontend && npm run build`.
- **UI test is a real headless Playwright run** (not an HTTP ping) against the running `:8000`
  container. Python Playwright (`pytest-playwright` / the `playwright` package) so it lives in the
  same toolchain as the runner. Captures **console errors/warnings, failed & 4xx/5xx network
  requests, uncaught page exceptions, and a full-page screenshot** per route.
- **Health output:** overwrite `docs/SELFTEST_REPORT.md` with the latest full run; append a one-line
  dated GREEN/RED summary to `DEVLOG.md`. (Keeps DEVLOG from bloating under scheduling.)
- **LLM proposals reuse C's `ProposalStore` inbox:** structured `Proposal` objects, run through C's
  guardrails, surfaced on the Brain page. A text digest is also written into the report.
- **Recommend-only:** D never auto-applies. Proposals always land in the inbox for the user, even if
  C's `autonomous_mode` is ON elsewhere (self-test proposals are advisory, not trade actions).
- **Model:** local Ollama, default **`qwen3.5:9b` (Q4_K_M)**, reusing `decision/ollama.py`
  (`OllamaClient.generate_json`, strict JSON schema, never raises). Model + URL + timeout are
  **configurable, never hardcoded** — same pattern as C.
- **Tests stay offline:** unit tests inject fakes for subprocess, Playwright page, and Ollama. No
  real browser/LLM/GPU in the suite. One opt-in integration test (skip-by-default) drives a real
  served instance.

## Current state (grounded in code)

- `decision/ollama.py` → `OllamaClient.generate_json(prompt, schema) -> OllamaResult`; never raises
  (connection/timeout/non-JSON → `ok=False`). This is D's LLM transport, unchanged.
- `decision/proposals.py` → `Proposal` dataclass, `make_proposal(...)`, `ProposalStore` (atomic JSON
  inbox surfaced at `/api/brain/*` and the Brain page), `IssueLog`. D emits `Proposal`s here.
- `decision/guardrails.py` → the gate C runs proposals through before they're applicable. D reuses it
  to stamp `guardrail_status` on its proposals.
- `notify.py` → `DiscordNotifier.send(event_type, payload) -> bool`. D pings on RED and on
  proposals-ready.
- No committed Playwright test exists — Sub-project A was Playwright-*verified* live via the MCP
  plugin, which a headless scheduler cannot call. D introduces the first **scripted** Playwright
  probe as a reusable artifact.
- The app runs in Docker (`crypto-swing-bot-swingbot-1` on `:8000`). The probe targets the already-
  running container; the deterministic checks run on the host workspace.

## Architecture

New package `src/swingbot/selftest/`, each unit one clear purpose, tested in isolation:

```
selftest/
  __init__.py
  __main__.py     # CLI entry: python -m swingbot.selftest [--base-url ...] [--no-llm]
  checks.py       # deterministic check wrappers -> CheckResult
  uiprobe.py      # Playwright probe -> list[UIFinding] + screenshots
  report.py       # SELFTEST_REPORT.md writer + DEVLOG.md one-liner
  llm.py          # build prompt from health+findings+diffstat -> Proposals via OllamaClient
  runner.py       # orchestration + gate decision (the brain of D)
```

### Data shapes

- `CheckResult{ name, ok, duration_s, key_output }` — one per deterministic step.
- `UIFinding{ route, severity (fatal|warn|info), kind (console|network|exception|layout),
  detail, screenshot_path }`. `fatal` = page threw, navigation failed, or a request returned 5xx.
- `HealthSummary{ green: bool, checks: list[CheckResult], ui_findings: list[UIFinding],
  started_at, duration_s, diffstat: str }`.

### Pipeline (`runner.run()`)

1. **Deterministic gate** (`checks.py`, host workspace, sequential): run `pytest -q`, `ruff check`,
   `npm run build` via an injected subprocess runner; each → `CheckResult` (truncated key output).
2. **Live UI probe** (`uiprobe.py`): launch headless Chromium, visit each main route
   (Dashboard `/`, Discover, Brain). For each, attach listeners for `console`, `pageerror`, and
   failed/`response>=400` events; take a screenshot to `docs/selftest-artifacts/<route>.png`.
   Emit `UIFinding`s.
3. **Gate decision** (`runner.py`): `green = all(c.ok for checks) and not any(f.severity=="fatal")`.
   - **RED:** `report.write(...)`, `notify.send("selftest_red", summary)`, **skip LLM**, exit `1`.
   - **GREEN:** continue to step 4.
4. **LLM proposal pass** (`llm.py`, green only, skippable via `--no-llm`): build a prompt from the
   `HealthSummary` (deterministic outputs + UI findings incl. console errors + screenshot paths + the
   `git diff --stat` of recent changes), call `OllamaClient.generate_json` with a fixed proposal
   schema. Map each returned item to a `Proposal` (`action` ∈ `tune` | `ui_fix` | `portfolio_settings`),
   stamp via `guardrails`, `ProposalStore.add_many(...)`. `notify.send("selftest_proposals", ...)`.
   Ollama down → record in report, still exit `0` (green run, LLM is best-effort).
5. **Report** (`report.py`): overwrite `docs/SELFTEST_REPORT.md` (deterministic table, UI findings
   table with screenshot links, proposal digest, timestamps); append one dated GREEN/RED line to
   `DEVLOG.md`.

### New action type

C's `Proposal.action` gains a `ui_fix` variant (target = `{route, issue}`), so Playwright-surfaced
UI problems become first-class, reviewable inbox items alongside trading proposals. Guardrails treat
`ui_fix` as always-recommend-only (never auto-applied).

## Error handling

- Every external call is defensive: `checks.py` captures non-zero exits as `ok=False` (never throws),
  `uiprobe.py` wraps navigation in try/except → a `fatal` `UIFinding` rather than a crash, `llm.py`
  inherits `OllamaClient`'s never-raise contract.
- A crash in the runner itself still writes a RED report and pings Discord (top-level try/finally).
- Exit codes: `0` green (LLM ran or was cleanly skipped), `1` red, `2` runner-internal error.

## Testing

- `checks.py`: fake subprocess runner returning canned (rc, stdout) → assert `CheckResult` mapping,
  truncation, and that a non-zero rc yields `ok=False`.
- `uiprobe.py`: fake Playwright page emitting recorded console/pageerror/response events → assert
  `UIFinding` severities and that a navigation exception becomes one `fatal` finding.
- `llm.py`: fake `OllamaClient` returning a fixed schema-valid payload → assert correct `Proposal`
  objects and that `ok=False` yields zero proposals (no crash).
- `runner.py`: inject fake checks+probe+llm; table-test the gate — all-green→LLM called; any fatal
  finding→LLM skipped + exit 1; failing check→LLM skipped + exit 1.
- `report.py`: write to a tmp path, assert report contents + single DEVLOG line appended.
- One opt-in `@pytest.mark.integration` test drives a real served instance + real Ollama, skipped by
  default (no browser/GPU in CI).
- Acceptance: `.venv/bin/python -m pytest -q` stays green; new tests included in the count.

## Scheduling

`python -m swingbot.selftest` is the unit of scheduling. The user wires it via `/loop` (e.g. nightly)
or `/schedule`. The runner is idempotent and writes only report/inbox artifacts — safe to repeat.

## Out of scope (YAGNI)

- No auto-apply of self-test proposals (recommend-only, locked).
- No new web endpoints — proposals surface through C's existing `/api/brain/*` + Brain page.
- No multi-browser matrix — headless Chromium only.
- No historical report retention beyond the latest file + the DEVLOG one-liners.
