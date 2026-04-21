# ─────────────────────────────────────────────────────────────
#  Forensic RAG — Whisper + pyannote transcription container
#  Build args:
#    GPU_BACKEND=rocm|cuda   (default: rocm)
#    TORCH_ROCM_VERSION      (default: rocm6.2)
#    TORCH_CUDA_VERSION      (default: cu121)
# ─────────────────────────────────────────────────────────────

ARG GPU_BACKEND=rocm

# ── Base comune ───────────────────────────────────────────────
FROM ubuntu:22.04 AS base-common

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3-pip \
        ffmpeg \
        libsndfile1 \
        libgomp1 \
        git \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && python3 -m pip install --upgrade pip

# ── Stage ROCm: installa PyTorch con backend ROCm ─────────────
FROM base-common AS base-rocm

ARG TORCH_ROCM_VERSION=rocm6.2

# Variabili ROCm — necessarie sia in build che a runtime
ENV HIP_VISIBLE_DEVICES=0 \
    ROCR_VISIBLE_DEVICES=0 \
    HSA_OVERRIDE_GFX_VERSION=12.0.0 \
    GPU_BACKEND=rocm

RUN pip install --no-cache-dir \
    torch==2.5.1 \
    torchaudio==2.5.1 \
    --index-url https://download.pytorch.org/whl/${TORCH_ROCM_VERSION}

# ── Stage CUDA: installa PyTorch con backend CUDA ─────────────
FROM base-common AS base-cuda

ARG TORCH_CUDA_VERSION=cu124

ENV GPU_BACKEND=cuda

RUN pip install --no-cache-dir \
    torch==2.5.1 \
    torchaudio==2.5.1 \
    --index-url https://download.pytorch.org/whl/${TORCH_CUDA_VERSION}

# ── Stage finale: dipendenze applicative sopra il backend ─────
FROM base-${GPU_BACKEND} AS final

WORKDIR /app

# Cache HuggingFace separata (montata come volume)
ENV HF_HOME=/app/model_cache \
    TRANSFORMERS_CACHE=/app/model_cache

# Layer separato: openai-whisper è lento da installare, isolarlo evita
# di reinstallarlo ogni volta che cambia requirements.txt
RUN pip install --no-cache-dir setuptools wheel && \
    pip install --no-cache-dir --no-build-isolation openai-whisper==20231117

COPY docker/whisper/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/transcription/ ./transcription/

ENTRYPOINT ["python3", "-m", "transcription.pipeline"]
