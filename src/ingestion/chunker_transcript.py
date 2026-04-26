"""
chunker_transcript.py — Spezza un JSON di trascrizione in chunk indicizzabili.

Ogni utterance diventa un chunk. Utterance molto lunghe (>800 parole) vengono
spezzate per frase per non superare il contesto dell'embedder.
"""
from __future__ import annotations

import json
from pathlib import Path

from ingestion.chunks import Chunk

_MAX_WORDS = 800


def _split_long_utterance(text: str, base_id: str, metadata: dict) -> list[Chunk]:
    words = text.split()
    if len(words) <= _MAX_WORDS:
        return [Chunk(chunk_id=base_id, text=text, metadata=metadata)]

    sentences = text.replace(". ", ".\n").replace("! ", "!\n").replace("? ", "?\n").split("\n")
    chunks, buf, part = [], "", 0
    for sentence in sentences:
        if len((buf + " " + sentence).split()) > _MAX_WORDS and buf:
            m = {**metadata, "part": part}
            chunks.append(Chunk(chunk_id=f"{base_id}_p{part}", text=buf.strip(), metadata=m))
            buf, part = sentence, part + 1
        else:
            buf = (buf + " " + sentence).strip()
    if buf:
        m = {**metadata, "part": part}
        chunks.append(Chunk(chunk_id=f"{base_id}_p{part}", text=buf.strip(), metadata=m))
    return chunks


def chunk_transcript(json_path: str, caso_id: str) -> list[Chunk]:
    path = Path(json_path)
    doc_id = path.stem

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    chunks: list[Chunk] = []
    for i, utt in enumerate(data["utterances"]):
        text = utt["text"].strip()
        if not text:
            continue
        base_id = f"{caso_id}__{doc_id}__{i:04d}"
        metadata = {
            "caso_id": caso_id,
            "doc_id": doc_id,
            "source_type": "transcript",
            "chunk_index": i,
            "speaker": utt["speaker"],
            "start": utt["start"],
            "end": utt["end"],
        }
        chunks.extend(_split_long_utterance(text, base_id, metadata))

    return chunks
