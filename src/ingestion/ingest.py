"""
ingest.py — Indicizza un documento o una trascrizione in ChromaDB + BM25.

Uso:
    python3 -m ingestion.ingest --input /data/raw_docs/perizia.txt \
        --caso-id caso_001 --tipo-atto perizia

    python3 -m ingestion.ingest --input /data/transcripts/udienza.json \
        --caso-id caso_001
"""
from __future__ import annotations

import argparse
import logging
import os
import pickle
import sys
from pathlib import Path

import torch

from ingestion.chunks import Chunk
from ingestion.chunker_doc import chunk_document
from ingestion.chunker_transcript import chunk_transcript

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

CHROMA_PATH = os.environ.get("CHROMA_PATH", "/indexes/chroma")
BM25_PATH = os.environ.get("BM25_PATH", "/indexes/bm25")
BGE_MODEL = os.environ.get("BGE_MODEL", "BAAI/bge-m3")
COLLECTION_NAME = "caso_corrente"


# ── Device ────────────────────────────────────────────────────────────────────

def get_device() -> str:
    if os.environ.get("GPU_BACKEND") == "cpu":
        log.info("Modalità CPU (ingestion container).")
        return "cpu"
    if torch.cuda.is_available():
        log.info(f"GPU: {torch.cuda.get_device_name(0)}")
        return "cuda"
    log.info("CUDA non disponibile, uso CPU.")
    return "cpu"


# ── Embedder ──────────────────────────────────────────────────────────────────

def load_embedder(device: str):
    from sentence_transformers import SentenceTransformer
    log.info(f"Carico embedder '{BGE_MODEL}'...")
    return SentenceTransformer(BGE_MODEL, device=device)


def embed(texts: list[str], model) -> list[list[float]]:
    log.info(f"Embedding {len(texts)} chunk...")
    vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
    return vecs.tolist()


# ── ChromaDB ──────────────────────────────────────────────────────────────────

def get_collection():
    import chromadb
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection(
        COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def ingest_to_chroma(chunks: list[Chunk], model) -> None:
    collection = get_collection()
    texts = [c.text for c in chunks]
    embeddings = embed(texts, model)
    collection.upsert(
        ids=[c.chunk_id for c in chunks],
        documents=texts,
        embeddings=embeddings,
        metadatas=[c.metadata for c in chunks],
    )
    log.info(f"ChromaDB: upsert di {len(chunks)} chunk. Totale collezione: {collection.count()}")


# ── BM25 ──────────────────────────────────────────────────────────────────────

def rebuild_bm25() -> None:
    from rank_bm25 import BM25Okapi
    collection = get_collection()
    result = collection.get(include=["documents", "metadatas"])
    docs = result["documents"]
    ids = result["ids"]
    metadatas = result["metadatas"]

    tokenized = [d.lower().split() for d in docs]
    bm25 = BM25Okapi(tokenized)

    Path(BM25_PATH).mkdir(parents=True, exist_ok=True)
    index_file = Path(BM25_PATH) / "index.pkl"
    with open(index_file, "wb") as f:
        pickle.dump({"bm25": bm25, "ids": ids, "documents": docs, "metadatas": metadatas}, f)
    log.info(f"BM25: indice ricostruito su {len(docs)} chunk totali.")


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Indicizza documenti e trascrizioni")
    p.add_argument("--input", required=True, help="Path file da indicizzare")
    p.add_argument("--caso-id", required=True, help="ID caso (es: caso_001)")
    p.add_argument("--tipo-atto", default="documento",
                   help="Tipo documento: perizia, verbale, relazione, ecc. Ignorato per trascrizioni.")
    p.add_argument("--dry-run", action="store_true",
                   help="Mostra i chunk senza indicizzare")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)

    if not input_path.exists():
        log.error(f"File non trovato: {input_path}")
        sys.exit(1)

    # Rileva tipo
    if input_path.suffix.lower() == ".json":
        log.info("Tipo: trascrizione")
        chunks = chunk_transcript(str(input_path), args.caso_id)
    else:
        log.info("Tipo: documento")
        chunks = chunk_document(str(input_path), args.caso_id, args.tipo_atto)

    log.info(f"Chunk prodotti: {len(chunks)}")

    if args.dry_run:
        for c in chunks:
            print(f"\n[{c.chunk_id}] {c.metadata}")
            print(c.text[:120] + ("..." if len(c.text) > 120 else ""))
        return

    device = get_device()
    model = load_embedder(device)
    ingest_to_chroma(chunks, model)
    rebuild_bm25()
    log.info("Ingestione completata.")


if __name__ == "__main__":
    main()
