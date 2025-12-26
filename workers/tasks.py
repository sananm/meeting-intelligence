"""
Celery tasks for processing meetings.

Handles the full pipeline:
1. Audio transcription with Whisper
2. Summary and action item extraction
3. Embedding generation for semantic search
"""

import logging
import os
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Sync database connection for Celery (Celery doesn't play well with async)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/meeting_intelligence"
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
        self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, max_retries=3)
def transcribe_audio(self, meeting_id: str):
    """
    Transcribe the audio/video file using Whisper.
    """
    logger.info(f"Transcribing meeting: {meeting_id}")

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

            # Check if transcript already exists
            existing = db.execute(
                select(Transcript).where(Transcript.meeting_id == meeting.id)
            ).scalar_one_or_none()

            if existing:
                # Update existing transcript
                existing.content = result.text
                existing.speaker_labels = segments_to_json(result.segments)
                existing.language = result.language
            else:
                # Create new transcript
                transcript = Transcript(
                    meeting_id=meeting.id,
                    content=result.text,
                    speaker_labels=segments_to_json(result.segments),
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

        # Chain to next task
        generate_insights.delay(meeting_id)

        return {"status": "transcribed", "meeting_id": meeting_id}

    except Exception as exc:
        logger.error(f"Error transcribing meeting {meeting_id}: {exc}")
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
        self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, max_retries=3)
def generate_insights(self, meeting_id: str):
    """
    Generate summary and action items from the transcript.
    """
    logger.info(f"Generating insights for meeting: {meeting_id}")

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

        # Chain to embedding generation
        generate_embeddings.delay(meeting_id)

        return {"status": "insights_generated", "meeting_id": meeting_id}

    except Exception as exc:
        logger.error(f"Error generating insights for {meeting_id}: {exc}")
        self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, max_retries=3)
def generate_embeddings(self, meeting_id: str):
    """
    Generate embeddings for transcript chunks for semantic search.
    """
    logger.info(f"Generating embeddings for meeting: {meeting_id}")

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

        return {"status": "ready", "meeting_id": meeting_id, "chunks": len(chunks)}

    except Exception as exc:
        logger.error(f"Error generating embeddings for {meeting_id}: {exc}")
        self.retry(exc=exc, countdown=60)
