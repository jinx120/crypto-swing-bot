# Docker GPU Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get the full swingbot stack (FastAPI + React dashboard + Kronos GPU inference) running in a single Docker container at http://localhost:8000.

**Architecture:** Multi-stage Dockerfile (node:20-slim builds frontend → pytorch/pytorch:2.6.0-cuda12.6-cudnn9-runtime runs everything). FastAPI serves the built frontend via StaticFiles. Kronos model weights are pre-downloaded to the host HuggingFace cache before first container start. Host `~/.swingbot` is bind-mounted for persistent data.

**Tech Stack:** Docker, nvidia-container-toolkit, PyTorch 2.6 + CUDA 12.6, FastAPI + uvicorn, React (pre-built), Kronos (`NeoQuasar/Kronos-small` + `NeoQuasar/Kronos-Tokenizer-base`), HuggingFace Hub.

---

## File Map

| Path | Action | What it does |
|------|--------|-------------|
| `Dockerfile` | Create | Multi-stage build |
| `docker-compose.yml` | Create | GPU runtime, volumes, ports |
| `.dockerignore` | Create | Slim build context |
| `Makefile` | Create | `build`, `up`, `down`, `logs`, `download-model` |
| `scripts/download_model.py` | Create | Pre-download Kronos weights to host HF cache |
| `src/swingbot/webmain.py` | Modify | Read `SWINGBOT_HOST` + `SWINGBOT_DATA_DIR` env vars |
| `src/swingbot/web.py` | Modify | Mount `frontend/dist` as StaticFiles at `/` |
| `src/swingbot/signals/kronos_adapter.py` | Modify | Fix PredictorProtocol, from_profile(), _run_with_timeout() with real Kronos API |
| `tests/test_kronos_forecast.py` | Modify | Update FakePredictor signature to match real Kronos API |

---

## Task 1: Install nvidia-container-toolkit on host

**Files:** None (host system setup)

This is a prerequisite. Without it, `runtime: nvidia` in docker-compose will fail.

- [ ] **Step 1: Install nvidia-container-toolkit**

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

- [ ] **Step 2: Verify GPU runtime is registered**

```bash
docker info | grep -i runtime
```

Expected output includes: `nvidia` in the Runtimes list.

- [ ] **Step 3: Smoke-test GPU passthrough**

```bash
docker run --rm --runtime=nvidia --gpus all nvidia/cuda:12.6.0-base-ubuntu22.04 nvidia-smi
```

Expected: nvidia-smi output showing RTX 3050.

---

## Task 2: Fix `webmain.py` to read env vars

**Files:**
- Modify: `src/swingbot/webmain.py`
- Test: `tests/test_web_read.py` (append)

`webmain.py` currently hardcodes `host="127.0.0.1"` and `DATA_DIR = os.path.expanduser("~/.swingbot")`. Docker needs both overridable via env vars.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web_read.py` (check what's there first — if no such file, append to `tests/test_cli.py`; if file exists, add at end):

```python
import os
import importlib


def test_webmain_respects_swingbot_host_env(monkeypatch):
    """SWINGBOT_HOST env var overrides the default 127.0.0.1 bind address."""
    monkeypatch.setenv("SWINGBOT_HOST", "0.0.0.0")
    import swingbot.webmain as wm
    importlib.reload(wm)
    assert wm.HOST == "0.0.0.0"
    monkeypatch.delenv("SWINGBOT_HOST", raising=False)
    importlib.reload(wm)


def test_webmain_respects_swingbot_data_dir_env(monkeypatch, tmp_path):
    """SWINGBOT_DATA_DIR env var overrides the default ~/.swingbot path."""
    monkeypatch.setenv("SWINGBOT_DATA_DIR", str(tmp_path))
    import swingbot.webmain as wm
    importlib.reload(wm)
    assert wm.DATA_DIR == str(tmp_path)
    monkeypatch.delenv("SWINGBOT_DATA_DIR", raising=False)
    importlib.reload(wm)
```

- [ ] **Step 2: Run to confirm failure**

```bash
.venv/bin/pytest tests/test_web_read.py::test_webmain_respects_swingbot_host_env -v 2>&1 | tail -8
```

Expected: `AttributeError: module 'swingbot.webmain' has no attribute 'HOST'`

- [ ] **Step 3: Update `src/swingbot/webmain.py`**

Replace the module-level `DATA_DIR` line and the `uvicorn.run()` call:

```python
from __future__ import annotations

