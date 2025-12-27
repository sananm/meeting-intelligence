"""
Transcription service using OpenAI Whisper.

Handles audio/video transcription with optional word-level timestamps.
"""

import logging
import ssl
import os
from dataclasses import dataclass
from pathlib import Path

import whisper
import torch

from app.core.config import get_settings

# Fix SSL certificate issues on macOS
# This is needed because Python on macOS doesn't use system certificates by default
if not os.environ.get("SSL_CERT_FILE"):
    import certifi
    os.environ["SSL_CERT_FILE"] = certifi.where()
    os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

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


def transcribe_file(file_path: str | Path, language: str | None = "en") -> TranscriptionResult:
    """
    Transcribe an audio or video file using Whisper.

    Args:
        file_path: Path to the audio/video file
        language: Language code (e.g., "en" for English). Set to None for auto-detection.
                  Default is "en" to avoid misdetection on short clips.

    Returns:
        TranscriptionResult with full text, language, and segments
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    logger.info(f"Transcribing file: {file_path} (language={language or 'auto'})")

    model = get_model()

    # Transcribe - specify language to avoid misdetection on short clips
    result = model.transcribe(
        str(file_path),
        task="transcribe",
        language=language,
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

    # Use specified language if provided, otherwise use detected language
    detected_language = result.get("language", "en")
    final_language = language if language else detected_language

    return TranscriptionResult(
        text=result["text"].strip(),
        language=final_language,
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
