"""
Real-time audio streaming and transcription service.

Handles WebSocket audio streams and provides real-time transcription
using Whisper with voice activity detection.
"""

import asyncio
import io
import logging
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncGenerator

import numpy as np

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Audio settings for streaming
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit audio


@dataclass
class TranscriptionChunk:
    """A chunk of transcribed text with timing."""
    text: str
    start_time: float
    end_time: float
    is_partial: bool = False


class AudioBuffer:
    """Buffer for accumulating audio data for transcription."""

    def __init__(
        self,
        min_chunk_duration: float = 2.0,
        max_chunk_duration: float = 10.0,
        silence_threshold: float = 0.01,
        silence_duration: float = 0.5,
    ):
        self.min_chunk_duration = min_chunk_duration
        self.max_chunk_duration = max_chunk_duration
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration

        self.buffer = io.BytesIO()
        self.total_samples = 0
        self.start_time = 0.0

    def add_audio(self, audio_data: bytes) -> bool:
        """
        Add audio data to the buffer.

        Returns True if buffer should be processed (enough audio or silence detected).
        """
        self.buffer.write(audio_data)
        num_samples = len(audio_data) // SAMPLE_WIDTH
        self.total_samples += num_samples

        duration = self.total_samples / SAMPLE_RATE

        # Check if max duration reached
        if duration >= self.max_chunk_duration:
            return True

        # Check if min duration reached and silence detected
        if duration >= self.min_chunk_duration:
            # Convert recent audio to numpy for analysis
            audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            rms = np.sqrt(np.mean(audio_array**2))

            if rms < self.silence_threshold:
                return True

        return False

    def get_audio(self) -> bytes:
        """Get all buffered audio data."""
        return self.buffer.getvalue()

    def get_duration(self) -> float:
        """Get current buffer duration in seconds."""
        return self.total_samples / SAMPLE_RATE

    def clear(self) -> float:
        """Clear the buffer and return the end time."""
        end_time = self.start_time + self.get_duration()
        self.start_time = end_time
        self.buffer = io.BytesIO()
        self.total_samples = 0
        return end_time


class RealtimeTranscriber:
    """Real-time transcription using Whisper."""

    def __init__(self):
        self._model = None
        self.audio_buffer = AudioBuffer()
        self.is_running = False

    @property
    def model(self):
        """Lazy load the Whisper model."""
        if self._model is None:
            from app.services.transcription import get_model
            self._model = get_model()
        return self._model

    def transcribe_chunk_sync(self, audio_data: bytes, start_time: float) -> TranscriptionChunk | None:
        """
        Transcribe a chunk of audio data (sync version for thread pool).

        Returns TranscriptionChunk or None if transcription failed.
        """
        if not audio_data:
            return None

        try:
            # Save audio to temp file (Whisper requires file path)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_path = Path(f.name)

                # Write WAV header and data
                with wave.open(f.name, "wb") as wav:
                    wav.setnchannels(CHANNELS)
                    wav.setsampwidth(SAMPLE_WIDTH)
                    wav.setframerate(SAMPLE_RATE)
                    wav.writeframes(audio_data)

            # Transcribe
            result = self.model.transcribe(
                str(temp_path),
                task="transcribe",
                verbose=False,
                fp16=False,
            )

            # Clean up temp file
            temp_path.unlink()

            text = result.get("text", "").strip()
            if not text:
                return None

            duration = len(audio_data) / (SAMPLE_RATE * SAMPLE_WIDTH)
            end_time = start_time + duration

            return TranscriptionChunk(
                text=text,
                start_time=start_time,
                end_time=end_time,
            )

        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return None

    async def process_audio_stream(
        self,
        audio_chunks: AsyncGenerator[bytes, None],
    ) -> AsyncGenerator[TranscriptionChunk, None]:
        """
        Process an async stream of audio data and yield transcription chunks.
        """
        self.is_running = True
        self.audio_buffer = AudioBuffer()

        try:
            async for chunk in audio_chunks:
                if not self.is_running:
                    break

                # Add to buffer
                should_process = self.audio_buffer.add_audio(chunk)

                if should_process:
                    audio_data = self.audio_buffer.get_audio()
                    start_time = self.audio_buffer.start_time
                    self.audio_buffer.clear()

                    # Transcribe in thread pool to not block
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        None,
                        self.transcribe_chunk_sync,
                        audio_data,
                        start_time,
                    )

                    if result:
                        yield result

            # Process any remaining audio
            if self.audio_buffer.total_samples > 0:
                audio_data = self.audio_buffer.get_audio()
                start_time = self.audio_buffer.start_time
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    self.transcribe_chunk_sync,
                    audio_data,
                    start_time,
                )
                if result:
                    yield result

        finally:
            self.is_running = False

    def stop(self):
        """Stop the transcription."""
        self.is_running = False
