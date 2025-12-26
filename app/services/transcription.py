"""
Transcription service using OpenAI Whisper.

Handles audio/video transcription with optional word-level timestamps.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import whisper
import torch

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Cache the model globally to avoid reloading
_model = None


def get_model() -> whisper.Whisper:
    """Load and cache the Whisper model."""
    global _model
    if _model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Loading Whisper model '{settings.whisper_model}' on {device}")
        _model = whisper.load_model(settings.whisper_model, device=device)
        logger.info("Whisper model loaded successfully")
    return _model


@dataclass
class TranscriptSegment:
    """A segment of transcribed text with timing info."""
    start: float
    end: float
    text: str
    speaker: str | None = None  # For future speaker diarization


@dataclass
class TranscriptionResult:
    """Result of transcribing an audio/video file."""
    text: str
    language: str
    duration: float
    segments: list[TranscriptSegment]


def transcribe_file(file_path: str | Path) -> TranscriptionResult:
    """
    Transcribe an audio or video file using Whisper.

    Args:
        file_path: Path to the audio/video file

    Returns:
        TranscriptionResult with full text, language, and segments
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    logger.info(f"Transcribing file: {file_path}")

    model = get_model()

    # Transcribe with word timestamps for better segment accuracy
    result = model.transcribe(
        str(file_path),
        task="transcribe",
        verbose=False,
    )

    # Extract segments
    segments = [
        TranscriptSegment(
            start=seg["start"],
            end=seg["end"],
            text=seg["text"].strip(),
        )
        for seg in result.get("segments", [])
    ]

    # Calculate duration from last segment
    duration = segments[-1].end if segments else 0.0

    logger.info(
        f"Transcription complete: {len(segments)} segments, "
        f"{duration:.1f}s duration, language={result.get('language')}"
    )

    return TranscriptionResult(
        text=result["text"].strip(),
        language=result.get("language", "en"),
        duration=duration,
        segments=segments,
    )


def segments_to_json(segments: list[TranscriptSegment]) -> list[dict]:
    """Convert segments to JSON-serializable format for database storage."""
    return [
        {
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
            "speaker": seg.speaker,
        }
        for seg in segments
    ]
