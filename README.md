# SwingBot

A personal, **long-only crypto swing-trading bot** for [Alpaca](https://alpaca.markets/) (spot — Alpaca crypto can't short). Target asset TRX/USD; holds range from minutes to about a day. Design motto: *simple beats clever*.

One strategy engine runs in three modes — **backtest**, **paper**, and **live** — and the whole thing is operable from a browser dashboard (no file editing required once it's running).

> ⚠️ **This trades real money in live mode.** It binds to localhost only and ships with guardrails (token auth, server-side graduation gate before live, kill switch, confirm dialogs). Read the [Security](#security) section before going live.

---

## How it works (1-minute version)

- **Entry** = a *confluence score* (oversold / VWAP / relative-strength / FVG signals, each weighted) that must clear a threshold **and** pass a hard trend-regime gate. The regime gate + relative-strength are the defense against buying a "falling knife" on a coin with no fundamental floor.
- **Exits** = an ATR-based bracket (stop = entry − k·ATR, take-profit = entry + m·ATR) plus a max-hold time cap. Alpaca crypto has no broker brackets, so exits are enforced client-side on every bar.
- **Risk** = fixed-fractional sizing (e.g. 1%/trade) plus four circuit breakers: daily-loss kill switch, max position cap, max-concurrent / one-per-instrument, and a re-entry cooldown.
- **Profiles** = per-asset config saved in SQLite; pick which one is active from the UI.

Full design + phase plans live in [`docs/superpowers/`](docs/superpowers/).

---

## Requirements

- **Python ≥ 3.11** (developed on 3.12; needs the `venv` module — on Debian/Ubuntu: `sudo apt install python3.12-venv`)
- **Node.js ≥ 18** + npm (for the dashboard)
- An **Alpaca account** with paper API keys (live keys only when you're ready)

---

## Clone & set up

```bash
git clone https://github.com/jinx120/crypto-swing-bot.git
cd crypto-swing-bot

# Python backend (editable install into a virtualenv)
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"      # drop [dev] if you don't want pytest/httpx

# Verify the install
pytest -q                    # expect: 112 passed, 2 skipped (Alpaca network tests)
```

Credentials can be entered in the browser (recommended), or via a `.env` file for the CLI tools:

```bash
cp .env.example .env         # then edit .env with your Alpaca paper keys
```

`.env` is gitignored — never commit it.

---

## Run the dashboard (the normal way to use it)

**1. Start the backend** (venv active, from the repo root):
```bash
swingbot-web
```
- Serves on **`http://127.0.0.1:8000`** (localhost only).
- Prints an **API token** on startup — copy it (also written to `~/.swingbot/token`).

**2. Start the frontend:**
```bash
cd frontend
npm install
npm run dev                  # opens on http://localhost:3000 (or next free port)
```
The dev server proxies `/api` → `:8000`.

**3. First-time setup, all in the browser:**
1. **Settings → API token:** paste the token from step 1 and Save (kept in this browser's localStorage; required for any control/write action).
2. **Settings → Alpaca credentials:** paste your paper **Key ID** + **Secret** (write-only/masked), keep *Paper endpoint* checked, Save.
3. **Strategy:** fill in the field-by-field form (symbol, signals, thresholds, exits, risk, circuit breakers), name the profile, Save, then **Set active**. Hover the **ⓘ** hints on any field for plain-English explanations.
4. **Dashboard:** watch the live signal breakdown, position, risk, journal, and metrics (2 s polling). Use **Controls** to HALT / reset / pause / resume / flatten, or switch mode (Go LIVE is blocked server-side until paper results graduate).

See [`frontend/README.md`](frontend/README.md) for more on the UI.

---

## Command-line tools

All installed by `pip install -e .`:

| Command | Purpose |
|---|---|
| `swingbot-backtest --csv DATA.csv --profile NAME` | Backtest a profile against historical OHLCV CSV |
| `swingbot-run --profile NAME --db state.db` | Run the paper/live trading loop headless |
| `swingbot-web` | Start the FastAPI server behind the dashboard |

---

## Production build (frontend)

```bash
cd frontend
npm run build                # outputs static assets to frontend/dist/
```

`dist/` and `node_modules/` are gitignored; rebuild after cloning.

---

## Security

- The backend binds to **127.0.0.1 only**. **Never expose port 8000 or 3000 to the internet** — the UI holds money-moving Alpaca credentials and can place orders. To reach it from another device, tunnel over a private network (e.g. Tailscale), not a public port.
- All write/control endpoints require the **`X-Token`** header (the token printed at startup).
- The Alpaca **secret** is stored in `~/.swingbot/credentials.json` (chmod 600), never returned by the API and never rendered back in the browser.
- **Live trading is gated:** the server refuses to switch to live mode until paper results pass the graduation checks.

---

## Project layout

```
src/swingbot/      Strategy engine, risk, broker/data adapters, orchestrator, FastAPI app
tests/             Pytest suite (112 passing)
frontend/          React 18 + Vite dashboard (plain CSS, Valhalla dark theme)
docs/superpowers/  Design spec and phased implementation plans
```

---

## Status

- **Phase 1** — strategy engine + backtester ✅
- **Phase 2** — paper/live broker adapters, risk manager, SQLite state store, orchestrator ✅
- **Phase 3** — FastAPI control API + React dashboard (token auth, field-based strategy editor, context hints) ✅

Personal/experimental. Not financial advice.
