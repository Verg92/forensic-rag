from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Chunk:
    chunk_id: str
    text: str
    metadata: dict
