"""
chunker_doc.py — Spezza un documento (TXT, PDF, DOCX) in chunk indicizzabili.

Strategia: split per paragrafo (doppio newline o newline singolo se non ci sono
doppi newline). Paragrafi troppo lunghi vengono spezzati per frase.
Heading Markdown (#) vengono usati come separatori, non come chunk.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ingestion.chunks import Chunk

_MAX_CHARS = 1200
_MIN_CHARS = 80   # chunk più corti vengono uniti al successivo


def _read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                pages = [page.extract_text() or "" for page in pdf.pages]
            return "\n\n".join(pages)
        except ImportError:
            raise RuntimeError("pdfplumber non installato — aggiungerlo a requirements.txt")
    if suffix in (".docx",):
        try:
            from docx import Document
            doc = Document(path)
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            raise RuntimeError("python-docx non installato — aggiungerlo a requirements.txt")
    # plain text (qualsiasi altra estensione o nessuna estensione)
    return path.read_text(encoding="utf-8")


def _split_text(text: str) -> list[str]:
    separator = "\n\n" if "\n\n" in text else "\n"
    raw_parts = text.split(separator)

    # Prima passata: raccogli parti non vuote e non heading
    candidates: list[str] = []
    for part in raw_parts:
        part = part.strip()
        if not part or part.startswith("#"):
            continue
        if len(part) <= _MAX_CHARS:
            candidates.append(part)
        else:
            # Spezza per frase i paragrafi troppo lunghi
            sentences = part.replace(". ", ".\n").replace("! ", "!\n").replace("? ", "?\n").split("\n")
            buf = ""
            for s in sentences:
                candidate = (buf + " " + s).strip()
                if len(candidate) > _MAX_CHARS and buf:
                    candidates.append(buf.strip())
                    buf = s
                else:
                    buf = candidate
            if buf.strip():
                candidates.append(buf.strip())

    # Seconda passata: unisci chunk troppo corti al successivo per dare contesto
    paragraphs: list[str] = []
    buf = ""
    for part in candidates:
        if not buf:
            buf = part
        elif len(buf) < _MIN_CHARS:
            buf = buf + "\n" + part
        elif len(buf + "\n" + part) <= _MAX_CHARS and len(part) < _MIN_CHARS:
            buf = buf + "\n" + part
        else:
            paragraphs.append(buf)
            buf = part
    if buf:
        paragraphs.append(buf)

    return paragraphs


def chunk_document(
    file_path: str,
    caso_id: str,
    tipo_atto: str,
    doc_id: Optional[str] = None,
) -> list[Chunk]:
    path = Path(file_path)
    doc_id = doc_id or path.stem

    text = _read_text(path)
    paragraphs = _split_text(text)

    chunks: list[Chunk] = []
    for i, para in enumerate(paragraphs):
        chunk_id = f"{caso_id}__{doc_id}__{i:04d}"
        metadata = {
            "caso_id": caso_id,
            "doc_id": doc_id,
            "source_type": "document",
            "tipo_atto": tipo_atto,
            "chunk_index": i,
        }
        chunks.append(Chunk(chunk_id=chunk_id, text=para, metadata=metadata))

    return chunks
