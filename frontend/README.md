# SwingBot Dashboard (frontend)

Valhalla-styled React UI to run the bot entirely from the browser — monitor, control, edit strategies, and enter Alpaca credentials. No file editing.

## Run it

**1. Start the backend** (from the repo root, venv active):
```bash
swingbot-web
```
- Serves on `http://127.0.0.1:8000` — **localhost only**.
- Prints an **API token** on startup. Copy it (also saved to `~/.swingbot/token`).

**2. Start the frontend dev server:**
```bash
cd frontend && npm install && npm run dev
```
Open the printed URL (http://localhost:3000, or 3001 if 3000 is taken). The dev server proxies `/api` → `:8000`.

## First-time setup (all in the browser)
1. **Settings → API token:** paste the token from step 1, Save (stored in this browser's localStorage; required for any write/control action).
2. **Settings → Alpaca credentials:** paste your paper **Key ID** + **Secret** (write-only/masked), keep "Paper endpoint" checked, Save.
3. **Strategy:** fill in the field-by-field form (symbol, signals, thresholds, exits, risk, circuit breakers) — hover the **ⓘ** hints for plain-English explanations — give it a name, Save, then **Set active**.
4. **Dashboard:** watch the live signal breakdown, position, risk, journal, and metrics (2s polling). Use **Controls** to HALT / reset / pause / resume / flatten, or switch mode (Go LIVE is blocked server-side until paper results graduate).

## Security
- The backend binds to **127.0.0.1 only**. **Never expose port 8000 or 3000 to the internet** — the UI stores money-moving Alpaca credentials and can place orders.
- The Alpaca secret is stored plaintext in `~/.swingbot/credentials.json` (chmod 600), never returned by the API, never rendered back in the browser.

## Build
```bash
cd frontend && npm run build   # produces dist/
```
