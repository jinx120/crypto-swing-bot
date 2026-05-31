# Docker GPU Deployment — Design Spec

**Date:** 2026-05-31  
**Status:** Approved  
**Approach:** Single container (multi-stage build) + pre-download script (Approach C)

---

## Goal

Package the full swingbot stack — FastAPI backend, React dashboard, Kronos forecast signal — into a single Docker container that uses the host NVIDIA GPU for PyTorch inference. Kronos model weights are pre-downloaded to the host HuggingFace cache before the first container start so there are no surprise multi-GB downloads at bot startup.

---

## Host Prerequisites (done once, before anything else)

### 1. nvidia-container-toolkit

Currently missing from this machine (Docker runtime shows only `runc`). Required for `--gpus all` / `runtime: nvidia` in docker-compose.

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

Verify: `docker info | grep -i runtime` should list `nvidia`.

### 2. Kronos model pre-download

Run once on the host before `docker compose up`:

```bash
make download-model
```

This populates `~/.cache/huggingface/` with Kronos weights. The compose file bind-mounts that directory into the container, so subsequent starts are instant.

---

## New Files

| Path | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage build: Node frontend builder → PyTorch runtime |
| `docker-compose.yml` | GPU runtime, volume mounts, port, env vars |
| `.dockerignore` | Exclude `.venv`, `node_modules`, `frontend/dist`, `tests`, `.git` |
| `scripts/download_model.py` | Pre-download Kronos weights via HuggingFace Hub |
| `Makefile` | Convenience targets: `build`, `up`, `down`, `download-model`, `logs` |

---

## Modified Files

| Path | Change |
|------|--------|
| `src/swingbot/webmain.py` | Read `SWINGBOT_HOST` env var (default `127.0.0.1`); Docker sets it to `0.0.0.0` |
| `src/swingbot/web.py` | Mount `frontend/dist` as `StaticFiles` at `/`; guarded by `os.path.isdir` so tests/dev are unaffected |
| `src/swingbot/signals/kronos_adapter.py` | Fix `from_profile()` with real `KronosPredictor` constructor (verified against Kronos README during implementation) |

---

## Dockerfile (multi-stage)

### Stage 1 — frontend builder

Base: `node:20-slim`

Steps:
1. `WORKDIR /build`
2. Copy `frontend/package.json`, `frontend/package-lock.json` (if present)
3. `npm ci`
4. Copy rest of `frontend/`
5. `npm run build`

Output artifact: `/build/dist`

### Stage 2 — runtime

Base: `pytorch/pytorch:2.6.0-cuda12.6-cudnn9-runtime`

This image ships with PyTorch + CUDA 12.6 + cuDNN 9. Compatible with host driver 580.159.03 (supports CUDA 13.0, forward-compatible with 12.x).

Steps:
1. `WORKDIR /app`
2. Install system packages: `git`, `libgomp1` (OpenMP, required by some torch ops)
3. Copy `pyproject.toml`, `src/`
4. `pip install -e ".[kronos]"` — installs swingbot + torch (already present in base, no-op re-install) + huggingface_hub + einops + safetensors + tqdm
5. `pip install git+https://github.com/shiyu-coder/Kronos.git` — installs Kronos package
6. Copy built frontend from Stage 1: `--from=builder /build/dist /app/frontend/dist`
7. `ENV HF_HOME=/hf-cache`
8. `ENV SWINGBOT_HOST=0.0.0.0`
9. `EXPOSE 8000`
10. `CMD ["swingbot-web"]`

Final image contains no Node.js or build tooling. Frontend dist is baked in.

---

## docker-compose.yml

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

Volume notes:
- `~/.swingbot:/data` — existing SQLite DB, credentials, and token survive container rebuilds. `webmain.py` `DATA_DIR` must read `DATA_DIR = os.environ.get("SWINGBOT_DATA_DIR", os.path.expanduser("~/.swingbot"))` so it can be overridden to `/data` in Docker via env var.
- `~/.cache/huggingface:/hf-cache` — pre-downloaded Kronos weights. `HF_HOME=/hf-cache` tells HuggingFace Hub to use this path.

---

## Backend Changes

### `webmain.py`

Add `SWINGBOT_HOST` and `SWINGBOT_DATA_DIR` env var support:

```python
HOST = os.environ.get("SWINGBOT_HOST", "127.0.0.1")
DATA_DIR = os.environ.get("SWINGBOT_DATA_DIR", os.path.expanduser("~/.swingbot"))
# ...
uvicorn.run(app, host=HOST, port=8000)
```