import os
import secrets

import uvicorn

from swingbot.credentials import CredentialStore
from swingbot.profiles import ProfileStore
from swingbot.service import BotService
from swingbot.web import create_app

HOST = os.environ.get("SWINGBOT_HOST", "127.0.0.1")
DATA_DIR = os.environ.get("SWINGBOT_DATA_DIR", os.path.expanduser("~/.swingbot"))


def _ensure_token(path: str) -> str:
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    tok = secrets.token_urlsafe(24)
    with open(path, "w") as f:
        f.write(tok)
    os.chmod(path, 0o600)
    return tok


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    token = _ensure_token(os.path.join(DATA_DIR, "token"))
    profiles = ProfileStore(os.path.join(DATA_DIR, "swingbot.db"))
    creds = CredentialStore(os.path.join(DATA_DIR, "credentials.json"))
    service = BotService(profiles=profiles, creds=creds,
                         state_db=os.path.join(DATA_DIR, "swingbot.db"))
    app = create_app(controller=service, profiles=profiles, creds=creds, token=token)
    print(f"[swingbot-web] token: {token}")
    print(f"[swingbot-web] http://{HOST}:8000")
    uvicorn.run(app, host=HOST, port=8000)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verify tests pass**

```bash
.venv/bin/pytest tests/test_web_read.py -x -q 2>&1 | tail -4
```

Expected: all pass (including the 2 new ones)

- [ ] **Step 5: Full suite check**

```bash
.venv/bin/pytest tests/ -x -q 2>&1 | tail -3
```

Expected: 132 passed, 4 skipped

- [ ] **Step 6: Commit**

```bash
git add src/swingbot/webmain.py tests/test_web_read.py
git commit -m "feat: read SWINGBOT_HOST and SWINGBOT_DATA_DIR from env vars"
```

---

## Task 3: Fix `web.py` to serve built frontend

**Files:**
- Modify: `src/swingbot/web.py`
- Test: `tests/test_web_read.py` (append)

FastAPI currently has no static file serving. Add a `StaticFiles` mount guarded by `os.path.isdir` so it only activates when `frontend/dist` actually exists (tests and dev remain unaffected).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web_read.py`:

```python
import pathlib
from unittest.mock import patch


def test_create_app_mounts_static_when_dist_exists(tmp_path):
    """create_app() mounts StaticFiles at / when frontend/dist exists."""
    # Create a minimal dist dir with index.html
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")

    from swingbot.web import create_app

    class FakeController:
        def status(self): return {}
        def journal(self): return []
        def metrics(self): return {}
        def halt(self): pass
        def reset(self): pass
        def pause(self): pass
        def resume(self): pass
        def flatten(self): pass
        def set_mode(self, m): return True, ""

    class FakeProfiles:
        def list(self): return []
        def save(self, n, p): pass
        def get(self, n): return None
        def get_active_name(self): return None
        def get_active(self): return None
        def set_active(self, n): pass
        def delete(self, n): pass

    class FakeCreds:
        def status(self): return {}
        def set(self, *a): pass

    with patch("swingbot.web._DIST", str(dist)):
        app = create_app(FakeController(), FakeProfiles(), FakeCreds(), token="test")

    route_names = [r.name for r in app.routes]
    assert "frontend" in route_names


def test_create_app_skips_static_when_dist_missing():
    """create_app() does NOT mount StaticFiles when frontend/dist is absent."""
    from swingbot.web import create_app

    class FakeController:
        def status(self): return {}
        def journal(self): return []
        def metrics(self): return {}
        def halt(self): pass
        def reset(self): pass
        def pause(self): pass
        def resume(self): pass
        def flatten(self): pass
        def set_mode(self, m): return True, ""

    class FakeProfiles:
        def list(self): return []
        def save(self, n, p): pass
        def get(self, n): return None
        def get_active_name(self): return None
        def get_active(self): return None
        def set_active(self, n): pass
        def delete(self, n): pass

    class FakeCreds:
        def status(self): return {}
        def set(self, *a): pass

    with patch("swingbot.web._DIST", "/nonexistent/path/that/does/not/exist"):
        app = create_app(FakeController(), FakeProfiles(), FakeCreds(), token="test")

    route_names = [r.name for r in app.routes]
    assert "frontend" not in route_names
