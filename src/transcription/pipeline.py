"""
pipeline.py — Entry point per la trascrizione diarizzata.

Uso:
    python3 -m transcription.pipeline \
        --audio /data/raw_audio/udienza.wav \
        --output /data/transcripts/udienza.json \
        --hf-token $HF_TOKEN \
        [--model large-v3] \
        [--language it] \
        [--num-speakers 3]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import torch
import whisper
from pyannote.audio import Pipeline

from transcription.align import (
    WhisperSegment,
    SpeakerTurn,
    assign_speakers,
    merge_utterances,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Estensioni supportate ──────────────────────────────────────

_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".ts", ".mts"}
_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus"}


# ── Rilevamento device ─────────────────────────────────────────

def get_device() -> str:
    gpu_backend = os.environ.get("GPU_BACKEND", "rocm")
    if gpu_backend == "cuda":
        if torch.cuda.is_available():
            log.info(f"CUDA disponibile: {torch.cuda.get_device_name(0)}")
            return "cuda"
        log.warning("CUDA non disponibile, fallback CPU.")
        return "cpu"
    # ROCm: gfx1200 (RDNA4) non supportato da PyTorch ROCm stabile, forza CPU
    log.warning("ROCm: gfx1200 non ancora supportato, uso CPU.")
    return "cpu"


# ── Estrazione audio da video ──────────────────────────────────

def _run_ffmpeg(input_path: str, output_path: str) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        "-vn",
        output_path,
    ]
    log.info(f"ffmpeg: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error(f"ffmpeg fallito:\n{result.stderr}")
        raise RuntimeError(f"ffmpeg ha restituito exit code {result.returncode}")
    size_mb = Path(output_path).stat().st_size / 1_048_576
    log.info(f"Audio estratto: {size_mb:.1f} MB")


def prepare_audio(input_path: str, tmp_dir: str) -> tuple[str, bool]:
    suffix = Path(input_path).suffix.lower()
    if suffix in _AUDIO_EXTENSIONS:
        log.info(f"File audio rilevato ({suffix}), nessuna conversione necessaria.")
        return input_path, False
    out_path = str(Path(tmp_dir) / (Path(input_path).stem + "_audio.wav"))
    log.info(f"File video/sconosciuto ({suffix}), estraggo audio → {out_path}")
    _run_ffmpeg(input_path, out_path)
    return out_path, True


# ── Checkpoint trascrizione ────────────────────────────────────

def _checkpoint_path(output_path: str) -> Path:
    """Percorso del file checkpoint segments, accanto all'output finale."""
    p = Path(output_path)
    return p.parent / (p.stem + "_segments_checkpoint.json")


def save_segments_checkpoint(segments: list[WhisperSegment], output_path: str) -> None:
    cp = _checkpoint_path(output_path)
    data = [{"start": s.start, "end": s.end, "text": s.text} for s in segments]
    with open(cp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"Checkpoint segmenti salvato: {cp}")


def load_segments_checkpoint(output_path: str) -> list[WhisperSegment] | None:
    cp = _checkpoint_path(output_path)
    if not cp.exists():
        return None
    log.info(f"Checkpoint trovato: {cp} — salto trascrizione Whisper.")
    with open(cp, encoding="utf-8") as f:
        data = json.load(f)
    segments = [WhisperSegment(start=s["start"], end=s["end"], text=s["text"]) for s in data]
    log.info(f"Segmenti caricati dal checkpoint: {len(segments)}")
    return segments


# ── Trascrizione con Whisper ───────────────────────────────────

def transcribe(
    audio_path: str,
    model_name: str,
    language: str,
    device: str,
    output_path: str,
) -> list[WhisperSegment]:
    # Prova a caricare checkpoint
    segments = load_segments_checkpoint(output_path)
    if segments is not None:
        return segments

    log.info(f"Carico modello Whisper '{model_name}' su {device}...")
    model = whisper.load_model(model_name, device=device)

    log.info(f"Trascrivo '{audio_path}' (lingua: {language})...")
    t0 = time.time()
    result = model.transcribe(
        audio_path,
        language=language,
        word_timestamps=False,
        verbose=False,
        fp16=(device == "cuda"),
    )
    elapsed = time.time() - t0
    log.info(f"Trascrizione completata in {elapsed:.1f}s")

    segments = [
        WhisperSegment(start=s["start"], end=s["end"], text=s["text"])
        for s in result["segments"]
    ]
    log.info(f"Segmenti estratti: {len(segments)}")

    # Salva checkpoint subito
    save_segments_checkpoint(segments, output_path)
    return segments


