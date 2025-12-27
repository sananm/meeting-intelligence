"""
Tests for meetings endpoints.
"""

import io
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Meeting, Transcript, MeetingInsights


@pytest.mark.asyncio
async def test_list_meetings_empty(client: AsyncClient):
    """Test listing meetings when none exist."""
    response = await client.get("/meetings")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_meetings(authenticated_client: AsyncClient, test_meeting: Meeting):
    """Test listing meetings for authenticated user."""
    response = await authenticated_client.get("/meetings")

    assert response.status_code == 200
    meetings = response.json()
    assert len(meetings) == 1
    assert meetings[0]["title"] == test_meeting.title
    assert meetings[0]["status"] == test_meeting.status


@pytest.mark.asyncio
async def test_get_meeting(authenticated_client: AsyncClient, test_meeting: Meeting):
    """Test getting a specific meeting."""
    response = await authenticated_client.get(f"/meetings/{test_meeting.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_meeting.id)
    assert data["title"] == test_meeting.title


@pytest.mark.asyncio
async def test_get_meeting_not_found(authenticated_client: AsyncClient):
    """Test getting a nonexistent meeting."""
    import uuid
    fake_id = uuid.uuid4()
    response = await authenticated_client.get(f"/meetings/{fake_id}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_meeting_with_transcript(
    authenticated_client: AsyncClient,
    db_session: AsyncSession,
    test_meeting: Meeting,
):
    """Test getting meeting with transcript data."""
    # Add transcript to meeting
    transcript = Transcript(
        meeting_id=test_meeting.id,
        content="This is the meeting transcript.",
        language="en",
        speaker_labels=[{"start": 0, "end": 5, "text": "Hello", "speaker": None}],
    )
    db_session.add(transcript)
    await db_session.commit()

    response = await authenticated_client.get(f"/meetings/{test_meeting.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["transcript"] is not None
    assert data["transcript"]["content"] == "This is the meeting transcript."


@pytest.mark.asyncio
async def test_get_meeting_with_insights(
    authenticated_client: AsyncClient,
    db_session: AsyncSession,
    test_meeting: Meeting,
):
    """Test getting meeting with insights data."""
    # Add insights to meeting
    insights = MeetingInsights(
        meeting_id=test_meeting.id,
        summary="This meeting discussed important topics.",
        action_items=[{"text": "Follow up with team", "assignee": None, "due_date": None}],
        key_topics=["planning", "development"],
    )
    db_session.add(insights)
    await db_session.commit()

    response = await authenticated_client.get(f"/meetings/{test_meeting.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["insights"] is not None
    assert "important topics" in data["insights"]["summary"]
    assert len(data["insights"]["action_items"]) == 1


@pytest.mark.asyncio
async def test_delete_meeting(
    authenticated_client: AsyncClient,
    db_session: AsyncSession,
    test_meeting: Meeting,
):
    """Test deleting a meeting."""
    response = await authenticated_client.delete(f"/meetings/{test_meeting.id}")

    assert response.status_code == 204

    # Verify meeting is deleted
    from sqlalchemy import select
    result = await db_session.execute(
        select(Meeting).where(Meeting.id == test_meeting.id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_meeting_not_found(authenticated_client: AsyncClient):
    """Test deleting a nonexistent meeting."""
    import uuid
    fake_id = uuid.uuid4()
    response = await authenticated_client.delete(f"/meetings/{fake_id}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_transcript(
    authenticated_client: AsyncClient,
    db_session: AsyncSession,
    test_meeting: Meeting,
):
    """Test getting transcript for a meeting."""
    transcript = Transcript(
        meeting_id=test_meeting.id,
        content="Full transcript content here.",
        language="en",
    )
    db_session.add(transcript)
    await db_session.commit()

    response = await authenticated_client.get(f"/meetings/{test_meeting.id}/transcript")

    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "Full transcript content here."


@pytest.mark.asyncio
async def test_get_transcript_not_found(
    authenticated_client: AsyncClient,
    test_meeting: Meeting,
):
    """Test getting transcript when none exists."""
    response = await authenticated_client.get(f"/meetings/{test_meeting.id}/transcript")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_insights(
    authenticated_client: AsyncClient,
    db_session: AsyncSession,
    test_meeting: Meeting,
):
    """Test getting insights for a meeting."""
    insights = MeetingInsights(
        meeting_id=test_meeting.id,
        summary="Meeting summary here.",
        action_items=[],
        key_topics=["topic1", "topic2"],
    )
    db_session.add(insights)
    await db_session.commit()

    response = await authenticated_client.get(f"/meetings/{test_meeting.id}/insights")

    assert response.status_code == 200
    data = response.json()
    assert data["summary"] == "Meeting summary here."
    assert len(data["key_topics"]) == 2


@pytest.mark.asyncio
async def test_get_insights_not_found(
    authenticated_client: AsyncClient,
    test_meeting: Meeting,
):
    """Test getting insights when none exist."""
    response = await authenticated_client.get(f"/meetings/{test_meeting.id}/insights")

    assert response.status_code == 404