```

- [ ] **Step 2: Run to confirm failure**

```bash
.venv/bin/pytest tests/test_web_read.py::test_create_app_mounts_static_when_dist_exists -v 2>&1 | tail -8
```

Expected: FAIL — `AssertionError: assert 'frontend' not in [...]` or `AttributeError: module 'swingbot.web' has no attribute '_DIST'`

- [ ] **Step 3: Update `src/swingbot/web.py`**

Add these imports at the top of the file (after existing imports):

```python
import os
import pathlib

from fastapi.staticfiles import StaticFiles
```

Add the module-level `_DIST` variable right after the imports (before `class ProfileBody`):

```python
_DIST = str(pathlib.Path(__file__).parent.parent.parent / "frontend" / "dist")
```

At the very end of `create_app()`, before `return app`, add:

```python
    if os.path.isdir(_DIST):
        app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")

    return app
```

The complete bottom of `create_app()` should look like:

```python
    app.state.controller = controller
    app.state.profiles = profiles
    app.state.creds = creds
    app.state.token = token

    if os.path.isdir(_DIST):
        app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")

    return app
```

- [ ] **Step 4: Verify tests pass**

```bash
.venv/bin/pytest tests/test_web_read.py -x -q 2>&1 | tail -4
```

Expected: all pass

- [ ] **Step 5: Full suite check**

```bash
.venv/bin/pytest tests/ -x -q 2>&1 | tail -3
```

Expected: 134 passed, 4 skipped

- [ ] **Step 6: Commit**

```bash
git add src/swingbot/web.py tests/test_web_read.py
git commit -m "feat: serve built frontend via FastAPI StaticFiles"
```

---

## Task 4: Fix `kronos_adapter.py` with real Kronos API

**Files:**
- Modify: `src/swingbot/signals/kronos_adapter.py`
- Modify: `tests/test_kronos_forecast.py`

The current adapter was written against an assumed API. The real Kronos API (confirmed from README) differs in three ways:
1. `KronosPredictor(model, tokenizer, max_context=512)` — requires separate model + tokenizer, not no-args
2. `x_timestamp` and `y_timestamp` are pandas **Series**, not single `pd.Timestamp` values
3. No `top_k` or `verbose` parameters — only `T` (temperature float, default 1.0), `top_p`, `sample_count`

The `FakePredictor` in tests also needs updating to match.

- [ ] **Step 1: Update `FakePredictor` and affected tests in `tests/test_kronos_forecast.py`**

Find and replace the `FakePredictor` class with the updated version that matches the real API:

```python
class FakePredictor:
    """Satisfies PredictorProtocol without importing torch."""

    def __init__(self, forecast: pd.DataFrame, delay_s: float = 0.0):
        self._forecast = forecast
        self._delay_s = delay_s
        self.call_count = 0
        self.received_df_columns: list[str] = []
        self.received_x_timestamp = None

    def predict(self, df, x_timestamp, y_timestamp, pred_len, T, top_p, sample_count):
        import time
        self.received_df_columns = list(df.columns)
        self.received_x_timestamp = x_timestamp
        self.call_count += 1
        if self._delay_s:
            time.sleep(self._delay_s)
        return self._forecast
```

Replace `test_candle_ts_renamed_to_datetime` with two new tests:

```python
def test_x_timestamp_is_candle_ts_series():
    """Adapter passes candles['ts'] as x_timestamp Series to predictor."""
    candles = _df([100.0, 101.0, 102.0])
    fcast = _forecast_df([103.0])
    predictor = FakePredictor(fcast)
    adapter = KronosAdapter(predictor=predictor, pred_len=1)
    adapter.forecast(candles)
    pd.testing.assert_series_equal(
        predictor.received_x_timestamp.reset_index(drop=True),
        candles["ts"].reset_index(drop=True),
    )


def test_df_has_no_ts_or_datetime_column():
    """df passed to predictor has no timestamp column — it goes in x_timestamp."""
    candles = _df([100.0, 101.0, 102.0])
    fcast = _forecast_df([103.0])
    predictor = FakePredictor(fcast)
    adapter = KronosAdapter(predictor=predictor, pred_len=1)
    adapter.forecast(candles)
    assert "ts" not in predictor.received_df_columns
    assert "datetime" not in predictor.received_df_columns
    assert "open" in predictor.received_df_columns
