# Sub-project C — Ollama Decision Brain — Design

**Date:** 2026-06-04
**Status:** Approved (design). Depends on B1 (archive) + B2 (auto-strategy discovery), both DONE.
**Roadmap ref:** `docs/superpowers/specs/2026-06-02-platform-improvement-roadmap-design.md` §C.

## Goal

Add a local-LLM **decision brain** that turns B2's ranked discovery output plus live portfolio
context into structured, guardrailed **proposals** — arm / disarm / tune / portfolio-settings
actions. Default behavior is **recommend-only**: proposals land in a persistent inbox the user
reviews and applies. An opt-in `autonomous_mode` (default OFF) auto-applies any proposal that
passes guardrails and clears a confidence threshold. A Discord webhook surfaces activity, and the
brain records its own limitations to a runtime "issues" feed.

The LLM is local **Ollama** (`qwen2.5` by default, reachable at `localhost:11434`). The model and
connection are **configurable, never hardcoded**.

## Decisions (locked with user)

- **Action scope:** everything — `arm`, `disarm`, `tune`, `portfolio_settings`.
- **Triggers:** all three — UI button, opt-in automatic (after a discovery sweep), and a persistent
  "save for later" inbox.
- **Autonomy:** ship the toggle now, default OFF. When ON it applies to **all** proposal types
  (no per-type carve-out); guardrails + confidence threshold are the only gate.
- **Model:** configurable setting (default `qwen2.5`), with `ollama_url`, `confidence_threshold`,
  `timeout_s` alongside it. No hardcoded model name.
- **Tests stay offline:** the Ollama client is mocked in the suite (deterministic, no network/GPU).
  Real Ollama is exercised only during the Playwright verification pass.
- **Discord pings:** new proposals ready, autonomous applies, blocks & errors, daily/periodic summary.
- **Shortcomings:** two artifacts — (1) a runtime issues feed the brain writes to; (2) a dev-time
  findings doc produced while driving the live site with Playwright "as the user would".

## Current state (grounded in code)

- `discovery.py` → `DiscoveryEngine.sweep` emits ranked rows per `{symbol, archetype}` with
  `metrics`, `eligible_now`, `fires_now`, `regime`, `profile`. This is the brain's primary input.
  Cached via `discovery.load_cache` / `save_cache` (atomic JSON) and surfaced on `app.state.discovery`.
- `web.py:discovery_arm` is the canonical apply path: `archetype_profile(...)` → `profiles.save` →
  `profiles.arm` → `profiles.set_live_eligible(True)` → `controller.reload()`.
- `portfolio_risk.py:PortfolioRiskManager.check_can_enter` is the entry guardrail (kill switch,
  `max_concurrent`, deployed-cap). `PortfolioSettings` = `max_concurrent`, `max_total_deployed_frac`,
  `portfolio_daily_loss_limit_pct`.
- Portfolio settings persist via `profiles.get_portfolio_settings` / `set_portfolio_settings`
  (`web.py` GET/PUT `/api/portfolio/settings`). Secrets persist via `CredentialStore`.
- `/api/state` holds open positions; `profiles.list()` / `armed_with_flags()` track armed strategies.
- Ollama live: `qwen2.5:latest` (7.6B Q4) at `localhost:11434`. No existing LLM code.

---

## Architecture

A small `decision/` package of independently testable units, plus a `notify.py`. Each unit answers
"what does it do / how do you use it / what does it depend on" in isolation:

| Unit | Responsibility | Depends on |
|------|----------------|------------|
| `decision/ollama.py` | HTTP client to Ollama; schema-constrained JSON; hard timeout; **never raises** | stdlib http only |
| `decision/prompt.py` | Build prompt from discovery rows + portfolio context; parse + validate model JSON → typed `Proposal`s | `types` |
| `decision/guardrails.py` | Validate each proposal against reality; pure, no IO | `portfolio_risk`, `presets`, `backtest` |
| `decision/proposals.py` | Persistent proposal inbox (JSON store) + status lifecycle | stdlib only |
| `decision/brain.py` | Orchestrates: gather context → ollama → parse → guardrail → store → notify | the four units above, `notify` |
| `notify.py` | Discord webhook sender; async, failure-tolerant | stdlib http only |

**Threading & safety:** every brain run executes on a **background thread** (same pattern as
`discovery_refresh`). The trading loop is never blocked and a brain failure can never abort trading.
Ollama unreachable / timeout / invalid JSON → the run records a structured error to the issues feed
and pings Discord; it does not raise.

### `decision/ollama.py`

```python
class OllamaClient:
    def __init__(self, url: str, model: str, timeout_s: float): ...
    def generate_json(self, prompt: str, schema: dict) -> OllamaResult: ...
    # OllamaResult: { ok: bool, data: dict | None, error: str | None }
```

