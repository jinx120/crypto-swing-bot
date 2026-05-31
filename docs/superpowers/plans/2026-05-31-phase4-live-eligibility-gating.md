# Phase 4 — Live-Eligibility Gating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce the live-trading safety model: in LIVE mode, only strategies explicitly toggled `live_eligible` may open new positions; armed-but-not-eligible strategies still *manage and exit* their open positions but open nothing. In PAPER mode every armed strategy trades. The global graduation gate (already enforced in `set_mode`) plus this per-strategy opt-in are the two locks before real money moves.

**Architecture:** A tiny, well-contained change in the supervisor's tick loop: each cycle, set each strategy's `Orchestrator.paused` to `supervisor.paused OR (mode == 'live' AND not live_eligible)`. The `Orchestrator` already treats `paused` as "manage open positions, open none" — exactly the desired semantics. The frontend live-eligible toggles and "paper-only" badge shipped in Phase 3; this phase makes them bite.

**Tech Stack:** Python 3.11+, pytest. Run with `.venv/bin/python -m pytest -q`.

**Reference:** Design spec `docs/superpowers/specs/2026-05-31-multi-asset-concurrent-trading-design.md` §4.4, §7 (go-live). Depends on Phases 1-3.

---

### Task 1: Supervisor enforces live-eligibility per cycle

**Files:**
- Modify: `src/swingbot/supervisor.py`
- Test: `tests/test_supervisor_live_gate.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_supervisor_live_gate.py` (reuses Phase-1 fakes):

```python
from datetime import datetime, timezone

from swingbot.profiles import ProfileStore
from swingbot.supervisor import PortfolioSupervisor
from tests.test_supervisor import FakeMarket, FakeBroker, _profile, _bars

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _sup(tmp_path, mode, eligible):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    for sym in ("BTC/USD", "ETH/USD"):
        name = sym.split("/")[0].lower()
        profiles.save(name, _profile(sym)); profiles.arm(name)
    for name in eligible:
        profiles.set_live_eligible(name, True)
    market = FakeMarket({"BTC/USD": _bars(100.0), "ETH/USD": _bars(110.0)})
    broker = FakeBroker()
    sup = PortfolioSupervisor(profiles=profiles, creds=None,
                              state_db=str(tmp_path / "s.db"), market=market,
                              broker=broker, mode=mode)
    sup.build()
    return sup, broker


def test_paper_mode_trades_all_armed_regardless_of_eligibility(tmp_path):
    sup, broker = _sup(tmp_path, mode="paper", eligible=["btc"])  # eth not eligible
    sup.tick_all(now=T0)
    assert set(broker.positions) == {"BTC/USD", "ETH/USD"}        # both trade in paper


def test_live_mode_only_eligible_strategies_open(tmp_path):
    sup, broker = _sup(tmp_path, mode="live", eligible=["btc"])    # eth armed but not eligible
    sup.tick_all(now=T0)
    assert "BTC/USD" in broker.positions
    assert "ETH/USD" not in broker.positions                      # gated out of opening


def test_live_mode_still_manages_existing_position_of_ineligible(tmp_path):
    sup, broker = _sup(tmp_path, mode="live", eligible=[])         # neither eligible
    # eth already holds a position carried in from paper; it must still be exitable
    broker.positions["ETH/USD"] = {"symbol": "ETH/USD", "qty": 5.0,
                                   "avg_entry_price": 110.0, "market_value": 550.0}
    from swingbot.types import OpenPosition, Regime, Side
    sup._store.save_position(OpenPosition(
        symbol="ETH/USD", entry_ts=T0, entry_price=110.0, qty=5.0, stop=120.0, tp=130.0,
        max_hold_until=T0, score_at_entry=0.5, regime_at_entry=Regime.UPTREND, side=Side.LONG),
        strategy="eth")
    sup.tick_all(now=T0)               # stop (120) is above price -> exit fires
    assert "ETH/USD" not in broker.positions   # ineligible position was still managed/closed
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_supervisor_live_gate.py -q`
Expected: FAIL — `test_live_mode_only_eligible_strategies_open` fails because the supervisor
currently opens positions for every armed strategy regardless of mode/eligibility.