```

Also update `test_forecast_returns_none_on_predictor_exception` — `BrokenPredictor.predict` uses `**kwargs` so it still works, but update to match new signature for clarity:

```python
def test_forecast_returns_none_on_predictor_exception():
    """An exception inside predict() returns None without raising."""
    class BrokenPredictor:
        def predict(self, df, x_timestamp, y_timestamp, pred_len, T, top_p, sample_count):
            raise RuntimeError("model exploded")

    candles = _df([100.0, 101.0, 102.0])
    adapter = KronosAdapter(predictor=BrokenPredictor(), pred_len=1)
    result = adapter.forecast(candles)
    assert result is None
```

Update `NonePredictor` classes in signal tests to match new signature:

```python
# In test_forecast_none_returns_neutral_when_neutral_on_error_true:
class NonePredictor:
    def predict(self, df, x_timestamp, y_timestamp, pred_len, T, top_p, sample_count):
        raise RuntimeError("always fails")

# In test_neutral_on_error_false_returns_zero:
class NonePredictor:
    def predict(self, df, x_timestamp, y_timestamp, pred_len, T, top_p, sample_count):
        raise RuntimeError("always fails")
```

- [ ] **Step 2: Run tests to confirm failures**

```bash
.venv/bin/pytest tests/test_kronos_forecast.py -x -q 2>&1 | tail -8
```

Expected: failures because `KronosAdapter._run_with_timeout` still uses old API (passing single Timestamp, top_k, verbose).

- [ ] **Step 3: Rewrite `src/swingbot/signals/kronos_adapter.py`**

```python
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Protocol

import pandas as pd

logger = logging.getLogger(__name__)


class PredictorProtocol(Protocol):
    """Matches the real KronosPredictor.predict() signature."""
    def predict(
        self,
        df: pd.DataFrame,
        x_timestamp: pd.Series,
        y_timestamp: pd.Series,
        pred_len: int,
        T: float,
        top_p: float,
        sample_count: int,
    ) -> pd.DataFrame: ...


def _load_kronos():
    """Lazy import gate — only called from KronosAdapter.from_profile()."""
    try:
        from kronos.model import Kronos, KronosTokenizer, KronosPredictor  # noqa: F401
        return Kronos, KronosTokenizer, KronosPredictor
    except ImportError as exc:
        raise ImportError(
            "Kronos forecast signal requires torch and the Kronos package. "
            "Install with: pip install -e '.[kronos]'"
        ) from exc


