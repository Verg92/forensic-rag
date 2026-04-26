#!/usr/bin/env bash
# Uso: ./scripts/transcribe.sh <file_audio> <caso_id> [num_speakers]
# Esempio: ./scripts/transcribe.sh data/raw_audio/udienza.mp4 caso_001 2
#
# Output: data/raw_docs/<caso_id>/<nome_file>.json
# Pronto per ingest: ./scripts/ingest.sh data/raw_docs/<caso_id>/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
cd "${PROJECT_ROOT}"

AUDIO_ARG="${1:?Argomento 1 richiesto: path audio (dentro data/raw_audio/)}"
CASO_ID="${2:?Argomento 2 richiesto: caso_id (es: caso_001)}"
NUM_SPEAKERS="${3:-}"

# Risolvi path assoluto dell'audio
if [[ "${AUDIO_ARG}" = /* ]]; then
    AUDIO_ABS="${AUDIO_ARG}"
else
    AUDIO_ABS="${PROJECT_ROOT}/${AUDIO_ARG}"
fi

DATA_DIR="${PROJECT_ROOT}/data"
if [[ "${AUDIO_ABS}" != "${DATA_DIR}"/* ]]; then
    echo "ERRORE: il file deve trovarsi dentro ${DATA_DIR}/" >&2
    exit 1
fi

AUDIO_IN_CONTAINER="/data/${AUDIO_ABS#${DATA_DIR}/}"
BASENAME=$(basename "${AUDIO_ABS%.*}")

# Output diretto nella cartella del caso
OUTPUT_DIR="${PROJECT_ROOT}/data/raw_docs/${CASO_ID}"
mkdir -p "${OUTPUT_DIR}"
OUTPUT_IN_CONTAINER="/data/raw_docs/${CASO_ID}/${BASENAME}.json"

SPEAKERS_ARG=""
if [[ -n "${NUM_SPEAKERS}" ]]; then
    SPEAKERS_ARG="--num-speakers ${NUM_SPEAKERS}"
fi

echo "Audio:    ${AUDIO_ABS}"
echo "Caso:     ${CASO_ID}"
echo "Output:   ${OUTPUT_DIR}/${BASENAME}.json"
echo "Speaker:  ${NUM_SPEAKERS:-auto-detect}"
echo ""

docker compose run --rm whisper \
    --audio "${AUDIO_IN_CONTAINER}" \
    --output "${OUTPUT_IN_CONTAINER}" \
    --model large-v3 \
    --language it \
    ${SPEAKERS_ARG}
