#!/usr/bin/env bash
# Uso: ./scripts/ask.sh "domanda" [caso_id] [top_k]
# Esempio: ./scripts/ask.sh "Il padre ha fatto il parent training?" caso_001

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
cd "${PROJECT_ROOT}"

QUERY="${1:?Argomento 1 richiesto: domanda}"
CASO_ID="${2:-}"
TOP_K="${3:-5}"

# Avvia Ollama se non è già in esecuzione
if ! docker compose ps ollama | grep -q "running"; then
    echo "Avvio Ollama..."
    docker compose up -d ollama
    echo "Attendo che Ollama sia pronto..."
    until docker compose exec ollama ollama list > /dev/null 2>&1; do
        sleep 2
    done
fi

# Scarica il modello se non è presente
MODEL="${LLM_MODEL:-qwen2.5:3b-instruct-q4_K_M}"
if ! docker compose exec ollama ollama list | grep -q "${MODEL%%:*}"; then
    echo "Scarico modello ${MODEL} (prima volta, ~2GB)..."
    docker compose exec ollama ollama pull "${MODEL}"
fi

CASO_ARG=""
if [[ -n "${CASO_ID}" ]]; then
    CASO_ARG="--caso-id ${CASO_ID}"
fi

docker compose run --rm --entrypoint python3 ingestion \
    -m ingestion.ask \
    "${QUERY}" \
    --top-k "${TOP_K}" \
    ${CASO_ARG}
