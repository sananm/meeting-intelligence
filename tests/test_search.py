"""
Tests for search endpoints.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Meeting, TranscriptChunk


@pytest.fixture
async def meeting_with_chunks(
    db_session: AsyncSession,
    test_user,
) -> Meeting:
    """Create a meeting with searchable transcript chunks."""
    meeting = Meeting(
        title="Searchable Meeting",
        status="ready",
        owner_id=test_user.id,
    )
    db_session.add(meeting)
    await db_session.flush()

    # Create chunks with mock embeddings (384 dimensions for all-MiniLM-L6-v2)
    chunks = [
        TranscriptChunk(
            meeting_id=meeting.id,
            chunk_index=0,
            content="We discussed the quarterly sales report.",
            start_time=0.0,
            end_time=10.0,
            embedding=[0.1] * 384,  # Mock embedding
        ),
        TranscriptChunk(
            meeting_id=meeting.id,
            chunk_index=1,
            content="The marketing team presented their campaign results.",
            start_time=10.0,
            end_time=20.0,
            embedding=[0.2] * 384,
        ),
        TranscriptChunk(
            meeting_id=meeting.id,
            chunk_index=2,
            content="We need to improve our customer support response times.",
            start_time=20.0,
            end_time=30.0,
            embedding=[0.3] * 384,
        ),
    ]

    for chunk in chunks:
        db_session.add(chunk)

    await db_session.commit()
    await db_session.refresh(meeting)

    return meeting


@pytest.mark.asyncio
async def test_semantic_search_empty_results(client: AsyncClient):
    """Test search when no matching content exists."""
    response = await client.post(
        "/search",
        json={"query": "random unrelated query", "limit": 10},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "random unrelated query"
    assert data["results"] == []


@pytest.mark.asyncio
async def test_search_within_meeting_not_found(client: AsyncClient):
    """Test searching within a nonexistent meeting."""
    import uuid
    fake_id = uuid.uuid4()

    response = await client.get(
        f"/search/meetings/{fake_id}",
        params={"query": "test query"},
    )

    # Should return empty results, not 404
    assert response.status_code == 200
    data = response.json()
    assert data["results"] == []


@pytest.mark.asyncio
async def test_search_query_validation(client: AsyncClient):
    """Test search with empty query."""
    response = await client.post(
        "/search",
        json={"query": "", "limit": 10},
    )

    # Empty query should fail validation
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_limit_parameter(client: AsyncClient):
    """Test search with custom limit."""
    response = await client.post(
        "/search",
        json={"query": "test", "limit": 5},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) <= 5


@pytest.mark.asyncio
async def test_search_response_format(client: AsyncClient, meeting_with_chunks):
    """Test search response has correct format."""
    # Note: This test uses mock embeddings, so similarity won't be meaningful
    response = await client.post(
        "/search",
        json={"query": "sales report", "limit": 10},
    )

    assert response.status_code == 200
    data = response.json()
    assert "query" in data
    assert "results" in data
    assert isinstance(data["results"], list)

    # If we have results, check format
    if data["results"]:
        result = data["results"][0]
        assert "meeting_id" in result
        assert "meeting_title" in result
        assert "chunk_content" in result
        assert "similarity" in result