- POSTs to `{url}/api/generate` with `format=<schema>` (Ollama schema-constrained JSON) and
  `stream=false`. Wraps all of: connection error, timeout, non-200, and `json.loads` failure into
  `OllamaResult(ok=False, error=...)`. **No exceptions escape.**
- `url`, `model`, `timeout_s` are injected — never literals in the module.

### Proposal model (`types.py` addition)

```python
@dataclass
class Proposal:
    id: str                # stable hash of (action, target) for dedupe within a run
    created_at: int
    action: str            # "arm" | "disarm" | "tune" | "portfolio_settings"
    target: dict           # arm/tune: {symbol, archetype, [params]}; disarm: {name};
                           # portfolio_settings: {max_concurrent?, max_total_deployed_frac?, ...}
    rationale: str         # model's free-text justification
    confidence: float      # 0..1, from the model, clamped
    guardrail_status: str  # "approved" | "blocked"
    guardrail_reason: str  # "" when approved
    status: str            # "pending" | "applied" | "dismissed" | "superseded"
    applied_at: int | None
    source: str            # "manual" | "auto-after-discovery" | "autonomous"
```

### Guardrails (`decision/guardrails.py`) — the safety core

Each proposal is gated before it is ever applicable. Blocked proposals are **kept** in the inbox
(shown greyed with the reason) so the user sees what the brain *wanted* to do.

- **arm** — target must match a current `eligible_now` discovery row, **and**
  `PortfolioRiskManager.check_can_enter(...)` must approve (kill switch off, under `max_concurrent`,
  within deployed cap). Else `blocked`.
- **disarm** — `target.name` must currently be armed. Else `blocked`.
- **tune** — every changed param must fall inside a bounded per-field range (clamps derived from
  the archetype/preset definition), **and** a re-backtest of the tuned profile must still pass
  `discovery.good_history(...)`. Else `blocked`. (The LLM cannot silently degrade a strategy.)
- **portfolio_settings** — each field clamped to a safe range:
  `max_concurrent ∈ [1, HARD_MAX]`, `max_total_deployed_frac ≤ 0.90`,
  `portfolio_daily_loss_limit_pct ∈ (0, 0.20]`. Out-of-range → `blocked`.

### Apply path (`decision/brain.py` → reuses existing primitives)

- **arm** → `archetype_profile` → `profiles.save` → `profiles.arm` → `set_live_eligible(True)` →
  `controller.reload()` (identical to `discovery_arm`).
- **disarm** → `controller.flatten(name)` → `profiles.disarm(name)` → `controller.reload()`.
- **tune** → `profiles.save(name, tuned_profile)` → `controller.reload()`.
- **portfolio_settings** → `profiles.set_portfolio_settings(patch)` → `controller.reload()`.

Applying flips proposal `status` to `applied`, stamps `applied_at`, and pings Discord.

### Autonomy

`autonomous_mode` (bool, default **OFF**) in portfolio settings. After a run, for every proposal
with `guardrail_status == "approved"` **and** `confidence >= confidence_threshold`, the brain
auto-applies it (`source="autonomous"`) and pings Discord per apply. Applies to **all** action
types — no carve-out. With the toggle OFF, nothing is applied automatically (pure recommend-only).

### Triggers

1. **UI button** — `POST /api/brain/recommend` spawns a background run, stores proposals.
2. **Automatic** — opt-in setting `auto_recommend` (default OFF): when a discovery sweep finishes
   (`discovery_refresh` job completion), kick a recommend run on the background thread.
3. **Save for later** — proposals persist in the inbox until applied/dismissed. A new run marks any
   still-`pending` proposals from the previous run as `superseded`.

### Notifications & issues feed

- **`notify.py`** — `discord(event_type, payload)` POSTs a compact embed to the configured webhook.
  Failure-tolerant: a webhook error is swallowed (logged), never touches trading. Events:
  `proposals_ready`, `autonomous_apply`, `blocked_or_error`, `daily_summary`.
- **Runtime issues feed** — the brain appends limitation records (low-confidence proposals dropped,
  Ollama timeout/parse failure, blocked applies, "no eligible candidates / data gap") to a JSON
  store surfaced at `GET /api/brain/issues`. This feed is the source for the `blocked_or_error`
  Discord ping. The `daily_summary` ping rolls up counts (proposals, applies, blocks, issues).

## Configuration

Non-secret brain config is added to **portfolio settings** (existing GET/PUT `/api/portfolio/settings`):

