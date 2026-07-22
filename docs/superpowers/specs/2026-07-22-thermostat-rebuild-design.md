# Thermostat Rebuild — Design Spec
**Date:** 2026-07-22  
**Status:** Approved — ready for implementation planning  
**Supersedes:** All prior UI/strategy/advisor design docs. This is the new north star.

---

## 1. Product Vision

A crypto trading bot that works like a thermostat. The user sets two things:
- **Which coins to trade**
- **How much risk to take**

Everything else — strategy selection, parameter tuning, position sizing, drawdown response, regime detection — is automated and invisible. The user opens the app and sees P&L. That's the product.

**The core principle:** all complexity lives in the engine room. Nothing that requires trading knowledge is exposed to the user.

**Target user:** The builder themselves — someone who understands the code and wants to own the automation, but does not want to manually tune trading parameters when using the product.

---

## 2. Why the Prior Foundation Was Wrong

The project was built for a quant who wants to tune. Entry thresholds, regime gates, confluence scores, rebalance settings, LLM advisor toggles — all exposed to the user. That is a cockpit, not a thermostat. The new design inverts this: the intelligence is in the engine room, the UI surface area is minimal.

The prior signal direction (Kronos on 15m) also showed no edge in backtesting (156k bars, 0 cost floor). The new design expands signal research to three candidate types with better-documented edge potential: higher-timeframe trend (4h EMA), funding rate mean-reversion, and on-chain exchange flows.

---

## 3. What We Keep / Replace / Add / Remove

### KEEP (backend infrastructure is sound)
- FastAPI backend, all SQLite stores (ProfileStore, TelemetryStore, StateStore, etc.)
- Alpaca broker integration + Coinbase data feed
- Kronos signal engine + GPU runtime on swingbot VM
- Docker setup + Tailscale public endpoint
- Core trading loop: orchestrator, strategy profiles, position management, telemetry

### REPLACE
- React frontend → new thermostat UI (3 screens, 2 user controls)
- LLM advisor → internal AutoTuner (not user-facing)
- Gates & Parameters panel → hidden, auto-managed by RiskProfile
- Rebalance panel → auto-managed
- Researched presets gallery → user never sees strategies

### ADD
- `RiskProfile` abstraction: Conservative / Moderate / Aggressive → maps to full internal param sets
- `AutoTuner` service: monitors drawdown, tightens/relaxes params within risk profile bounds automatically
- Signal research layer: 4h EMA trend, funding rate mean-reversion, on-chain inflow signals (in `lab/` first, promoted when walk-forward validated)
- Signal fusion: regime-aware selection of which signal(s) to use per asset

### REMOVE
- All user-facing strategy parameter editing
- Regime gate configuration UI
- Manual rebalance controls
- Usage Agent / selftest subsystem
- Decision journal complexity (keep simple recent-activity feed only)
- All "researched strategies" UI (VWAP, EMA presets, badges, etc.)

---

## 4. The Three Screens

### Screen 1 — Home
The only screen the user needs on a daily basis.

```
● Running                    [Stop]

Portfolio
$10,842.33   +$342 (+3.2%)
[24h]  [7d]  [30d]

Open Positions
BTC   0.12    $8,204   +1.8%
ETH   0.45    $1,821   -0.4%

Recent Activity
BTC   SELL   +$84    2h ago
ETH   BUY    —       5h ago
SOL   SELL   -$12    yesterday

[Home]  [Coins]  [Settings]
```

- No signal scores, no decision codes, no regime labels
- If AutoTuner is in defensive mode: small status note — *"Defensive mode — recovering from recent losses."* No numbers, no explanation required
- P&L tabs (24h / 7d / 30d) show realized + unrealized

### Screen 2 — Coins
The two user controls live here.

```
Trading

● BTC/USD                   [×]
● ETH/USD                   [×]
○ SOL/USD  (paused)         [×]

[+ Add coin]

Risk Level
○ Conservative
● Moderate
○ Aggressive
```

- **Add coin:** user types a symbol → system creates a strategy profile, sizes the position within the current risk level, starts trading. No other input required.
- **Remove coin:** flattens any open position, stops trading that asset.
- **Risk level change:** system adjusts all internal params automatically, no restart required. Change takes effect on the next decision cycle.

### Screen 3 — Settings
One-time setup. Rarely visited.

```
Broker
Alpaca Paper   ● Connected
[Update credentials]

Mode
○ Paper trading
● Live trading

Notifications (optional)
○ Trade alerts
○ Drawdown warnings
```

- No strategy settings. No thresholds. No gates.
- Broker credentials update takes effect without rebuild (existing hot-swap mechanism).

---

## 5. The Automation Layer (Engine Room)

### 5a. RiskProfile

Three named profiles map to full internal parameter sets. The user picks the name; they never see the numbers.

