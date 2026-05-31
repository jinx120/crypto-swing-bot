#!/usr/bin/env python3
"""Pre-download Kronos model weights to the HuggingFace cache.

Run once on the host before 'docker compose up':
    python scripts/download_model.py

Weights are saved to ~/.cache/huggingface/ (or $HF_HOME if set).
The docker-compose.yml bind-mounts this directory into the container
at /hf-cache, so subsequent container starts need no network access.

Models downloaded:
  - NeoQuasar/Kronos-Tokenizer-base  (tokenizer, small)
  - NeoQuasar/Kronos-small           (24.7M params, fast inference, good for RTX 3050)
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