| Field | Default | Notes |
|-------|---------|-------|
| `model` | `"qwen2.5"` | swappable; never hardcoded |
| `ollama_url` | `"http://localhost:11434"` | |
| `confidence_threshold` | `0.7` | autonomous-apply gate |
| `timeout_s` | `30` | per Ollama call |
| `autonomous_mode` | `false` | full autonomy when ON |
| `auto_recommend` | `false` | run after each discovery sweep |

The **Discord webhook URL** is a secret → stored via `CredentialStore` (set-only; never returned in
plaintext from GET, mirroring `has_secret`).

## Endpoints (`web.py`)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/brain/recommend` | start a background recommend run |
| GET | `/api/brain/proposals` | the inbox (pending + recent applied/blocked/superseded) |
| POST | `/api/brain/proposals/{id}/apply` | apply one (guardrail re-checked at apply time) |
| POST | `/api/brain/proposals/{id}/dismiss` | mark dismissed |
| GET | `/api/brain/issues` | runtime shortcomings feed |

Write endpoints use the existing `require_token` dependency. Webhook URL + brain config flow through
the existing credentials / portfolio-settings endpoints.

## Frontend

A new **Brain** page (nav entry + `Brain.jsx`, following the `Discover.jsx` pattern):

- **"Recommend now"** button → `POST /api/brain/recommend`, polls `/api/brain/proposals`.
- **Proposals inbox** — each card shows action, target, rationale, confidence; **Apply** / **Dismiss**
  buttons. Blocked proposals greyed with the reason. Applied/superseded shown muted.
- **Toggles** — `autonomous_mode` and `auto_recommend` (wired to portfolio settings PUT).
- **Brain config** — model / ollama_url / confidence_threshold / timeout_s fields; Discord webhook
  URL field (write-only).
- **Issues feed** — list from `/api/brain/issues`.

## Testing

- **Unit (offline, deterministic — Ollama mocked):**
  - `ollama.py`: connection error / timeout / non-200 / bad-JSON all yield `ok=False` (monkeypatched
    transport); valid response yields parsed `data`.
  - `prompt.py`: prompt includes discovery + portfolio context; parser drops malformed proposals and
    clamps confidence.
  - `guardrails.py`: each action type — an approved case and a blocked case (over max_concurrent,
    disarm-unarmed, tune out-of-bounds, tune-fails-backtest, settings clamp).
  - `proposals.py`: persistence round-trip; lifecycle transitions; supersede-on-new-run.
  - `brain.py`: end-to-end with a fake `OllamaClient` and fake `profiles`/`controller` — recommend
    produces stored proposals; apply hits the right primitive; autonomous applies only approved +
    above-threshold; failures land in the issues feed.
  - `notify.py`: webhook payload shape; swallowed failure.
  - web endpoints: each returns expected shape; auth enforced on writes.
- **Suite gate:** `.venv/bin/python -m pytest -q` green (expect prior `250 passed, 5 skipped` plus
  the new brain tests). `cd frontend && npm run build`.

## Verification (Playwright, real Ollama)

Drive the live containerized site *as the user would* and write findings to
`docs/SUBPROJECT_C_FINDINGS.md`:

1. Open Brain page → click **Recommend now** → confirm proposals render with rationale + confidence.
2. **Apply** an `arm` proposal → confirm the strategy appears armed on the Strategy/Dashboard view.
3. **Dismiss** a proposal → confirm it leaves the pending list.
4. Toggle **autonomous_mode** ON, trigger a run → confirm approved+high-confidence proposals
   auto-apply and the issues feed / Discord receive the expected events (webhook to a test URL).
5. Confirm blocked proposals show greyed with a reason; confirm changing `model` to a bogus value
   surfaces an issue rather than crashing.
6. Record any UX gaps, rough edges, or room-for-improvement in the findings doc for manual review.

> Container note: a rebuild (`docker compose build swingbot && docker compose up -d swingbot`)
> interrupts the live paper-trading bot — get user consent before restarting.

## Out of scope (deferred)

- Scheduled/cron self-testing and LLM-authored improvement proposals to the devlog — that's
  **Sub-project D** (reuses the issues feed + notify here).
- Streaming/token-by-token LLM UX; multi-model ensembles; fine-tuning.
- Non-Discord notification channels.

## Sequencing within the plan

1. `decision/ollama.py` + `notify.py` (leaf utilities, mocked tests).
2. `types.Proposal` + `decision/proposals.py` (inbox).
3. `decision/prompt.py` (build + parse).
4. `decision/guardrails.py` (all four action types).
5. `decision/brain.py` (orchestrate + apply + autonomous).
6. Config plumbing (portfolio settings + credentials webhook).
7. Web endpoints.
8. Frontend Brain page.
9. Wire brain into `webmain.py` startup; auto_recommend hook on discovery completion.
10. Playwright verification + findings doc + DEVLOG + ROADMAP_STATUS update.