# ── Diarizzazione con pyannote ─────────────────────────────────

def diarize(
    audio_path: str,
    hf_token: str,
    device: str,
    num_speakers: int | None = None,
) -> list[SpeakerTurn]:
    log.info("Carico pipeline pyannote speaker-diarization-3.1...")
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=hf_token,
    )
    pipeline = pipeline.to(torch.device(device))

    log.info(f"Dirizzo '{audio_path}'"
             + (f" (num_speakers={num_speakers})" if num_speakers else "") + "...")
    t0 = time.time()

    params = {}
    if num_speakers is not None:
        params["num_speakers"] = num_speakers

    diarization = pipeline(audio_path, **params)
    elapsed = time.time() - t0
    log.info(f"Diarizzazione completata in {elapsed:.1f}s")

    turns = [
        SpeakerTurn(start=turn.start, end=turn.end, speaker=label)
        for turn, _, label in diarization.itertracks(yield_label=True)
    ]
    speakers = sorted(set(t.speaker for t in turns))
    log.info(f"Speaker rilevati: {len(speakers)} → {speakers}")
    return turns


# ── Salvataggio output ─────────────────────────────────────────

def save_output(utterances, output_path: str, audio_path: str, model_name: str) -> None:
    output = {
        "metadata": {
            "audio_file": str(Path(audio_path).name),
            "original_format": Path(audio_path).suffix.lower(),
            "whisper_model": model_name,
            "diarization_model": "pyannote/speaker-diarization-3.1",
            "schema_version": "1.0",
        },
        "utterances": [
            {"speaker": u.speaker, "start": u.start, "end": u.end, "text": u.text}
            for u in utterances
        ],
    }
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    log.info(f"Output salvato in '{output_path}' ({len(utterances)} utterances)")

    # Rimuovi checkpoint — non serve più
    cp = _checkpoint_path(output_path)
    if cp.exists():
        cp.unlink()
        log.info(f"Checkpoint rimosso: {cp}")


# ── Main ───────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Transcribe + diarize audio")
    p.add_argument("--audio", required=True, help="Path audio/video input")
    p.add_argument("--output", required=True, help="Path JSON output")
    p.add_argument("--hf-token", default=os.environ.get("HF_TOKEN", ""),
                   help="HuggingFace token (o env HF_TOKEN)")
    p.add_argument("--model", default="large-v3",
                   help="Modello Whisper (default: large-v3)")
    p.add_argument("--language", default="it",
                   help="Lingua audio ISO-639-1 (default: it)")
    p.add_argument("--num-speakers", type=int, default=None,
                   help="Numero speaker noti (opzionale ma migliora qualità)")
    p.add_argument("--dry-run", action="store_true",
                   help="Testa solo il device, non trascrive")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    device = get_device()

    if args.dry_run:
        log.info("Dry-run completato — device OK, uscita.")
        sys.exit(0)

    if not args.hf_token:
        log.error("HF_TOKEN mancante. Vedi README per setup pyannote.")
        sys.exit(1)

    if not Path(args.audio).exists():
        log.error(f"File audio non trovato: {args.audio}")
        sys.exit(1)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=Path(args.output).parent) as tmp_dir:
        audio_path, was_converted = prepare_audio(args.audio, tmp_dir)

        segments = transcribe(
            audio_path=audio_path,
            model_name=args.model,
            language=args.language,
            device=device,
            output_path=args.output,
        )

        turns = diarize(
            audio_path=audio_path,
            hf_token=args.hf_token,
            device=device,
            num_speakers=args.num_speakers,
        )

    assigned = assign_speakers(segments, turns)
    utterances = merge_utterances(assigned)
    save_output(
        utterances=utterances,
        output_path=args.output,
        audio_path=args.audio,
        model_name=args.model,
    )


if __name__ == "__main__":
    main()
