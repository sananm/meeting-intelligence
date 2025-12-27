"""
Celery tasks for processing meetings.

Handles the full pipeline:
1. Audio transcription with Whisper
2. Summary and action item extraction
3. Embedding generation for semantic search

Features:
- Exponential backoff retries
- Idempotent task execution
- Dead letter queue handling (configured in celery_app.py)
"""

import hashlib
import logging
import os
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def exponential_backoff(retry_count: int, base_delay: int = 10, max_delay: int = 600) -> int:
    """
    Calculate exponential backoff delay.

    Args:
        retry_count: Current retry attempt (0-indexed)
        base_delay: Base delay in seconds
        max_delay: Maximum delay cap in seconds

    Returns:
        Delay in seconds: base_delay * 2^retry_count, capped at max_delay
    """
    delay = base_delay * (2 ** retry_count)
    return min(delay, max_delay)


def get_idempotency_key(task_name: str, meeting_id: str) -> str:
    """Generate an idempotency key for a task."""
    return f"idempotency:{task_name}:{meeting_id}"


class IdempotencyGuard:
    """
    Context manager for idempotent task execution.

    Uses Redis to ensure a task only runs once for a given meeting_id.
    The lock expires after ttl seconds to handle crashed workers.
    """

    def __init__(self, task_name: str, meeting_id: str, ttl: int = 3600):
        self.key = get_idempotency_key(task_name, meeting_id)
        self.ttl = ttl
        self._redis = None
        self._acquired = False

    @property
    def redis(self):
        if self._redis is None:
            import redis
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            self._redis = redis.from_url(redis_url)
        return self._redis

    def acquire(self) -> bool:
        """Try to acquire the idempotency lock. Returns True if acquired."""
        # Use SET NX (set if not exists) with expiry
        self._acquired = self.redis.set(self.key, "processing", nx=True, ex=self.ttl)
        return self._acquired

    def is_completed(self) -> bool:
        """Check if this task has already completed."""
        value = self.redis.get(self.key)
        return value == b"completed"

    def mark_completed(self):
        """Mark the task as completed (with longer TTL for dedup window)."""
        self.redis.set(self.key, "completed", ex=self.ttl * 24)  # 24 hour dedup window

    def release(self):
        """Release the lock without marking complete (for retries)."""
        if self._acquired:
            self.redis.delete(self.key)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Only release on error - successful completion calls mark_completed
        if exc_type is not None:
            self.release()


# Sync database connection for Celery (Celery doesn't play well with async)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5433/meeting_intelligence"
)
# Convert async URL to sync
SYNC_DATABASE_URL = DATABASE_URL.replace("+asyncpg", "")