| Parameter | Conservative | Moderate | Aggressive |
|-----------|-------------|----------|------------|
| `max_position_frac` | 0.05 | 0.10 | 0.20 |
| `entry_threshold` | 0.70 | 0.50 | 0.30 |
| `tp_pct` | 0.8% | 1.2% | 2.0% |
| `sl_pct` | -0.5% | -0.8% | -1.5% |
| `max_open_positions` | 1 | 2 | 4 |
| `drawdown_sensitivity` | HIGH | MEDIUM | LOW |
| `cooldown_minutes` | 60 | 30 | 0 |

These are starting values; the AutoTuner adjusts within bounds relative to the chosen profile.

### 5b. AutoTuner

Watches portfolio drawdown and adjusts params automatically. Replaces all manual breaker configuration.

**Triggers:**
- Portfolio drawdown > 3% in 24h → shift to one tier more conservative (Moderate → Conservative floor)
- Portfolio drawdown > 8% in 7d → suspend new entries, hold existing positions only
- Recovery: if drawdown recovers below 1% → gradually relax back to baseline over 48h

**What changes automatically on tighten:**
- `max_position_frac` reduced 30%
- `entry_threshold` raised 20%
- `max_open_positions` reduced by 1 (floor: 1)

**User-visible surface:** one status line on the Home screen when active. No config required.

### 5c. Coin Onboarding (automated)

When user adds a coin:
1. System checks if a strategy profile exists for that asset → creates one if not
2. Applies current RiskProfile param set
3. Starts trading on next decision cycle
4. Position sizing: `max_position_frac` × portfolio equity, never exceeding per-coin limit

When user removes a coin:
1. If position open → submit market sell to flatten
2. Remove from watchlist
3. Archive telemetry (don't delete — keep for performance history)

---

## 6. Signal Research Layer

Signal research lives in `lab/` and is promoted to the main system only after walk-forward validation. The three candidate signal types (chosen by the user):

### 6a. 4h EMA Trend
- **Rationale:** Backtest already showed thin but real edge (PF ~1.1 gross on 4h). Survives at lower cost tiers than 15m.
- **Mechanics:** fast EMA / slow EMA crossover on 4h bars, Kronos forecast as confirmation filter
- **Research task:** walk-forward test on BTC/ETH 4h (2022–2026), verify edge survives 60 bps cost

### 6b. Funding Rate Mean-Reversion
- **Rationale:** Perpetual swap funding rates have documented mean-reversion behavior. Extreme positive funding → crowded long → price often snaps back. Neutral signal for spot, strong for perps.
- **Mechanics:** poll Binance/Bybit funding rate API; when 8h funding > 0.05% (annualized ~220%) → signal SHORT bias; when < -0.01% → LONG bias
- **Research task:** backtest funding-rate extremes as entry filter overlaid on BTC/ETH spot price (2021–2026)
- **Note:** Alpaca is spot-only. Funding rate is used as a filter/timing signal, not a direct trade.

### 6c. On-Chain Exchange Flows
- **Rationale:** Large BTC inflows to exchanges often precede sell pressure. Outflows signal accumulation.
- **Data source:** Glassnode free tier or CryptoQuant (exchange net flow, 24h)
- **Mechanics:** if 7d net flow to exchanges > +2 std dev → reduce position / skip new longs; if < -2 std dev → allow larger position
- **Research task:** correlation analysis between exchange net flow and BTC price 7–30 days forward (2020–2026)

### Signal Fusion (future)
Once ≥2 signals are validated, a fusion layer weights them per regime:
- Uptrend: EMA trend signal primary, on-chain as position-size modifier
- Downtrend: funding rate filter primary, EMA for timing
- Neutral: conservative defaults, funding rate filter only

---

## 7. What Does NOT Change

- Trading loop cadence (15m bar evaluation)
- Alpaca paper/live order submission
- Coinbase candle ingestion
- Telemetry and decision logging (backend stays intact)
- The VM deployment (swingbot VM 107, Tailscale endpoint)
- Docker compose setup
- Test suite (adapt existing tests, don't delete coverage)

---

## 8. Implementation Order (for the plan)

1. **RiskProfile abstraction** — define the three param sets, wire to existing ProfileStore, expose via new `/api/risk-level` endpoint (GET/PUT). No UI yet.
2. **AutoTuner service** — drawdown monitoring, auto-adjustment logic, defensive mode flag. Unit tested in isolation.
3. **New thermostat frontend** — three screens, two controls, wired to the new endpoints. Old frontend deleted.
4. **Coin onboarding automation** — add/remove coin triggers automated profile creation + position management.
5. **API cleanup** — hide/remove all tuning endpoints not needed by the new UI.
6. **Signal research (parallel / ongoing)** — `lab/` work on 4h EMA, funding rate, on-chain. Runs alongside but does not block 1–5.
7. **Signal promotion** — when a signal passes walk-forward validation, integrate into the engine and wire to the fusion layer.

---

## 9. Success Criteria

- User can open the app, see portfolio P&L, and take no action required
- Adding a coin requires only typing a symbol — no other configuration
- Changing risk level requires one tap — visible effect on next bar
- AutoTuner responds to drawdown without any user input
- No strategy parameters are visible or accessible in the UI
- At least one new signal type passes walk-forward validation and is promoted to live paper trading
