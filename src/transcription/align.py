"""
align.py — Fonde output Whisper con diarizzazione pyannote.

Strategia: per ogni segmento Whisper, trova il turno speaker
con la massima sovrapposizione temporale. Poi aggrega segmenti
consecutivi dello stesso speaker in utterance.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WhisperSegment:
    start: float
    end: float
    text: str


@dataclass
class SpeakerTurn:
    start: float
    end: float
    speaker: str


@dataclass
class Utterance:
    speaker: str
    start: float
    end: float
    text: str


def _overlap(a_start: float, a_end: float,
             b_start: float, b_end: float) -> float:
    """Durata della sovrapposizione tra due intervalli."""
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def assign_speakers(
    segments: list[WhisperSegment],
    turns: list[SpeakerTurn],
    min_overlap_ratio: float = 0.3,
) -> list[tuple[WhisperSegment, str]]:
    """
    Assegna un speaker a ogni segmento Whisper.

    Se nessun turno speaker ha sovrapposizione >= min_overlap_ratio
    rispetto alla durata del segmento, assegna "UNKNOWN".
    """
    assigned: list[tuple[WhisperSegment, str]] = []

    for seg in segments:
        seg_duration = seg.end - seg.start
        if seg_duration <= 0:
            assigned.append((seg, "UNKNOWN"))
            continue

        best_speaker = "UNKNOWN"
        best_overlap = 0.0

        for turn in turns:
            ov = _overlap(seg.start, seg.end, turn.start, turn.end)
            if ov > best_overlap:
                best_overlap = ov
                best_speaker = turn.speaker

        # Scarta assegnazioni con sovrapposizione troppo bassa
        if best_overlap / seg_duration < min_overlap_ratio:
            best_speaker = "UNKNOWN"

        assigned.append((seg, best_speaker))

    return assigned


def merge_utterances(
    assigned: list[tuple[WhisperSegment, str]],
    gap_threshold: float = 0.8,
) -> list[Utterance]:
    """
    Aggrega segmenti consecutivi dello stesso speaker in utterance.

    gap_threshold: se il silenzio tra due segmenti dello stesso speaker
    supera questo valore (secondi), crea una nuova utterance.
    """
    if not assigned:
        return []

    utterances: list[Utterance] = []
    current_seg, current_speaker = assigned[0]
    current_texts = [current_seg.text.strip()]
    current_start = current_seg.start
    current_end = current_seg.end

    for seg, speaker in assigned[1:]:
        gap = seg.start - current_end
        same_speaker = (speaker == current_speaker)
        small_gap = (gap <= gap_threshold)

        if same_speaker and small_gap:
            # Continua l'utterance corrente
            current_texts.append(seg.text.strip())
            current_end = seg.end
        else:
            # Chiudi utterance corrente, apri nuova
            utterances.append(Utterance(
                speaker=current_speaker,
                start=round(current_start, 3),
                end=round(current_end, 3),
                text=" ".join(current_texts),
            ))
            current_speaker = speaker
            current_texts = [seg.text.strip()]
            current_start = seg.start
            current_end = seg.end

    # Chiudi l'ultima utterance
    utterances.append(Utterance(
        speaker=current_speaker,
        start=round(current_start, 3),
        end=round(current_end, 3),
        text=" ".join(current_texts),
    ))

    return utterances
