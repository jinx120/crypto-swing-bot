# Deploy handoff — core-engine autonomous loop (NEXT SESSION)

> **✅ DEPLOYED 2026-06-17.** The steps below were executed: container `core-engine` is running
> (`--restart unless-stopped`, `core_engine_data:/data` volume). First autonomous tick verified —
> 300 candles self-backfilled, journal `decision` = BTC/USD HOLD ("regime gate blocks entry:
> Regime.DOWNTREND", confluence-only), `running_desired=1`. NB: no `PYTHONUNBUFFERED` in the image,
> so `docker logs` stays empty until the buffer flushes — use `docker exec core-engine python -m
> core_engine report` or read `/data/journal.db`. Open forks: promote `core-engine`→`master`? add
> Kronos/torch for full-signal decisions? The runbook below is retained for rebuild/reference.

> **Single-read resume for the deploy task.** Everything below is current as of 2026-06-17.
> The engine is built, fully fixed, and live-paper-validated. The ONLY remaining work is
> deploying it as a persistent autonomous loop. Do this on a clean/fresh session.

## State snapshot (verified)
- Branch: **`core-engine`** @ `5847900` (= `origin/core-engine`; pushed). `master`/`src` mostly untouched.
- Suites green: full repo **572 passed / 6 skipped**, lab **23 passed**, ruff clean.
- Docker image **`core-engine:dev`** builds + runs (`docker build -f lab/core-engine/Dockerfile -t core-engine:dev .` from repo root).
- Live paper acceptance PASS (see `docs/LIVE_ACCEPTANCE.md`). `get_position` sees real holdings; adopt derives real brackets.
- Alpaca **paper account is FLAT** (~$95.4k cash, 0 positions, 0 open orders).
- Engine is **stopped**: `running_desired=False`. Creds in repo `.env` (gitignored): `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY`, `ALPACA_BASE_URL=https://paper-api.alpaca.markets`.

## Key gotchas (already solved — don't rediscover)
- **`.env` is `.dockerignore`d**, so the image has NO creds. You MUST pass them at run time with `--env-file /home/redji/crypto-swing-bot/.env`. `load_alpaca_credentials()` reads `os.environ`, which `--env-file` populates.
- **Kronos isn't in the slim image** → the engine logs "Kronos unavailable" and runs **confluence-only** (`kronos=None`, neutral 0.0). Acceptable; note decisions won't use Kronos until torch+Kronos are added to the image.
- `python -m core_engine run` sets `running_desired=True` on start, then `run_forever()` ticks every `LOOP_SECONDS=300`. It self-backfills candles each tick via `AlpacaData.get_candles(lookback=300)`, so no manual backfill is needed.
- Engine timeframe is **`5m`** (not "5Min" — that 404s the fetcher).
- Container data lives in volume `/data` (`CORE_ENGINE_DATA=/data`): `candles.db`, `state.db`, `journal.db`.

## Deploy steps (recommended: persistent `docker run`)
```bash
cd /home/redji/crypto-swing-bot
git checkout core-engine && git pull --ff-only origin core-engine
docker build -f lab/core-engine/Dockerfile -t core-engine:dev .      # ensure current
docker run -d --name core-engine --restart unless-stopped \
  --env-file /home/redji/crypto-swing-bot/.env \
  -v core_engine_data:/data \
  core-engine:dev
```

## Verify the first autonomous tick
```bash
docker logs -f core-engine            # watch the first tick (Ctrl-C to stop following)
# after ~1 tick:
docker exec core-engine python -m core_engine report   # expect a journaled decision
```
- Confirm `journal` has a `decision` event (HOLD or an entry).
- If it ENTERED: check Alpaca paper for the order; confirm the engine reports truthfully
  (a `pending_new` BUY is "entry pending", NOT a position — Alpaca paper crypto BUYs often stall).
- `running_desired` should be `True` (started); a restart should auto-resume.

## Decisions likely to surface
- Promote `core-engine` → `master`? (separate decision once the loop is proven live.)
- Add Kronos (torch) to the image for full-signal decisions, or stay confluence-only for now?
- Add a thin UI later (secondary, per the project's priority order).
