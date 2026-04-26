#!/usr/bin/env bash
# Uso: ./scripts/ingest.sh <file> <caso_id> [tipo_atto]
# Esempi:
#   ./scripts/ingest.sh data/raw_docs/perizia.txt caso_001 perizia
#   ./scripts/ingest.sh data/transcripts/udienza.json caso_001

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
cd "${PROJECT_ROOT}"

INPUT_ARG="${1:?Argomento 1 richiesto: path file}"
CASO_ID="${2:?Argomento 2 richiesto: caso_id (es: caso_001)}"
TIPO_ATTO="${3:-documento}"

# Risolvi path assoluto
if [[ "${INPUT_ARG}" = /* ]]; then
    INPUT_ABS="${INPUT_ARG}"
else
    INPUT_ABS="${PROJECT_ROOT}/${INPUT_ARG}"
fi

# Mappa al path dentro il container
DATA_DIR="${PROJECT_ROOT}/data"
if [[ "${INPUT_ABS}" == "${DATA_DIR}"/* ]]; then
    INPUT_IN_CONTAINER="/data/${INPUT_ABS#${DATA_DIR}/}"
else
    echo "ERRORE: il file deve trovarsi dentro ${DATA_DIR}/" >&2
    exit 1
fi

echo "📄  File:     ${INPUT_ABS}"
echo "🗂️   Caso ID:  ${CASO_ID}"
echo "🏷️   Tipo:     ${TIPO_ATTO}"
echo ""

docker compose run --rm ingestion \
    --input "${INPUT_IN_CONTAINER}" \
    --caso-id "${CASO_ID}" \
    --tipo-atto "${TIPO_ATTO}"