engine = create_engine(SYNC_DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def get_db() -> Session:
    """Get a sync database session for Celery tasks."""
    return SessionLocal()


@celery_app.task(bind=True, max_retries=3)
def process_meeting(self, meeting_id: str):
    """
    Main task to process a meeting through the full pipeline.

    This is the entry point - it chains the subtasks.
    """
    logger.info(f"Starting processing for meeting: {meeting_id}")

    try:
        # Import here to avoid circular imports
        from app.models import Meeting

        db = get_db()
        try:
            meeting = db.execute(
                select(Meeting).where(Meeting.id == UUID(meeting_id))
            ).scalar_one_or_none()

            if not meeting:
                logger.error(f"Meeting {meeting_id} not found")
                return {"error": "Meeting not found"}

            # Update status
            meeting.status = "processing"
            db.commit()
        finally:
            db.close()

        # Chain the tasks
        transcribe_audio.delay(meeting_id)

        return {"status": "processing", "meeting_id": meeting_id}

    except Exception as exc:
        logger.error(f"Error starting processing for {meeting_id}: {exc}")
        countdown = exponential_backoff(self.request.retries)
        logger.info(f"Retrying in {countdown}s (attempt {self.request.retries + 1}/{self.max_retries})")
        self.retry(exc=exc, countdown=countdown)


@celery_app.task(bind=True, max_retries=3)
def transcribe_audio(self, meeting_id: str):
    """
    Transcribe the audio/video file using Whisper.
    Also performs speaker diarization if available.
    Idempotent: will skip if already completed for this meeting_id.
    """
    logger.info(f"Transcribing meeting: {meeting_id}")

    # Idempotency check
    guard = IdempotencyGuard("transcribe_audio", meeting_id)
    if guard.is_completed():
        logger.info(f"Transcription already completed for meeting {meeting_id}, skipping")
        generate_insights.delay(meeting_id)  # Ensure next step runs
        return {"status": "already_completed", "meeting_id": meeting_id}

    if not guard.acquire():
        logger.info(f"Transcription already in progress for meeting {meeting_id}, skipping")
        return {"status": "already_processing", "meeting_id": meeting_id}

    try:
        from app.models import Meeting, Transcript
        from app.services.transcription import transcribe_file, segments_to_json

        db = get_db()
        try:
            meeting = db.execute(
                select(Meeting).where(Meeting.id == UUID(meeting_id))
            ).scalar_one_or_none()

            if not meeting:
                logger.error(f"Meeting {meeting_id} not found")
                return {"error": "Meeting not found"}

            if not meeting.audio_url:
                logger.error(f"Meeting {meeting_id} has no audio file")
                return {"error": "No audio file"}

            # Transcribe the file
            result = transcribe_file(meeting.audio_url)

            # Convert segments to JSON format
            transcript_segments = segments_to_json(result.segments)

            # Check if transcript already exists
            existing = db.execute(
                select(Transcript).where(Transcript.meeting_id == meeting.id)
            ).scalar_one_or_none()

            if existing:
                # Update existing transcript
                existing.content = result.text
                existing.speaker_labels = transcript_segments
                existing.language = result.language
            else:
                # Create new transcript
                transcript = Transcript(
                    meeting_id=meeting.id,
                    content=result.text,
                    speaker_labels=transcript_segments,
                    language=result.language,
                )
                db.add(transcript)

            # Update meeting duration
            meeting.duration_seconds = int(result.duration)
            meeting.status = "transcribed"
            db.commit()

            logger.info(f"Transcription complete for meeting {meeting_id}")

        finally:
            db.close()

        # Mark as completed for idempotency
        guard.mark_completed()

        # Chain to next task
        generate_insights.delay(meeting_id)

        return {"status": "transcribed", "meeting_id": meeting_id}

    except Exception as exc:
        logger.error(f"Error transcribing meeting {meeting_id}: {exc}")
        # Release idempotency lock for retry
        guard.release()
        # Update status to error
        db = get_db()
        try:
            from app.models import Meeting
            meeting = db.execute(
                select(Meeting).where(Meeting.id == UUID(meeting_id))
            ).scalar_one_or_none()
            if meeting:
                meeting.status = "error"
                db.commit()
        finally:
            db.close()
        countdown = exponential_backoff(self.request.retries)
        logger.info(f"Retrying transcription in {countdown}s (attempt {self.request.retries + 1}/{self.max_retries})")
        self.retry(exc=exc, countdown=countdown)


@celery_app.task(bind=True, max_retries=3)
def generate_insights(self, meeting_id: str):
    """
    Generate summary and action items from the transcript.
    Idempotent: will skip if already completed for this meeting_id.
    """
    logger.info(f"Generating insights for meeting: {meeting_id}")

    # Idempotency check
    guard = IdempotencyGuard("generate_insights", meeting_id)
    if guard.is_completed():
        logger.info(f"Insights already generated for meeting {meeting_id}, skipping")
        generate_embeddings.delay(meeting_id)  # Ensure next step runs
        return {"status": "already_completed", "meeting_id": meeting_id}

    if not guard.acquire():
        logger.info(f"Insights generation already in progress for meeting {meeting_id}, skipping")
        return {"status": "already_processing", "meeting_id": meeting_id}

    try:
        from app.models import Meeting, Transcript, MeetingInsights
        from app.services.summarizer import analyze_transcript, action_items_to_json

        db = get_db()
        try:
            # Get the transcript
            transcript = db.execute(
                select(Transcript).where(Transcript.meeting_id == UUID(meeting_id))
            ).scalar_one_or_none()

            if not transcript:
                logger.error(f"Transcript not found for meeting {meeting_id}")
                return {"error": "Transcript not found"}

            # Analyze the transcript
            analysis = analyze_transcript(transcript.content)

            # Check if insights already exist
            existing = db.execute(
                select(MeetingInsights).where(MeetingInsights.meeting_id == UUID(meeting_id))
            ).scalar_one_or_none()

            if existing:
                existing.summary = analysis.summary
                existing.action_items = action_items_to_json(analysis.action_items)
                existing.key_topics = analysis.key_topics
            else:
                insights = MeetingInsights(
                    meeting_id=UUID(meeting_id),
                    summary=analysis.summary,
                    action_items=action_items_to_json(analysis.action_items),
                    key_topics=analysis.key_topics,
                )
                db.add(insights)

            db.commit()
            logger.info(f"Insights generated for meeting {meeting_id}")

        finally:
            db.close()

        # Mark as completed for idempotency
        guard.mark_completed()

        # Chain to embedding generation
        generate_embeddings.delay(meeting_id)

        return {"status": "insights_generated", "meeting_id": meeting_id}

    except Exception as exc:
        logger.error(f"Error generating insights for {meeting_id}: {exc}")
        # Release idempotency lock for retry
        guard.release()
        countdown = exponential_backoff(self.request.retries)
        logger.info(f"Retrying insights in {countdown}s (attempt {self.request.retries + 1}/{self.max_retries})")
        self.retry(exc=exc, countdown=countdown)


@celery_app.task(bind=True, max_retries=3)
def generate_embeddings(self, meeting_id: str):
    """
    Generate embeddings for transcript chunks for semantic search.
    Idempotent: will skip if already completed for this meeting_id.
    """
    logger.info(f"Generating embeddings for meeting: {meeting_id}")

    # Idempotency check
    guard = IdempotencyGuard("generate_embeddings", meeting_id)
    if guard.is_completed():
        logger.info(f"Embeddings already generated for meeting {meeting_id}, skipping")
        return {"status": "already_completed", "meeting_id": meeting_id}

    if not guard.acquire():
        logger.info(f"Embeddings generation already in progress for meeting {meeting_id}, skipping")
        return {"status": "already_processing", "meeting_id": meeting_id}

    try:
        from app.models import Meeting, Transcript, TranscriptChunk
        from app.services.embeddings import chunk_transcript, generate_embeddings as gen_emb

        db = get_db()
        try:
            # Get the transcript
            transcript = db.execute(
                select(Transcript).where(Transcript.meeting_id == UUID(meeting_id))
            ).scalar_one_or_none()

            if not transcript:
                logger.error(f"Transcript not found for meeting {meeting_id}")
                return {"error": "Transcript not found"}

            # Delete existing chunks for this meeting
            db.execute(
                TranscriptChunk.__table__.delete().where(
                    TranscriptChunk.meeting_id == UUID(meeting_id)
                )
            )

            # Chunk the transcript
            chunks = chunk_transcript(
                transcript.content,
                segments=transcript.speaker_labels,
            )

            if not chunks:
                logger.warning(f"No chunks created for meeting {meeting_id}")
                return {"status": "no_chunks", "meeting_id": meeting_id}

            # Generate embeddings for all chunks
            chunk_texts = [chunk.text for chunk in chunks]
            embeddings = gen_emb(chunk_texts)

            # Save chunks with embeddings
            for chunk, embedding in zip(chunks, embeddings):
                db_chunk = TranscriptChunk(
                    meeting_id=UUID(meeting_id),
                    chunk_index=chunk.index,
                    content=chunk.text,
                    start_time=chunk.start_time,
                    end_time=chunk.end_time,
                    embedding=embedding,
                )
                db.add(db_chunk)

            # Update meeting status to ready
            meeting = db.execute(
                select(Meeting).where(Meeting.id == UUID(meeting_id))
            ).scalar_one_or_none()

            if meeting:
                meeting.status = "ready"

            db.commit()
            logger.info(
                f"Embeddings generated for meeting {meeting_id}: {len(chunks)} chunks"
            )

        finally:
            db.close()

        # Mark as completed for idempotency
        guard.mark_completed()

        return {"status": "ready", "meeting_id": meeting_id, "chunks": len(chunks)}

    except Exception as exc:
        logger.error(f"Error generating embeddings for {meeting_id}: {exc}")
        # Release idempotency lock for retry
        guard.release()
        countdown = exponential_backoff(self.request.retries)
        logger.info(f"Retrying embeddings in {countdown}s (attempt {self.request.retries + 1}/{self.max_retries})")
        self.retry(exc=exc, countdown=countdown)
