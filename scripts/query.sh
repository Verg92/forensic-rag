#!/usr/bin/env bash
# Uso: ./scripts/query.sh "domanda" [top_k] [caso_id]
# Esempio: ./scripts/query.sh "Il padre ha fatto il parent training?" 5 caso_001

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
cd "${PROJECT_ROOT}"

QUERY="${1:?Argomento 1 richiesto: domanda}"
TOP_K="${2:-5}"
CASO_ID="${3:-}"

CASO_ARG=""
if [[ -n "${CASO_ID}" ]]; then
    CASO_ARG="--caso-id ${CASO_ID}"
fi

docker compose run --rm --entrypoint python3 ingestion \
    -m ingestion.retrieval \
    "${QUERY}" \
    --top-k "${TOP_K}" \
    ${CASO_ARG}