### `web.py`

After all route registrations, at the bottom of `create_app()`:

```python
import pathlib
from fastapi.staticfiles import StaticFiles

_dist = pathlib.Path(__file__).parent.parent.parent / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
```

The `if _dist.is_dir()` guard means the API works in dev/test without a built frontend present. Routes registered before this mount take priority, so `/api/*` routes are unaffected.

### `kronos_adapter.py` — `from_profile()`

The current stub calls `KronosPredictor()` with no args, which is incorrect. During implementation, the actual constructor is verified against the [Kronos README](https://github.com/shiyu-coder/Kronos). Expected pattern based on HuggingFace convention:

```python
@classmethod
def from_profile(cls, params: dict) -> "KronosAdapter":
    _, _, KronosPredictor = _load_kronos()
    predictor = KronosPredictor.from_pretrained("shiyu-coder/Kronos-Base")
    return cls(
        predictor=predictor,
        pred_len=params.get("pred_len", 4),
        timeout_s=params.get("timeout_s", 30.0),
        T=params.get("T", 200),
        top_k=params.get("top_k", 5),
        top_p=params.get("top_p", 1.0),
        sample_count=params.get("sample_count", 10),
    )
```

Exact model ID (`"shiyu-coder/Kronos-Base"` or `"shiyu-coder/Kronos"`) confirmed from README during implementation.

---

## Pre-download Script

### `scripts/download_model.py`

```python
#!/usr/bin/env python3
"""Pre-download Kronos model weights to the HuggingFace cache.

Run once on the host before 'docker compose up':
    python scripts/download_model.py

Weights are saved to ~/.cache/huggingface/ (or $HF_HOME if set).
The docker-compose.yml bind-mounts this directory into the container,
so subsequent container starts require no network access for the model.
"""
from huggingface_hub import snapshot_download

REPO_ID = "shiyu-coder/Kronos-Base"  # verify exact ID against Kronos README

print(f"Downloading {REPO_ID} to HuggingFace cache...")
path = snapshot_download(repo_id=REPO_ID)
print(f"Done. Weights cached at: {path}")
```

---

## Makefile

```makefile
.PHONY: build up down logs download-model

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

download-model:
	pip install --quiet huggingface_hub
	python scripts/download_model.py
```

---

## .dockerignore

```
.git
.venv
__pycache__
*.pyc
*.pyo
node_modules
frontend/node_modules
frontend/dist
tests
docs
*.md
.env
```

`frontend/dist` is excluded because it is rebuilt inside the Docker multi-stage build; including it would make the build context unnecessarily large.

---

## Workflow

### First time

```bash
# 1. Install nvidia-container-toolkit (once per machine)
#    See "Host Prerequisites" section above.

# 2. Pre-download Kronos model weights
make download-model

# 3. Build and start
make build
make up

# 4. Open dashboard
xdg-open http://localhost:8000
# Token is printed in logs:
make logs | grep token
```

### Routine usage

```bash
make up         # start
make down       # stop
make logs       # tail logs
make build && make up   # rebuild after code changes
```

### Data and credentials

Stored in `~/.swingbot/` on the host — unaffected by container rebuilds. The auth token is generated once on first start and persists in `~/.swingbot/token`.

---

## What Is Not Changing

- Signal protocol, ConfluenceEngine, risk controls, broker adapters — unchanged.
- `StrategyProfile` — unchanged; Kronos params live in the `signals` dict as before.
- Test suite — all 130 tests continue to run without Docker or torch installed.
- `DATA_DIR` fallback default — if `SWINGBOT_DATA_DIR` is unset, `webmain.py` still uses `~/.swingbot` so local dev is unaffected.

---

## GPU Notes

- Host: NVIDIA RTX 3050 (8 GB VRAM), driver 580.159.03, CUDA 13.0
- Container base: `pytorch/pytorch:2.6.0-cuda12.6-cudnn9-runtime` (CUDA 12.6 ≤ 13.0 ✓)
- Kronos inference runs on GPU automatically when torch detects CUDA; the `KronosAdapter` does not need explicit `.to("cuda")` calls if Kronos handles device placement internally (verify during implementation)
- RTX 3050 8 GB is sufficient for inference on most foundation time-series models; if OOM occurs, reduce `sample_count` or `T` in the profile config
