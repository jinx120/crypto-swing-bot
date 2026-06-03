# Sub-project C — Decision Brain: Verification Findings

**Date:** 2026-06-03
**Verified against:** live Docker container `crypto-swing-bot-swingbot-1` on :8000, rebuilt from this
branch, driving the UI with Playwright and the API with curl. LLM = real `qwen2.5` via Ollama.

This doc is for your manual review. Grouped: Works as intended / Bugs found & fixed / Known gaps /
Future improvements.

## Works as intended

- **Brain page renders** with zero console errors: header (Recommend now + Autonomous + Auto-after-
  discovery toggles), proposals inbox, Model & connection config, Discord webhook, Issues feed.
- **Happy-path recommend with real qwen2.5** (~12s inference): a recommend run produced a coherent,
  guardrail-**approved** proposal — `disarm {"name": "aggressive"}`, confidence 100%, rationale
  *"No eligible candidates available, disarming aggressive strategy to reduce risk."* The full
  pipeline (context → Ollama → parse → guardrail → store → surface in UI) works end-to-end.
- **Graceful Ollama failure**: pointing `brain_ollama_url` at an unreachable address logged
  `[ollama_error] ollama transport: <urlopen error [Errno 111] Connection refused>` to the issues
  feed; `/api/state` stayed healthy (HTTP 200). A brain failure never touches trading.
- **Config fields** (model / Ollama URL / confidence threshold / timeout) render, reflect persisted
  settings, and save on blur via `PUT /api/portfolio/settings`.
- **Dismiss flow** (UI): proposal status → `dismissed`; the live "aggressive" strategy remained
  armed — Dismiss has no trading side effect, as designed.
- **Backend suite**: `288 passed, 5 skipped` (was 250; +38 new brain tests). Frontend `npm run build`
  clean.

## Bugs found & fixed during the build

- **Apply didn't record source** — an autonomously-applied proposal kept `source="manual"`. Fixed by
  letting `ProposalStore.mark()` accept and persist `source`; `brain.apply()` now passes it. (Caught
  by `test_autonomous_applies_approved_above_threshold`.)
- **Brain config not exposed in UI** — the plan's Brain page shipped only the toggles + webhook, but
  you explicitly wanted the model adjustable from the UI. Added Model / Ollama URL / confidence /
  timeout fields to the Brain page before verifying.

## Known gaps / environment notes (need your attention)

- **Docker → host Ollama networking.** Inside the container, `localhost:11434` (the default
  `brain_ollama_url`) is **unreachable**; so is `host.docker.internal`. Only the bridge gateway
  **`http://172.17.0.1:11434`** works. I set the running instance to that value (persisted in
  `swingbot.db`), so the brain works now — but the **code default is wrong for Docker**. Options to
  consider: default to the gateway, add an `OLLAMA_URL` env var in `docker-compose.yml`, or add
  `extra_hosts: ["host.docker.internal:host-gateway"]` to the compose service and default to that.
- **Zero eligible candidates right now.** Discovery returned 8 rows but 0 `eligible_now` (none clear
  `good_history` + regime), so the brain had no arm candidates to choose from. This is the known
  ~5-day candle-history bottleneck, **not** a brain defect — once the archive backfill deepens, the
  arm path will have real candidates. The brain handled the empty case sensibly (proposed a disarm).
- **Live Apply / autonomous auto-apply not exercised against the live bot.** The only live proposal
  was a `disarm` of a running paper strategy; applying it (or enabling autonomous) would mutate your
  live config purely for a test, so I left it. These paths are covered by automated tests
  (`test_apply_and_dismiss`, `test_apply_disarm_path`, `test_autonomous_applies_approved_above_threshold`).
- **Discord delivery not exercised end-to-end** (no real webhook configured). Payload shape + the
  swallow-on-failure behavior are covered by `tests/test_notify.py`.

## Future improvements (room for later)

- Fix the Docker Ollama-URL default (above) so it works out of the box.
- Show a spinner / live status while a recommend run is in flight (currently a fixed ~1.8s delay
  before refresh; a long qwen inference can outlast it, so the user may need to reopen the tab).
- Poll proposals/issues while a run is computing instead of a single delayed refresh.
- Surface the `source` and `applied_at` of applied proposals in the inbox for an audit trail.
- A "Send summary now" button wired to `POST /api/brain/summary` (endpoint exists; UI button doesn't).
- Confidence-threshold and autonomous-mode interactions deserve an explicit on-screen explainer.
- Consider re-running guardrails at apply time against fresh discovery (currently apply re-dispatches
  but trusts the stored guardrail verdict; the supervisor's own `check_can_enter` remains the hard
  gate at actual entry).
