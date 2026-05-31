# SwingBot Trading Guide

A step-by-step walkthrough for getting the bot trading, what every field on the
Strategy form does, and two ready-to-use example configurations.

> **Safety first:** The bot defaults to **PAPER** (simulated money on Alpaca's
> test server). It will not touch real money until you explicitly switch to LIVE,
> and the server blocks that switch until your paper results pass a graduation
> check (see [Going Live](#going-live)).

---

## The 5 steps to start trading

You must do these **in order**. The bot will not open a single trade until all
five are done.

| # | Where | What |
|---|-------|------|
| 1 | Settings → Access token | Unlock write actions with your API token |
| 2 | Settings → Alpaca credentials | Paste your Alpaca key/secret (Paper) and Save |
| 3 | Strategy | Fill the form, enable ≥1 signal, **Save profile** |
| 4 | Strategy | **Set active** on that profile |
| 5 | Dashboard → Controls | Click **Start bot** |

If you skip step 3 or 4, **Start bot** returns *"no active strategy profile set."*
If you skip step 2, it returns *"Alpaca credentials not set."*

---

### Step 1 — Unlock the UI with your access token

Every action that changes state (saving credentials, saving a profile, starting
the bot) requires the server access token in the `X-Token` header. The UI stores
it in your browser once you paste it.

Find the token:

```bash
# It's printed in the container logs and stored on disk:
cat ~/.swingbot/token
# or
docker compose logs | grep -i token
```

Paste it into the **Access token** box (Settings page, bottom). Read-only views
(Dashboard, journal, metrics) work without it; writes do not.

---

### Step 2 — Connect your Alpaca account (paper)

1. Create a free account at [alpaca.markets](https://alpaca.markets) and generate
   **paper trading** API keys (paper and live each have *separate* keys).
2. Settings → **Alpaca credentials**:
   - **Key ID** — the public half, paste from Alpaca.
   - **Secret key** — the private half; write-only, never shown back.
   - **Paper endpoint** — leave **checked**.
3. **Save credentials.** "Secret set" should flip to `true`.

---

### Step 3 — Build a strategy profile

Go to the **Strategy** tab. The form is grouped into Core / Entry signals /
Exits / Risk. Every field maps directly to a `StrategyProfile` value. You must
enable **at least one** entry signal or Save is rejected.

#### Core

| Field | Profile key | What it does | Sensible value |
|-------|-------------|--------------|----------------|
| Profile name | `name` | A save slot label. One per coin or idea. | `btc-starter` |
| Symbol | `symbol` | Alpaca crypto pair, `BASE/QUOTE`. Must be a pair Alpaca supports. | `BTC/USD` |
| Timeframe | `timeframe` | Candle size. Each "bar" is one candle. Most settings below count in bars. | `15m` |
| Entry threshold | `entry_threshold` | Buy when the combined signal score clears this. Higher = pickier. **Calibrate against your signal weights** (see below). | `0.3` |
| Regime MA period | `regime_ma_period` | Length (bars) of the trend filter moving average. | `50` |

**The trend gate (regime).** Before scoring signals, the bot checks the trend:

- **Uptrend** — price above the MA *and* the MA is rising → entries allowed.
- **Neutral** — anything in between → entries allowed.
- **Downtrend** — price below the MA *and* the MA is falling → **entries blocked.**

So in a clear downtrend the bot simply waits, no matter how strong the signals.

#### Entry signals (enable at least one)

Each enabled signal produces a reading from **0 to 1**, multiplied by its
**weight**. The bot sums the contributions; if the total ≥ `entry_threshold`
(and the regime gate allows), it buys. Weights typically sum to ~1.0.

| Signal | Params | Reading is high when… |
|--------|--------|-----------------------|
| **Oversold (RSI dip)** | `weight`, `oversold_level`, `period` | RSI drops below `oversold_level`. Score = `(level − RSI) / level`, clamped 0–1. |
| **VWAP** | `weight`, `window`, `max_dist` | Price is below VWAP. Score = `(VWAP − price) / VWAP ÷ max_dist`, clamped 0–1. `max_dist` is how far below still counts. |
| **Relative strength** | `benchmark_symbol`, `weight`, `band`, `lookback` | The coin is outperforming the benchmark (e.g. BTC) over `lookback` bars. |
| **FVG** | `weight` | ⚠️ **Stub — always scores 0.** Not implemented. Leave off. |
| **Kronos Forecast** | `weight`, `pred_len`, `threshold_pct` | The Kronos AI model forecasts a price rise. Score = `expected_gain ÷ threshold_pct`, clamped 0–1. Needs GPU (the Docker image has it). |

**Kronos fields:**
- `pred_len` — how many bars ahead to forecast. At 15m, `4` = 1 hour ahead.
- `threshold_pct` — the expected % gain that maps to a full score of 1.0.
  `0.02` means "a 2% forecast gain = max score." Flat/negative forecasts score 0.

#### Exits (always active)

Alpaca crypto can't hold stop/target orders on the exchange, so the bot enforces
them itself on every poll.

| Field | Profile key | What it does | Sensible value |
|-------|-------------|--------------|----------------|
| ATR period | `atr_period` | Bars used to measure volatility (Average True Range). | `14` |
| Stop multiple | `stop_atr_mult` | Stop = entry − (this × ATR). | `1.5` |
| Take-profit multiple | `take_profit_atr_mult` | Target = entry + (this × ATR). Keep > stop multiple. | `2.0` |
| Max hold bars | `max_hold_bars` | Time-exit: close after this many bars if neither stop nor target hit. | `32` (8h at 15m) |

#### Risk & circuit breakers

| Field | Profile key | What it does | Sensible value |
|-------|-------------|--------------|----------------|
| Risk per trade | `risk_per_trade` | Fraction of equity risked if the stop is hit. | `0.01` (1%) |
| Max position size | `max_position_frac` | Hard cap on one position as a fraction of equity. | `0.25` (25%) |
| Daily loss kill-switch | `daily_loss_limit_pct` | Halt new entries after the day is down this much. | `0.05` (−5%) |
| Max consecutive losses | `max_consecutive_losses` | Halt after this many losers in a row. | `4` |
| Cooldown after stop-out | `cooldown_minutes` | Wait this long after a stop before re-entering. | `60` |

**Position sizing** combines two caps and takes the smaller:

```
risk_qty = (equity × risk_per_trade) / stop_distance     # risk-based
cap_qty  = (equity × max_position_frac) / entry_price     # size cap
qty      = min(risk_qty, cap_qty)
```

Click **Save profile** when done.

---

### Step 4 — Set the profile active

Saving a profile does **not** select it. On the Strategy page, find your profile
in the list and click **Set active**. The bot only ever runs the *active*
profile. The active one shows an `active` chip.

---

### Step 5 — Start the bot

Dashboard → **Controls** → **Start bot**.

The status banner flips to running. From here the bot polls the market every
`poll_seconds` (default 60s), and on each poll:

1. Manages any open position (stop / target / time-exit).
2. If flat and not paused, and the kill switch is clear, and the regime gate
   allows, and the combined signal score ≥ threshold, and ATR > 0, and computed
   size > 0 → it **market-buys** and records the stop/target/time-exit.

**Stop bot** halts the loop entirely. **Pause entries** keeps managing the open
position but stops scanning for new ones. **HALT** trips the kill switch (no new
entries; open position still managed). **Flatten** market-sells right now.

---

## Worked example: how one entry happens

Profile: **BTC/USD, 15m**, `oversold` (weight 0.6, level 45) + `vwap`
(weight 0.4, max_dist 0.03), `entry_threshold = 0.3`, `regime_ma_period = 50`.

At some 15m close, suppose:

- **Regime:** BTC price is above a rising 50-bar MA → **Uptrend** → entry allowed.
- **Oversold:** RSI = 32 → `(45 − 32) / 45 = 0.289` → ×0.6 = **0.173**.
- **VWAP:** price sits 1.5% below VWAP → `0.015 / 0.03 = 0.5` → ×0.4 = **0.200**.
- **Total score = 0.373 ≥ 0.30** → the bot buys.

Sizing at entry (say price $60,000, ATR $400, equity $1,000):

- Stop = `60000 − 1.5 × 400` = **$59,400** (stop distance $600).
- Target = `60000 + 2.0 × 400` = **$60,800**.
- `risk_qty = (1000 × 0.01) / 600 = 0.0167 BTC` (~$1,000 notional).
- `cap_qty  = (1000 × 0.25) / 60000 = 0.00417 BTC` (~$250 notional).
- `qty = min(...) = 0.00417 BTC` → the **25% size cap binds**, keeping the
  position small. The trade then exits on the $59,400 stop, $60,800 target, or
  after 32 bars (8 hours), whichever comes first.

---

## Example profiles (JSON)

If you'd rather not click through the form, these are exactly what the form
produces. They're shown for reference — you still enter the values in the UI.

### A. Simple starter (no GPU needed)

```json
{
  "symbol": "BTC/USD",
  "timeframe": "15m",
  "benchmark_symbol": "BTC/USD",
  "entry_threshold": 0.3,
  "regime_ma_period": 50,
  "atr_period": 14,
  "stop_atr_mult": 1.5,
  "take_profit_atr_mult": 2.0,
  "max_hold_bars": 32,
  "risk_per_trade": 0.01,
  "max_position_frac": 0.25,
  "daily_loss_limit_pct": 0.05,
  "max_consecutive_losses": 4,
  "cooldown_minutes": 60,
  "signals": {
    "oversold": { "weight": 0.6, "oversold_level": 45, "period": 14 },
    "vwap":     { "weight": 0.4, "window": 96, "max_dist": 0.03 }
  }
}
```

### B. Kronos-assisted (uses the GPU)

Adds the AI forecast as a third of the score. Note `entry_threshold` is raised
to `0.45` because there are now three signals contributing.

```json
{
  "symbol": "BTC/USD",
  "timeframe": "15m",
  "benchmark_symbol": "BTC/USD",
  "entry_threshold": 0.45,
  "regime_ma_period": 50,
  "atr_period": 14,
  "stop_atr_mult": 1.5,
  "take_profit_atr_mult": 2.0,
  "max_hold_bars": 32,
  "risk_per_trade": 0.01,
  "max_position_frac": 0.25,
  "daily_loss_limit_pct": 0.05,
  "max_consecutive_losses": 4,
  "cooldown_minutes": 60,
  "signals": {
    "oversold":        { "weight": 0.4, "oversold_level": 45, "period": 14 },
    "vwap":            { "weight": 0.3, "window": 96, "max_dist": 0.03 },
    "kronos_forecast": { "weight": 0.3, "pred_len": 4, "threshold_pct": 0.02 }
  }
}
```

In the form, enable the **Kronos Forecast** toggle and set Weight `0.3`,
Forecast bars `4`, Bullish threshold `0.02`. The model
(`NeoQuasar/Kronos-small`) is already baked into the Docker image's cache.

---

## Going live

The **Go LIVE** button is intentionally gated. The server refuses to switch to
real money until your paper trading clears:

- **≥ 30 closed paper trades**, and
- **positive expectancy** (average trade > 0).

Until then, **Go LIVE** returns *"go-live blocked: …"* with the reason. Run on
paper, accumulate a track record, then switch. When you do go live, you'll need
**live** Alpaca keys (uncheck "Paper endpoint" in Settings and save those keys).

---

## Controls reference

| Button | Effect |
|--------|--------|
| **Start bot** | Begins the trading loop (requires creds + active profile). |
| **Stop bot** | Halts the loop entirely. Open positions stop being managed. |
| **Pause entries** | Keeps managing the open position; stops scanning for new ones. |
| **HALT** | Trips the kill switch: no new entries. Open position still managed by stop/target. |
| **Reset kill switch** | Clears a tripped kill switch so entries resume. |
| **Flatten** | Market-sells the open position immediately, ignoring stop/target. |
| **Go LIVE / Go paper** | Switch money mode. LIVE is gated by the graduation check. |

---

## Quick reference: what blocks an entry

The bot stays flat on any poll where **any** of these is true:

- Bot not started, or **Stopped** / **Paused**.
- Kill switch active (manual HALT, daily-loss limit, or consecutive-loss limit).
- Inside the post-stop **cooldown** window.
- Regime is **Downtrend**.
- Combined signal score **< entry_threshold**.
- ATR is 0 (not enough history warmed up), or computed size ≤ 0.
- The broker already holds a position (desync guard).
