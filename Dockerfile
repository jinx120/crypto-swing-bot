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
