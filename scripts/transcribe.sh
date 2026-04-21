#!/usr/bin/env bash
# Uso: ./scripts/transcribe.sh <file_audio> [num_speakers]
# Esempio: ./scripts/transcribe.sh data/raw_audio/test.wav 3

set -euo pipefail

AUDIO="${1:?Argomento 1 richiesto: path audio}"
NUM_SPEAKERS="${2:-}"  # opzionale

# Derive output path: data/raw_audio/test.wav → data/transcripts/test.json
BASENAME=$(basename "${AUDIO%.*}")
OUTPUT="data/transcripts/${BASENAME}.json"

SPEAKERS_ARG=""
if [[ -n "${NUM_SPEAKERS}" ]]; then
    SPEAKERS_ARG="--num-speakers ${NUM_SPEAKERS}"
fi

echo "📼  Audio:   ${AUDIO}"
echo "📄  Output:  ${OUTPUT}"
echo "🎤  Speaker: ${NUM_SPEAKERS:-auto-detect}"
echo ""

docker compose run --rm whisper \
    --audio "/data/${AUDIO#data/}" \
    --output "/data/${OUTPUT#data/}" \
    --model large-v3 \
    --language it \
    ${SPEAKERS_ARG}
