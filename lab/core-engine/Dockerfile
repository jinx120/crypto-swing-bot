FROM python:3.11-slim
WORKDIR /app
# Build context is the repo root so we can install the parent swingbot package.
COPY . /app
RUN pip install --no-cache-dir -e . && pip install --no-cache-dir -e lab/core-engine
ENV CORE_ENGINE_DATA=/data
VOLUME /data
CMD ["python", "-m", "core_engine", "run"]
