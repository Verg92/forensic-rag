# syntax=docker/dockerfile:1
# Base leggera — PyTorch CPU per ingestion/embedding
# Dimensione ~300MB invece di 3GB+. Per ~1000 chunk la CPU è sufficiente.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SENTENCE_TRANSFORMERS_HOME=/app/model_cache/bge \
    HF_HOME=/app/model_cache/hf \
    GPU_BACKEND=cpu

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# PyTorch CPU — wheel molto più piccolo del CUDA
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu

COPY docker/ingestion/requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY src/ingestion/ ./ingestion/

ENTRYPOINT ["python3", "-m", "ingestion.ingest"]
