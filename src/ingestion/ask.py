"""
ask.py — RAG completo: retrieval + LLM (Ollama) + risposta con citazioni.

Uso da CLI:
    python3 -m ingestion.ask "domanda" [--caso-id caso_001] [--top-k 5]
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

import requests

from ingestion.retrieval import search, SearchResult

log = logging.getLogger(__name__)

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
LLM_MODEL  = os.environ.get("LLM_MODEL",  "qwen2.5:3b-instruct-q4_K_M")


# ── Formatting ────────────────────────────────────────────────

def _source_label(meta: dict) -> str:
    if meta.get("source_type") == "transcript":
        m, s = divmod(int(meta.get("start", 0)), 60)
        return f"Trascrizione, {meta.get('speaker','?')}, {m:02d}:{s:02d}"
    return f"{meta.get('tipo_atto','Documento').capitalize()}: {meta.get('doc_id','?')}"


def _build_prompt(query: str, chunks: list[SearchResult]) -> str:
    context = ""
    for i, chunk in enumerate(chunks, 1):
        context += f"\n[FONTE {i} — {_source_label(chunk.metadata)}]\n{chunk.text}\n"

    return f"""Sei un assistente specializzato in analisi di documenti legali e psicologici.
Rispondi in italiano in modo preciso e professionale, basandoti ESCLUSIVAMENTE sui documenti forniti.
Per ogni affermazione indica la fonte con [FONTE N].
Se l'informazione non è presente nei documenti forniti, dillo esplicitamente senza inventare.

---
DOCUMENTI:
{context}
---

DOMANDA: {query}

RISPOSTA:"""


# ── Ollama ────────────────────────────────────────────────────

def _check_ollama() -> bool:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        return r.status_code == 200
    except requests.exceptions.ConnectionError:
        return False


def _model_available(model: str) -> bool:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        return any(model in m for m in models)
    except Exception:
        return False


def _call_ollama(prompt: str) -> str:
    log.info(f"Chiamata Ollama ({LLM_MODEL})...")
    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": LLM_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,   # bassa per risposte fattuali
                "num_predict": 512,
            },
        },
        timeout=180,
    )
    response.raise_for_status()
    return response.json()["response"].strip()


# ── Main ──────────────────────────────────────────────────────

def ask(query: str, caso_id: str = None, top_k: int = 5) -> None:
    if not _check_ollama():
        print(f"\nERRORE: Ollama non raggiungibile su {OLLAMA_URL}")
        print("Avvia il servizio con: docker compose up -d ollama")
        sys.exit(1)

    if not _model_available(LLM_MODEL):
        print(f"\nERRORE: modello '{LLM_MODEL}' non trovato in Ollama.")
        print(f"Scaricalo con: docker compose exec ollama ollama pull {LLM_MODEL}")
        sys.exit(1)

    # Retrieval
    log.info(f"Ricerca: '{query}'")
    chunks = search(query, top_k=top_k, caso_id=caso_id)

    if not chunks:
        print("\nNessun documento rilevante trovato per questa domanda.")
        return

    # Risposta LLM
    prompt   = _build_prompt(query, chunks)
    risposta = _call_ollama(prompt)

    # Output
    print(f"\n{'='*70}")
    print(f"  Domanda: {query}")
    print(f"{'='*70}\n")
    print(risposta)
    print(f"\n{'─'*70}")
    print("  Fonti usate:")
    for i, chunk in enumerate(chunks, 1):
        print(f"  [{i}] {_source_label(chunk.metadata)}  (score {chunk.score})")
    print()


def main() -> None:
    logging.basicConfig(level=logging.WARNING)

    p = argparse.ArgumentParser(description="RAG: domanda → retrieval → risposta LLM")
    p.add_argument("query",              help="Domanda in italiano")
    p.add_argument("--caso-id",          default=None)
    p.add_argument("--top-k", type=int,  default=5)
    args = p.parse_args()

    ask(args.query, caso_id=args.caso_id, top_k=args.top_k)


if __name__ == "__main__":
    main()