class KronosAdapter:
    """Wraps a PredictorProtocol: column extraction, x/y timestamp Series, cache, timeout."""

    def __init__(
        self,
        predictor: PredictorProtocol,
        pred_len: int = 4,
        timeout_s: float = 30.0,
        T: float = 1.0,
        top_p: float = 0.9,
        sample_count: int = 1,
    ) -> None:
        self._predictor = predictor
        self.pred_len = pred_len
        self._timeout_s = timeout_s
        self._T = T
        self._top_p = top_p
        self._sample_count = sample_count
        self._cache_key = None
        self._cache_val: pd.DataFrame | None = None
        self._precomputed: dict | None = None
        self._executor = ThreadPoolExecutor(max_workers=1)

    @classmethod
    def from_profile(cls, params: dict) -> "KronosAdapter":
        """Load real Kronos model from HuggingFace Hub.

        Recommended models for RTX 3050 (8 GB VRAM):
          - NeoQuasar/Kronos-small  (24.7M params, fast)   ← default
          - NeoQuasar/Kronos-base   (102.3M params, slower but more accurate)
        """
        Kronos, KronosTokenizer, KronosPredictor = _load_kronos()
        model_name = params.get("model_name", "NeoQuasar/Kronos-small")
        tokenizer_name = params.get("tokenizer_name", "NeoQuasar/Kronos-Tokenizer-base")
        tokenizer = KronosTokenizer.from_pretrained(tokenizer_name)
        model = Kronos.from_pretrained(model_name)
        predictor = KronosPredictor(model, tokenizer, max_context=512)
        return cls(
            predictor=predictor,
            pred_len=params.get("pred_len", 4),
            timeout_s=params.get("timeout_s", 30.0),
            T=params.get("T", 1.0),
            top_p=params.get("top_p", 0.9),
            sample_count=params.get("sample_count", 1),
        )

    def set_precomputed(self, cache: dict) -> None:
        """Populate the precomputed forecast cache (used by run_backtest)."""
        self._precomputed = cache

    def forecast(self, candles: pd.DataFrame) -> pd.DataFrame | None:
        """Return forecast DataFrame, or None if inference fails/times out."""
        ts_key = candles["ts"].iloc[-1]
        if self._precomputed is not None:
            return self._precomputed.get(ts_key)
        if ts_key == self._cache_key:
            return self._cache_val
        result = self._run_with_timeout(candles)
        self._cache_key = ts_key
        self._cache_val = result
        return result

    def _run_with_timeout(self, candles: pd.DataFrame) -> pd.DataFrame | None:
        """Execute predictor.predict() in a thread; return None on timeout or error."""
        x_timestamp = candles["ts"].reset_index(drop=True)
        kronos_df = candles[["open", "high", "low", "close", "volume"]].reset_index(drop=True)

        last_ts = candles["ts"].iloc[-1]
        bar_dur = candles["ts"].iloc[-1] - candles["ts"].iloc[-2]
        y_timestamp = pd.date_range(
            start=last_ts + bar_dur,
            periods=self.pred_len,
            freq=bar_dur,
            tz=last_ts.tzinfo,
        ).to_series().reset_index(drop=True)

        def _call() -> pd.DataFrame:
            return self._predictor.predict(
                df=kronos_df,
                x_timestamp=x_timestamp,
                y_timestamp=y_timestamp,
                pred_len=self.pred_len,
                T=self._T,
                top_p=self._top_p,
                sample_count=self._sample_count,
            )

        try:
            fut = self._executor.submit(_call)
            return fut.result(timeout=self._timeout_s)
        except (FuturesTimeoutError, Exception):
            logger.warning("Kronos inference failed or timed out", exc_info=True)
            return None
```

- [ ] **Step 4: Verify all Kronos tests pass**

```bash
.venv/bin/pytest tests/test_kronos_forecast.py tests/test_kronos_backtest.py -x -q 2>&1 | tail -5
```

Expected: 18 passed (14 forecast + 4 backtest)

- [ ] **Step 5: Full suite check**

```bash
.venv/bin/pytest tests/ -x -q 2>&1 | tail -3
```

Expected: 134 passed, 4 skipped

- [ ] **Step 6: Commit**

```bash
git add src/swingbot/signals/kronos_adapter.py tests/test_kronos_forecast.py
git commit -m "fix: update KronosAdapter to real Kronos API (Series timestamps, no top_k)"
```

---

## Task 5: Create `scripts/download_model.py`

**Files:**
- Create: `scripts/download_model.py`

Pre-downloads the Kronos tokenizer and model to the host HuggingFace cache (`~/.cache/huggingface/`). Run once before `docker compose up`.

- [ ] **Step 1: Create `scripts/` directory and script**

```bash
mkdir -p /home/redji/crypto-swing-bot/scripts
```

Create `scripts/download_model.py`:

```python
#!/usr/bin/env python3
"""Pre-download Kronos model weights to the HuggingFace cache.

Run once on the host before 'docker compose up':
    python scripts/download_model.py

Weights are saved to ~/.cache/huggingface/ (or $HF_HOME if set).
The docker-compose.yml bind-mounts this directory into the container
at /hf-cache, so subsequent container starts need no network access.

Models downloaded:
  - NeoQuasar/Kronos-Tokenizer-base  (~few MB)
  - NeoQuasar/Kronos-small           (~100MB, 24.7M params, recommended for RTX 3050)
"""
from huggingface_hub import snapshot_download

TOKENIZER_REPO = "NeoQuasar/Kronos-Tokenizer-base"
MODEL_REPO = "NeoQuasar/Kronos-small"

print(f"Downloading tokenizer: {TOKENIZER_REPO}")
tok_path = snapshot_download(repo_id=TOKENIZER_REPO)
print(f"  → {tok_path}")

print(f"Downloading model: {MODEL_REPO}")
model_path = snapshot_download(repo_id=MODEL_REPO)
print(f"  → {model_path}")

