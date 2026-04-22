#!/usr/bin/env bash
# Uso: ./scripts/transcribe.sh <file_audio> [num_speakers]
# Esempio: ./scripts/transcribe.sh data/raw_audio/test.wav 3

set -euo pipefail

# Spostati sempre nella root del progetto (cartella padre di scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
cd "${PROJECT_ROOT}"

AUDIO_ARG="${1:?Argomento 1 richiesto: path audio}"
NUM_SPEAKERS="${2:-}"

# Risolvi il path assoluto dell'audio sull'host
if [[ "${AUDIO_ARG}" = /* ]]; then
    AUDIO_ABS="${AUDIO_ARG}"
else
    AUDIO_ABS="${PROJECT_ROOT}/${AUDIO_ARG}"
fi

# Il volume Docker monta ./data → /data dentro il container.
# Calcola il path dentro il container strippando il prefix della data dir host.
DATA_DIR="${PROJECT_ROOT}/data"
if [[ "${AUDIO_ABS}" != "${DATA_DIR}"/* ]]; then
    echo "ERRORE: il file deve trovarsi dentro ${DATA_DIR}/" >&2
    exit 1
fi
AUDIO_IN_CONTAINER="/data/${AUDIO_ABS#${DATA_DIR}/}"

BASENAME=$(basename "${AUDIO_ABS%.*}")
OUTPUT_IN_CONTAINER="/data/transcripts/${BASENAME}.json"

SPEAKERS_ARG=""
if [[ -n "${NUM_SPEAKERS}" ]]; then
    SPEAKERS_ARG="--num-speakers ${NUM_SPEAKERS}"
fi

echo "📼  Audio:   ${AUDIO_ABS}"
echo "📄  Output:  ${PROJECT_ROOT}/data/transcripts/${BASENAME}.json"
echo "🎤  Speaker: ${NUM_SPEAKERS:-auto-detect}"
echo ""

docker compose run --rm whisper \
    --audio "${AUDIO_IN_CONTAINER}" \
    --output "${OUTPUT_IN_CONTAINER}" \
    --model large-v3 \
    --language it \
    ${SPEAKERS_ARG}