- [ ] **Step 3: Gate per-strategy in the tick loop**

In `src/swingbot/supervisor.py`, in `tick_all`, replace this block:

```python
        for name in sorted(self._strategies):                 # deterministic priority
            s = self._strategies[name]
            if self.paused:
                s["orch"].paused = True
            try:
                s["orch"].tick(now)
            except Exception as e:                            # one bad strategy never aborts the cycle
                print(f"[supervisor] {name} tick error: {e}")
            s["snapshot"] = self._snapshot(s["profile"])
```

with:

```python
        for name in sorted(self._strategies):                 # deterministic priority
            s = self._strategies[name]
            # In LIVE mode, a strategy that is not live-eligible is paused: it still
            # manages/exits an open position but opens nothing. In PAPER mode every
            # armed strategy trades (unless the whole supervisor is paused).
            ineligible_live = (self.mode == "live"
                               and not self.profiles.is_live_eligible(name))
            s["orch"].paused = self.paused or ineligible_live
            try:
                s["orch"].tick(now)
            except Exception as e:                            # one bad strategy never aborts the cycle
                print(f"[supervisor] {name} tick error: {e}")
            s["snapshot"] = self._snapshot(s["profile"])
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_supervisor_live_gate.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Run the full backend suite (no regressions)**

Run: `.venv/bin/python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/swingbot/supervisor.py tests/test_supervisor_live_gate.py
git commit -m "feat(supervisor): enforce live-eligibility — ineligible strategies are paper-only in LIVE mode"
```

---

### Task 2: End-to-end verification of the go-live flow

No new code — confirm the two locks behave together. (Phase 3 already renders the
live-eligible toggles and the "paper-only" badge.)

**Files:** none (verification only).

- [ ] **Step 1: Confirm the graduation gate still blocks an unproven portfolio**

Run: `.venv/bin/python -m pytest tests/test_supervisor_control.py::test_set_mode_live_blocked_without_graduation -q`
Expected: PASS — `set_mode("live")` returns `(False, "go-live blocked: ...")` until the
aggregate paper record clears ≥30 trades + positive expectancy.

- [ ] **Step 2: Manual end-to-end (backend running via `swingbot-web`, creds set)**

Walk the flow and confirm each lock:
1. Arm two profiles; mark only one **live-eligible** on the Strategy tab.
2. With the portfolio in PAPER, **Start** — both cards open/manage positions (banner shows
   both under "Open").
3. Attempt **Go LIVE** before graduation — the control returns the "go-live blocked" reason
   (no mode change).
4. After the aggregate paper record graduates (or by lowering the bar only for a manual
   test), **Go LIVE** succeeds; the non-eligible card shows the **paper-only** badge and
   opens no new positions, while still managing any it already holds; the eligible card
   trades live.

- [ ] **Step 3: Commit (docs only, if you annotate anything)**

No code change. If you added notes to a runbook, commit them; otherwise skip.

---

## Self-Review Notes (for the implementer)

- **Spec coverage:** §4.4 live-eligibility skip (Task 1), §7 go-live = global gate +
  per-strategy opt-in (Task 1 enforces the opt-in; `set_mode` from Phase 2 enforces the
  global gate; Task 2 verifies both together).
- **Semantics check:** `Orchestrator.paused` blocks `_maybe_enter` only; `_manage_open`
  runs regardless — so an ineligible strategy in LIVE mode exits cleanly, which the third
  test asserts.
- **`tick_all` is authoritative** over `orch.paused` (it sets it every cycle), so
  `supervisor.resume()` toggling `orch.paused` is harmless — the next cycle recomputes the
  correct value from `self.paused` + eligibility.
- This is the final phase. After it, the full suite should be green and the dashboard
  supports concurrent multi-asset paper/live trading with portfolio-level risk.
