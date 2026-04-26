"""
retrieval.py — Ricerca ibrida su ChromaDB (semantico) + BM25 (keyword).

Uso come modulo:
    from ingestion.retrieval import search
    results = search("Il padre ha fatto il parent training?", top_k=5)

Uso da CLI:
    python3 -m ingestion.retrieval "domanda" [--top-k 5] [--caso-id caso_001]
"""
from __future__ import annotations

import argparse
import logging
import os
import pickle
from dataclasses import dataclass
from pathlib import Path

import torch

log = logging.getLogger(__name__)

CHROMA_PATH = os.environ.get("CHROMA_PATH", "/indexes/chroma")
BM25_PATH   = os.environ.get("BM25_PATH",   "/indexes/bm25")
BGE_MODEL   = os.environ.get("BGE_MODEL",   "BAAI/bge-m3")
COLLECTION  = "caso_corrente"


@dataclass
class SearchResult:
    chunk_id: str
    text: str
    metadata: dict
    score: float


# ── Device ────────────────────────────────────────────────────

def _device() -> str:
    if os.environ.get("GPU_BACKEND") == "cpu":
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


# ── Embedder (singleton per sessione) ─────────────────────────

_embedder = None

def _get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        log.info(f"Carico embedder '{BGE_MODEL}'...")
        _embedder = SentenceTransformer(BGE_MODEL, device=_device())
    return _embedder


# ── Ricerca semantica (ChromaDB) ──────────────────────────────

def _semantic(query: str, top_k: int) -> list[tuple[str, str, dict, float]]:
    import chromadb
    client     = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_collection(COLLECTION)

    total = collection.count()
    if total == 0:
        return []

    model    = _get_embedder()
    vec      = model.encode([query], normalize_embeddings=True).tolist()
    results  = collection.query(
        query_embeddings=vec,
        n_results=min(top_k, total),
        include=["documents", "metadatas", "distances"],
    )

    out = []
    for chunk_id, doc, meta, dist in zip(
        results["ids"][0],
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        # ChromaDB cosine: distance 0=identico, 2=opposto → similarità 0-1
        out.append((chunk_id, doc, meta, 1.0 - dist / 2.0))
    return out


# ── Ricerca keyword (BM25) ────────────────────────────────────

def _keyword(query: str, top_k: int) -> list[tuple[str, str, dict, float]]:
    index_file = Path(BM25_PATH) / "index.pkl"
    if not index_file.exists():
        return []

    with open(index_file, "rb") as f:
        data = pickle.load(f)

    import re
    tokens = re.sub(r"[^\w\s]", " ", query.lower()).split()
    scores = data["bm25"].get_scores(tokens)
    max_s  = max(scores) if max(scores) > 0 else 1.0

    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
    return [
        (data["ids"][i], data["documents"][i], data["metadatas"][i], s / max_s)
        for i, s in ranked if s > 0
    ]


# ── Reciprocal Rank Fusion ────────────────────────────────────

def _rrf(
    semantic : list[tuple],
    keyword  : list[tuple],
    k        : int   = 60,
    w_sem    : float = 0.6,
    w_kw     : float = 0.4,
) -> list[SearchResult]:
    pool: dict[str, dict] = {}

    for rank, (cid, text, meta, _) in enumerate(semantic):
        if cid not in pool:
            pool[cid] = {"text": text, "meta": meta, "score": 0.0}
        pool[cid]["score"] += w_sem / (k + rank + 1)

    for rank, (cid, text, meta, _) in enumerate(keyword):
        if cid not in pool:
            pool[cid] = {"text": text, "meta": meta, "score": 0.0}
        pool[cid]["score"] += w_kw / (k + rank + 1)

    ranked = sorted(pool.items(), key=lambda x: x[1]["score"], reverse=True)
    return [
        SearchResult(cid, d["text"], d["meta"], round(d["score"], 4))
        for cid, d in ranked
    ]


# ── Entry point pubblico ──────────────────────────────────────

def search(
    query   : str,
    top_k   : int  = 5,
    caso_id : str  = None,
) -> list[SearchResult]:
    """Ricerca ibrida. Restituisce i top_k chunk più rilevanti."""
    sem = _semantic(query, top_k=top_k * 2)
    kw  = _keyword(query,  top_k=top_k * 2)
    results = _rrf(sem, kw)

    if caso_id:
        results = [r for r in results if r.metadata.get("caso_id") == caso_id]

    return results[:top_k]


# ── CLI ───────────────────────────────────────────────────────

def _fmt_source(meta: dict) -> str:
    if meta.get("source_type") == "transcript":
        m, s = divmod(int(meta.get("start", 0)), 60)
        return f"[trascrizione · {meta.get('speaker','?')} · {m:02d}:{s:02d}]"
    return f"[{meta.get('tipo_atto','documento')} · {meta.get('doc_id','?')}]"


def main() -> None:
    logging.basicConfig(level=logging.WARNING)

    p = argparse.ArgumentParser(description="Ricerca ibrida su indice caso")
    p.add_argument("query",               help="Domanda o testo da cercare")
    p.add_argument("--top-k",  type=int,  default=5)
    p.add_argument("--caso-id",           default=None)
    args = p.parse_args()

    results = search(args.query, top_k=args.top_k, caso_id=args.caso_id)

    if not results:
        print("Nessun risultato trovato.")
        return

    print(f"\n{'='*70}")
    print(f"  Query: {args.query}")
    print(f"{'='*70}\n")

    for i, r in enumerate(results, 1):
        print(f"[{i}] score={r.score}  {_fmt_source(r.metadata)}")
        print(f"    {r.text[:200]}{'...' if len(r.text) > 200 else ''}")
        print()


if __name__ == "__main__":
    main()