print("\nDone. Kronos weights are ready for Docker.")
print("Next: make build && make up")
```

- [ ] **Step 2: Make executable**

```bash
chmod +x /home/redji/crypto-swing-bot/scripts/download_model.py
```

- [ ] **Step 3: Commit**

```bash
git add scripts/download_model.py
git commit -m "feat: add Kronos model pre-download script"
```

---

## Task 6: Create `Dockerfile`

**Files:**
- Create: `Dockerfile`

Multi-stage build. Stage 1 builds the React frontend with Node. Stage 2 is the PyTorch runtime that runs the bot.

- [ ] **Step 1: Create `Dockerfile`**

```dockerfile
# ── Stage 1: Build React frontend ─────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python + PyTorch runtime ─────────────────────────────────────
FROM pytorch/pytorch:2.6.0-cuda12.6-cudnn9-runtime

# System deps: git (for pip install from GitHub), libgomp1 (OpenMP for torch)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libgomp1 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python package (swingbot + [kronos] extras)
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e ".[kronos]"

# Install Kronos package from GitHub
RUN pip install --no-cache-dir git+https://github.com/shiyu-coder/Kronos.git

# Copy built frontend from Stage 1
COPY --from=frontend-builder /build/dist ./frontend/dist

# Runtime config
ENV HF_HOME=/hf-cache
ENV SWINGBOT_HOST=0.0.0.0
ENV SWINGBOT_DATA_DIR=/data

EXPOSE 8000

CMD ["swingbot-web"]
```

- [ ] **Step 2: Commit**

```bash
git add Dockerfile
git commit -m "feat: add multi-stage Dockerfile (node builder + pytorch runtime)"
```

---

## Task 7: Create `docker-compose.yml`

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Create `docker-compose.yml`**

```yaml
services:
  swingbot:
    build: .
    runtime: nvidia
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=compute,utility
      - SWINGBOT_HOST=0.0.0.0
      - SWINGBOT_DATA_DIR=/data
      - HF_HOME=/hf-cache
    ports:
      - "8000:8000"
    volumes:
      - ${HOME}/.swingbot:/data
      - ${HOME}/.cache/huggingface:/hf-cache
    restart: unless-stopped
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add docker-compose.yml with GPU runtime and volume mounts"
```

---

## Task 8: Create `.dockerignore`

**Files:**
- Create: `.dockerignore`

Keeps the build context lean — excludes things rebuilt inside Docker or not needed in the image.

- [ ] **Step 1: Create `.dockerignore`**

```
.git
.venv
__pycache__
*.pyc
*.pyo
*.egg-info
.pytest_cache
frontend/node_modules
frontend/dist
tests
docs
graphify-out
*.md
.env
scripts
```

`frontend/dist` is excluded because Stage 1 rebuilds it from source inside Docker. Sending it in the build context would waste bandwidth and time.

- [ ] **Step 2: Commit**

```bash
git add .dockerignore
git commit -m "chore: add .dockerignore"
```

---

## Task 9: Create `Makefile`

**Files:**
- Create: `Makefile`

- [ ] **Step 1: Create `Makefile`**

```makefile
.PHONY: build up down logs shell download-model

## Build the Docker image
build:
	docker compose build

## Start the bot in the background
up:
	docker compose up -d

## Stop the bot
down:
	docker compose down

## Tail container logs (Ctrl-C to exit)
logs:
	docker compose logs -f

## Open a shell inside the running container
shell:
	docker compose exec swingbot bash

## Pre-download Kronos model weights to ~/.cache/huggingface (run once before first 'make up')
download-model:
	pip install --quiet huggingface_hub
	python scripts/download_model.py
```

- [ ] **Step 2: Commit**

```bash
git add Makefile
git commit -m "chore: add Makefile with build/up/down/logs/download-model targets"
```

---

## Task 10: Push all commits

- [ ] **Step 1: Push to remote**

```bash
git push origin master
```

---

## Task 11: Pre-download Kronos model weights

This step runs on the **host** (not in Docker). Downloads tokenizer + model to `~/.cache/huggingface/` which is bind-mounted into the container.

- [ ] **Step 1: Install huggingface_hub on host if not present**

```bash
pip install huggingface_hub 2>/dev/null || .venv/bin/pip install huggingface_hub
```

- [ ] **Step 2: Run the download script**

```bash
python scripts/download_model.py
```

Expected output:
```
Downloading tokenizer: NeoQuasar/Kronos-Tokenizer-base
  → /home/redji/.cache/huggingface/hub/models--NeoQuasar--Kronos-Tokenizer-base/...
