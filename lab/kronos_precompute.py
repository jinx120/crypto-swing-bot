"""Run INSIDE the swingbot container (GPU torch + Kronos). Caches per-bar Kronos
forecast pct_change so the host can backtest Kronos profiles cheaply.

For each bar i it feeds the trailing CTX (=max_context) bars to Kronos and records
pct_change = (forecast_close[last] - close[i]) / close[i]  -- exactly what
KronosForecastSignal.evaluate computes. Output CSV: ts, pct_change.

Env: DB, SYM, RULE (""=native 15m, e.g. "4h"), PRED (pred_len), OUT (csv path).
Run: docker exec -i <c> sh -c 'DB=/tmp/bt.db SYM=BTC/USD RULE=4h PRED=8 OUT=/tmp/k.csv \
       python -u lab/kronos_precompute.py 2>/tmp/k.err'
"""
import os
import sqlite3
import time

import numpy as np
import pandas as pd

from swingbot.signals.kronos_adapter import KronosAdapter

DB = os.environ["DB"]
SYM = os.environ["SYM"]
RULE = os.environ.get("RULE", "")
PRED = int(os.environ.get("PRED", "8"))
OUT = os.environ["OUT"]
CTX = 512

con = sqlite3.connect(DB)
df = pd.read_sql_query(
    "select ts, open, high, low, close, volume from bars "
    "where symbol=? and timeframe='15m' order by ts",
    con, params=(SYM,))
con.close()
df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True)
if RULE:
    df = (df.set_index("ts")
            .resample(RULE)
            .agg({"open": "first", "high": "max", "low": "min",
                  "close": "last", "volume": "sum"})
            .dropna().reset_index())
if os.environ.get("LIMIT"):
    df = df.tail(int(os.environ["LIMIT"])).reset_index(drop=True)

ad = KronosAdapter.from_profile({"pred_len": PRED})
n = len(df)
start = max(CTX, 210)
print(f"{SYM} rule={RULE or '15m'} pred={PRED}: {n} bars, forecasting {n-start} "
      f"from idx {start}", flush=True)

ts_out, pct_out = [], []
t0 = time.time()
for i in range(start, n):
    sl = df.iloc[i + 1 - CTX:i + 1]
    fc = ad._run_with_timeout(sl)
    if fc is None:
        pc = np.nan
    else:
        cur = float(sl["close"].iloc[-1])
        pc = (float(fc["close"].iloc[-1]) - cur) / cur
    ts_out.append(df["ts"].iloc[i])
    pct_out.append(pc)
    if (i - start) % 500 == 0 and i > start:
        done = i - start
        rate = done / (time.time() - t0)
        eta = (n - i) / rate / 60
        print(f"  {done}/{n-start}  {rate:.1f} bar/s  eta {eta:.0f}min", flush=True)

pd.DataFrame({"ts": ts_out, "pct_change": pct_out}).to_csv(OUT, index=False)
print(f"wrote {OUT}: {len(ts_out)} rows in {(time.time()-t0)/60:.1f}min "
      f"(nan {int(np.isnan(pct_out).sum())})", flush=True)
