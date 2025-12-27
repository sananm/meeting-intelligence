"""
WebSocket endpoints for real-time audio streaming and transcription.

Supports:
- Live audio streaming from browser microphone
- Real-time transcription with interim results
- Session management for saving completed streams
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models import Meeting, Transcript
from app.services.streaming import RealtimeTranscriber, TranscriptionChunk

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


class StreamingSession:
    """Manages a live streaming session."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.transcriber = RealtimeTranscriber()
        self.transcript_chunks: list[TranscriptionChunk] = []
        self.raw_audio: bytes = b""
        self.started_at = datetime.utcnow()
        self.is_active = True

    def add_chunk(self, chunk: TranscriptionChunk):
        """Add a transcription chunk to the session."""
        self.transcript_chunks.append(chunk)

    def add_audio(self, audio_data: bytes):
        """Add raw audio data to the session."""
        self.raw_audio += audio_data

    def get_full_transcript(self) -> str:
        """Get the complete transcript text."""
        return " ".join(chunk.text for chunk in self.transcript_chunks)

    def get_transcript_segments(self) -> list[dict]:
        """Get transcript segments in JSON format."""
        return [
            {
                "start": chunk.start_time,
                "end": chunk.end_time,
                "text": chunk.text,
                "speaker": None,  # Could be added with diarization
            }
            for chunk in self.transcript_chunks
        ]


# Store active sessions
active_sessions: dict[str, StreamingSession] = {}


@router.websocket("/live")
async def live_transcription(websocket: WebSocket):
    """
    WebSocket endpoint for live audio transcription.

    Protocol:
    1. Client connects and receives session_id
    2. Client sends binary audio chunks (16-bit PCM, 16kHz, mono)
    3. Server sends JSON transcription updates
    4. Client sends {"action": "stop"} to end session
    5. Server sends final transcript and closes connection

    Messages from server:
    - {"type": "session_start", "session_id": "..."}
    - {"type": "transcript", "text": "...", "start": 0.0, "end": 1.0, "is_partial": false}
    - {"type": "session_end", "transcript": "...", "duration": 60.0}
    - {"type": "error", "message": "..."}
    """
    await websocket.accept()

    session_id = str(uuid.uuid4())
    session = StreamingSession(session_id)
    active_sessions[session_id] = session

    logger.info(f"Live transcription session started: {session_id}")

    # Send session start message
    await websocket.send_json({
        "type": "session_start",
        "session_id": session_id,
    })

    try:
        # Create async generator for audio chunks
        async def audio_generator():
            while session.is_active:
                try:
                    message = await asyncio.wait_for(
                        websocket.receive(),
                        timeout=30.0,
                    )

                    if "bytes" in message:
                        audio_data = message["bytes"]
                        session.add_audio(audio_data)
                        yield audio_data

                    elif "text" in message:
                        data = json.loads(message["text"])
                        if data.get("action") == "stop":
                            session.is_active = False
                            break

                except asyncio.TimeoutError:
                    # Send keepalive
                    await websocket.send_json({"type": "keepalive"})

        # Process audio stream and send transcriptions
        async for chunk in session.transcriber.process_audio_stream(audio_generator()):
            session.add_chunk(chunk)
            await websocket.send_json({
                "type": "transcript",
                "text": chunk.text,
                "start": chunk.start_time,
                "end": chunk.end_time,
                "is_partial": chunk.is_partial,
            })

        # Send session end message
        duration = (datetime.utcnow() - session.started_at).total_seconds()
        await websocket.send_json({
            "type": "session_end",
            "transcript": session.get_full_transcript(),
            "duration": duration,
            "session_id": session_id,
        })

    except WebSocketDisconnect:
        logger.info(f"Client disconnected from session: {session_id}")
    except Exception as e:
        logger.error(f"Error in live transcription session {session_id}: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
            })
        except:
            pass
    finally:
        session.transcriber.stop()
        session.is_active = False
        # Keep session in memory for a bit to allow saving
        # In production, you'd want a cleanup task

    # Only close if not already closed
    try:
        await websocket.close()
    except RuntimeError:
        pass  # Already closed


@router.post("/live/{session_id}/save")
async def save_streaming_session(
    session_id: str,
    title: str = "Live Recording",
    db: AsyncSession = Depends(get_db),
):
    """
    Save a completed streaming session as a meeting.

    Call this after the WebSocket session ends to persist the transcript.
    """
    session = active_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.is_active:
        raise HTTPException(status_code=400, detail="Session still active")

    # Calculate duration
    duration = (datetime.utcnow() - session.started_at).total_seconds()

    # Save audio file if we have raw audio
    audio_url = None
    if session.raw_audio:
        upload_dir = Path(settings.upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        audio_path = upload_dir / f"{session_id}.wav"

        import wave
        with wave.open(str(audio_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(session.raw_audio)

        audio_url = str(audio_path)

    # Create meeting
    meeting = Meeting(
        title=title,
        audio_url=audio_url,
        duration_seconds=int(duration),
        status="transcribed",  # Already transcribed in real-time
    )
    db.add(meeting)
    await db.flush()

    # Create transcript
    transcript = Transcript(
        meeting_id=meeting.id,
        content=session.get_full_transcript(),
        speaker_labels=session.get_transcript_segments(),
        language="en",  # Could detect from transcription
    )
    db.add(transcript)

    await db.commit()
    await db.refresh(meeting)

    # Clean up session
    del active_sessions[session_id]

    # Trigger background tasks for insights and embeddings
    from workers.tasks import generate_insights
    generate_insights.delay(str(meeting.id))

    return {
        "meeting_id": str(meeting.id),
        "title": title,
        "duration_seconds": int(duration),
        "transcript_length": len(session.get_full_transcript()),
    }


@router.get("/live/sessions")
async def list_active_sessions():
    """List all active streaming sessions (for debugging)."""
    return {
        "sessions": [
            {
                "session_id": session_id,
                "started_at": session.started_at.isoformat(),
                "is_active": session.is_active,
                "chunks_count": len(session.transcript_chunks),
            }
            for session_id, session in active_sessions.items()
        ]
    }