Downloading model: NeoQuasar/Kronos-small
  → /home/redji/.cache/huggingface/hub/models--NeoQuasar--Kronos-small/...

Done. Kronos weights are ready for Docker.
Next: make build && make up
```

- [ ] **Step 3: Verify weights landed in cache**

```bash
ls ~/.cache/huggingface/hub/ | grep Kronos
```

Expected: two directories (`models--NeoQuasar--Kronos-Tokenizer-base` and `models--NeoQuasar--Kronos-small`)

---

## Task 12: Build the Docker image

- [ ] **Step 1: Build**

```bash
make build
```

This runs `docker compose build`. Expected duration: 5–15 minutes on first build (downloading pytorch base image + installing packages). Subsequent builds are fast due to layer caching.

Expected final lines:
```
 => [swingbot] exporting to image
 => => writing image sha256:...
 => => naming to docker.io/library/crypto-swing-bot-swingbot
```

- [ ] **Step 2: Verify image exists**

```bash
docker images | grep swingbot
```

Expected: one line with image name and a recent timestamp.

---

## Task 13: Start the container and verify web UI

- [ ] **Step 1: Start the bot**

```bash
make up
```

Expected: `Container crypto-swing-bot-swingbot-1  Started`

- [ ] **Step 2: Check logs for startup token**

```bash
make logs
```

Expected output within a few seconds:
```
[swingbot-web] token: <some-token>
[swingbot-web] http://0.0.0.0:8000
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

- [ ] **Step 3: Verify API responds**

```bash
curl -s http://localhost:8000/api/state | head -c 100
```

Expected: JSON response (not an error), e.g. `{"running":false,"mode":"paper",...}`

- [ ] **Step 4: Verify frontend serves**

```bash
curl -s http://localhost:8000/ | grep -i "swingbot\|react\|<div id"
```

Expected: HTML content containing the React app root.

- [ ] **Step 5: Verify GPU is visible inside container**

```bash
docker compose exec swingbot nvidia-smi
```

Expected: nvidia-smi output showing RTX 3050.

- [ ] **Step 6: Open dashboard in browser**

```bash
xdg-open http://localhost:8000
```

Log in with the token from Step 2. Navigate to Strategy → enable Kronos Forecast signal → Save profile.

---

## Self-Review

| Spec requirement | Task |
|-----------------|------|
| nvidia-container-toolkit installed | Task 1 |
| `SWINGBOT_HOST` env var in webmain.py | Task 2 |
| `SWINGBOT_DATA_DIR` env var in webmain.py | Task 2 |
| StaticFiles mount for frontend/dist in web.py | Task 3 |
| `_DIST` module-level var for test patching | Task 3 |
| Real Kronos constructor (`model + tokenizer + max_context`) | Task 4 |
| `x_timestamp` / `y_timestamp` as pd.Series | Task 4 |
| No `top_k` or `verbose` in predict call | Task 4 |
| FakePredictor updated to match real API | Task 4 |
| Pre-download script with correct NeoQuasar/ repo IDs | Task 5 |
| Multi-stage Dockerfile (node builder + pytorch runtime) | Task 6 |
| `frontend/dist` copied from builder stage | Task 6 |
| Kronos installed from GitHub in Dockerfile | Task 6 |
| `docker-compose.yml` with GPU runtime + volumes + env vars | Task 7 |
| `SWINGBOT_DATA_DIR=/data` in compose env | Task 7 |
| `~/.swingbot:/data` volume mount | Task 7 |
| `~/.cache/huggingface:/hf-cache` volume mount | Task 7 |
| `.dockerignore` excluding frontend/dist, .venv, .git, tests | Task 8 |
| Makefile with all targets | Task 9 |
| Model weights pre-downloaded before first run | Task 11 |
| Image builds successfully | Task 12 |
| Web UI accessible at http://localhost:8000 | Task 13 |
| GPU visible inside container | Task 13 |
