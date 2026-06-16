# Phase 6 — Live Acceptance Runbook (real Alpaca paper)

> **OPT-IN, real-money-adjacent.** This drives the live container against a **real Alpaca
> paper account**. Run only against paper. Probe steps place a real (paper) order. Back up
> first (step 1). Fill the **Observed** and **Result** columns as you go; this file is the
> recorded acceptance evidence referenced by `docs/ROADMAP_STATUS.md`.

**Preconditions**
- Container builds/runs on `:8000` (`docker compose build swingbot && docker compose up -d swingbot`;
  if the daemon lacks `runtime: nvidia`, use a temporary `runtime: runc` override, not committed).
- Real Alpaca **paper** credentials are configured in `~/.swingbot/credentials.json`.
- `TOKEN=$(cat ~/.swingbot/token)` for authenticated calls.
- Helper: `Q() { curl -fsS -H "Authorization: Bearer $TOKEN" "http://localhost:8000$1"; }`

| # | Spec step | Command(s) | Pass check | Observed | Result |
|---|-----------|------------|-----------|----------|--------|
| 1 | Back up data dir | `scripts/backup-data-dir.sh` | Prints a new `swingbot-data-<stamp>.tar.gz`; file exists | | |
| 2 | Start from managed-canvas/probe config | Set `SWINGBOT_ENABLE_PAPER_PROBE=1` in the compose env; `docker compose up -d swingbot` | `Q /api/strategies` lists `btc_trend`,`eth_trend` (kind=strategy) and `paper_probe` (kind=probe) | | |
| 3 | Rebuild/restart **without** pressing Start | (ensure desire already true from a prior Start, or press Start once, then) `docker compose build swingbot && docker compose up -d swingbot` | `Q /api/control/lifecycle` → `running_desired:true`, `running_actual:true`, `startup_error:null` (no Start press this boot) | | |
| 4 | Verify desired/actual, fresh bars, cycles, decisions | `Q /api/health/trading` | `status` ∈ {active,unhealthy}; `last_cycle.bar_ts` is a recent closed bar; `last_decisions_by_strategy` has a code+reason per armed strategy; `reliability` shows sample counts + window | | |
| 5 | Probe: confirmed fill, durable position, marker, chart marker | watch `Q /api/state` until the probe enters; cross-check Alpaca paper dashboard | `paper_probe` shows a broker-confirmed `position` (qty>0); `probe_complete:true`; an entry marker renders on the probe chart in the UI; position survives a page reload | | |
| 6 | Restart → no duplicate probe/order, position managed | `docker compose up -d swingbot` (recreate); `Q /api/state` | No second probe order on the Alpaca paper account; probe `probe_complete` still true; any open position still present and managed | | |
| 7 | Credential/network failure → UI stays available, truthful, no false-flat | `mv ~/.swingbot/credentials.json ~/.swingbot/credentials.json.bak` then `docker compose up -d swingbot`; `Q /api/health/ready`; `Q /api/state`; then restore: `mv ~/.swingbot/credentials.json.bak ~/.swingbot/credentials.json && docker compose up -d swingbot` | UI/endpoints still respond (no 500 storm); `/api/health/ready` → not ready with a credentials/reconcile reason; previously-open positions are **not** cleared to flat; **no** duplicate orders appear on Alpaca | | |

**Post-run**
- Restore credentials and confirm `running_actual:true`, `startup_error:null` again.
- Decide whether to leave the probe enabled or set `SWINGBOT_ENABLE_PAPER_PROBE` back to unset.
- Record overall PASS/FAIL and the date below.

**Acceptance result:** _<PASS/FAIL — date — operator>_
