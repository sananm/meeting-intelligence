"""
Speaker diarization service.

Uses pyannote-audio for identifying different speakers in audio files.
Requires a Hugging Face token with access to pyannote models.

To enable:
1. Accept pyannote terms at https://huggingface.co/pyannote/speaker-diarization-3.1
2. Set HUGGINGFACE_TOKEN in environment
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Cache the diarization pipeline
_pipeline = None
_diarization_available = None


def is_diarization_available() -> bool:
    """Check if diarization is available (pyannote installed and token set)."""
    global _diarization_available

    if _diarization_available is not None:
        return _diarization_available

    hf_token = os.getenv("HUGGINGFACE_TOKEN")
    if not hf_token:
        logger.warning("HUGGINGFACE_TOKEN not set, speaker diarization disabled")
        _diarization_available = False
        return False

    try:
        from pyannote.audio import Pipeline
        _diarization_available = True
        return True
    except ImportError:
        logger.warning("pyannote-audio not installed, speaker diarization disabled")
        _diarization_available = False
        return False


def get_diarization_pipeline():
    """Load and cache the diarization pipeline."""
    global _pipeline

    if _pipeline is not None:
        return _pipeline

    if not is_diarization_available():
        return None

    try:
        from pyannote.audio import Pipeline
        import torch

        hf_token = os.getenv("HUGGINGFACE_TOKEN")

        logger.info("Loading speaker diarization model...")
        _pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=hf_token,
        )

        # Use GPU if available
        if torch.cuda.is_available():
            _pipeline.to(torch.device("cuda"))
            logger.info("Diarization pipeline using GPU")
        else:
            logger.info("Diarization pipeline using CPU")

        logger.info("Speaker diarization model loaded")
        return _pipeline

    except Exception as e:
        logger.error(f"Failed to load diarization model: {e}")
        return None


@dataclass
class SpeakerSegment:
    """A segment of speech attributed to a specific speaker."""
    speaker: str
    start: float
    end: float


@dataclass
class DiarizationResult:
    """Result of speaker diarization."""
    segments: list[SpeakerSegment]
    num_speakers: int


def diarize_audio(file_path: str | Path) -> DiarizationResult | None:
    """
    Perform speaker diarization on an audio file.

    Args:
        file_path: Path to the audio file

    Returns:
        DiarizationResult with speaker segments, or None if diarization unavailable
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    pipeline = get_diarization_pipeline()
    if pipeline is None:
        logger.info("Diarization not available, skipping")
        return None

    logger.info(f"Diarizing audio file: {file_path}")

    try:
        # Load audio using torchaudio to avoid torchcodec issues
        import torchaudio
        waveform, sample_rate = torchaudio.load(str(file_path))

        # pyannote expects mono audio, convert if stereo
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)

        # Pass audio as dictionary to bypass file loading issues
        audio_input = {"waveform": waveform, "sample_rate": sample_rate}

        # Run diarization
        diarization_output = pipeline(audio_input)

        # Handle new pyannote API that returns DiarizeOutput object
        if hasattr(diarization_output, 'speaker_diarization'):
            diarization = diarization_output.speaker_diarization
        else:
            diarization = diarization_output

        # Extract speaker segments
        segments = []
        speakers = set()

        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append(
                SpeakerSegment(
                    speaker=speaker,
                    start=turn.start,
                    end=turn.end,
                )
            )
            speakers.add(speaker)

        # Sort by start time
        segments.sort(key=lambda s: s.start)

        logger.info(
            f"Diarization complete: {len(segments)} segments, "
            f"{len(speakers)} speakers detected"
        )

        return DiarizationResult(
            segments=segments,
            num_speakers=len(speakers),
        )

    except Exception as e:
        logger.error(f"Diarization failed: {e}")
        return None


def merge_transcription_with_diarization(
    transcript_segments: list[dict],
    diarization_segments: list[SpeakerSegment],
) -> list[dict]:
    """
    Merge Whisper transcription segments with speaker diarization.

    Assigns speaker labels to transcript segments based on temporal overlap.

    Args:
        transcript_segments: List of transcript segments with start/end times
        diarization_segments: List of speaker segments from diarization

    Returns:
        Transcript segments with speaker labels added
    """
    if not diarization_segments:
        return transcript_segments

    result = []

    for trans_seg in transcript_segments:
        trans_start = trans_seg.get("start", 0)
        trans_end = trans_seg.get("end", 0)

        # Find the speaker with most overlap
        best_speaker = None
        best_overlap = 0

        for dia_seg in diarization_segments:
            # Calculate overlap
            overlap_start = max(trans_start, dia_seg.start)
            overlap_end = min(trans_end, dia_seg.end)
            overlap = max(0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = dia_seg.speaker

        # Create new segment with speaker label
        merged_seg = trans_seg.copy()
        merged_seg["speaker"] = best_speaker

        result.append(merged_seg)

    return result


def segments_to_json(segments: list[SpeakerSegment]) -> list[dict]:
    """Convert speaker segments to JSON-serializable format."""
    return [
        {
            "speaker": seg.speaker,
            "start": seg.start,
            "end": seg.end,
        }
        for seg in segments
    ]
