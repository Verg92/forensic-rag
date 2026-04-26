# syntax=docker/dockerfile:1
# Base ufficiale PyTorch — include già CUDA 12.4 + PyTorch 2.6.0
FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/model_cache \
    TRANSFORMERS_CACHE=/app/model_cache \
    GPU_BACKEND=cuda

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        libgomp1 \
        git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install setuptools wheel && \
    pip install --no-build-isolation openai-whisper==20231117

COPY docker/whisper/requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY src/transcription/ ./transcription/

ENTRYPOINT ["python3", "-m", "transcription.pipeline"]
