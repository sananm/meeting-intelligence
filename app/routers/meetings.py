import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import OptionalUser
from app.models import Meeting, MeetingInsights, Transcript

router = APIRouter()
settings = get_settings()


# Pydantic schemas
class MeetingCreate(BaseModel):
    title: str


class TranscriptResponse(BaseModel):
    id: uuid.UUID
    content: str
    speaker_labels: list | None = None
    language: str | None = None

    class Config:
        from_attributes = True


class InsightsResponse(BaseModel):
    id: uuid.UUID
    summary: str | None = None
    action_items: list | None = None
    key_topics: list | None = None
    sentiment_scores: dict | None = None

    class Config:
        from_attributes = True


class MeetingResponse(BaseModel):
    id: uuid.UUID
    title: str
    audio_url: str | None = None
    duration_seconds: int | None = None
    status: str
    transcript: TranscriptResponse | None = None
    insights: InsightsResponse | None = None

    class Config:
        from_attributes = True


class MeetingListResponse(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    duration_seconds: int | None = None

    class Config:
        from_attributes = True


# Endpoints
@router.post("/upload", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
async def upload_meeting(
    title: Annotated[str, Form()],
    file: Annotated[UploadFile, File(description="Audio or video file")],
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
):
    """Upload an audio or video file for transcription"""
    # Validate file type
    allowed_types = [
        # Audio
        "audio/mpeg",
        "audio/wav",
        "audio/mp4",
        "audio/x-m4a",
        "audio/webm",
        "audio/ogg",
        # Video
        "video/mp4",
        "video/webm",
        "video/quicktime",  # .mov
        "video/x-msvideo",  # .avi
        "video/x-matroska",  # .mkv
    ]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {allowed_types}",
        )

    # Validate file size
    max_size = settings.max_file_size_mb * 1024 * 1024
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Max size: {settings.max_file_size_mb}MB",
        )

    # Save file
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_id = uuid.uuid4()
    file_ext = Path(file.filename or "media.mp4").suffix
    file_path = upload_dir / f"{file_id}{file_ext}"

    with open(file_path, "wb") as f:
        f.write(content)

    # Create meeting record
    meeting = Meeting(
        title=title,
        audio_url=str(file_path),
        status="pending",
        owner_id=current_user.id if current_user else None,
    )
    db.add(meeting)
    await db.commit()

    # Re-fetch with relationships to avoid lazy loading issues
    result = await db.execute(
        select(Meeting)
        .where(Meeting.id == meeting.id)
        .options(selectinload(Meeting.transcript), selectinload(Meeting.insights))
    )
    meeting = result.scalar_one()

    # Trigger Celery task for processing
    from workers.tasks import process_meeting
    process_meeting.delay(str(meeting.id))

    return meeting


@router.get("", response_model=list[MeetingListResponse])
async def list_meetings(
    current_user: OptionalUser,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List all meetings (filtered by user if authenticated)"""
    query = select(Meeting).order_by(Meeting.created_at.desc())

    # If user is authenticated, show only their meetings
    if current_user:
        query = query.where(Meeting.owner_id == current_user.id)

    result = await db.execute(query.offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/{meeting_id}", response_model=MeetingResponse)
async def get_meeting(
    meeting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a meeting by ID with transcript and insights"""
    result = await db.execute(
        select(Meeting)
        .where(Meeting.id == meeting_id)
        .options(selectinload(Meeting.transcript), selectinload(Meeting.insights))
    )
    meeting = result.scalar_one_or_none()

    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found",
        )

    return meeting


@router.get("/{meeting_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(
    meeting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get the transcript for a meeting"""
    result = await db.execute(
        select(Transcript).where(Transcript.meeting_id == meeting_id)
    )
    transcript = result.scalar_one_or_none()

    if not transcript:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcript not found",
        )

    return transcript


@router.get("/{meeting_id}/insights", response_model=InsightsResponse)
async def get_insights(
    meeting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get insights (summary, action items) for a meeting"""
    result = await db.execute(
        select(MeetingInsights).where(MeetingInsights.meeting_id == meeting_id)
    )
    insights = result.scalar_one_or_none()

    if not insights:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insights not found",
        )

    return insights


class UpdateMeetingRequest(BaseModel):
    title: str


@router.patch("/{meeting_id}", response_model=MeetingListResponse)
async def update_meeting(
    meeting_id: uuid.UUID,
    update: UpdateMeetingRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update a meeting's title"""
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()

    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found",
        )

    meeting.title = update.title
    await db.commit()
    await db.refresh(meeting)

    return meeting


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(
    meeting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a meeting"""
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()

    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found",
        )

    # Delete audio file
    if meeting.audio_url:
        audio_path = Path(meeting.audio_url)
        if audio_path.exists():
            audio_path.unlink()

    await db.delete(meeting)
    await db.commit()
