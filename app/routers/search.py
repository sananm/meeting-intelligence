import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Meeting, TranscriptChunk
from app.services.embeddings import generate_embedding

router = APIRouter()


class SearchQuery(BaseModel):
    query: str
    limit: int = 10


class SearchResult(BaseModel):
    meeting_id: uuid.UUID
    meeting_title: str
    chunk_content: str
    start_time: float | None = None
    end_time: float | None = None
    similarity: float

    class Config:
        from_attributes = True


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]


@router.post("", response_model=SearchResponse)
async def semantic_search(
    search: SearchQuery,
    db: AsyncSession = Depends(get_db),
):
    """
    Semantic search across all meeting transcripts using vector similarity.

    Generates an embedding for the query and finds the most similar transcript chunks.
    """
    # Generate embedding for the search query
    query_embedding = generate_embedding(search.query)

    # Vector similarity search using pgvector
    # Using cosine distance (<=>), lower is more similar
    # Converting to similarity score: 1 - distance
    result = await db.execute(
        text("""
            SELECT
                tc.meeting_id,
                tc.content as chunk_content,
                tc.start_time,
                tc.end_time,
                m.title as meeting_title,
                1 - (tc.embedding <=> :embedding::vector) as similarity
            FROM transcript_chunks tc
            JOIN meetings m ON tc.meeting_id = m.id
            WHERE tc.embedding IS NOT NULL
            ORDER BY tc.embedding <=> :embedding::vector
            LIMIT :limit
        """),
        {
            "embedding": str(query_embedding),
            "limit": search.limit,
        },
    )

    rows = result.fetchall()

    results = [
        SearchResult(
            meeting_id=row.meeting_id,
            meeting_title=row.meeting_title,
            chunk_content=row.chunk_content,
            start_time=row.start_time,
            end_time=row.end_time,
            similarity=float(row.similarity),
        )
        for row in rows
    ]

    return SearchResponse(query=search.query, results=results)


@router.get("/meetings/{meeting_id}", response_model=SearchResponse)
async def search_within_meeting(
    meeting_id: uuid.UUID,
    query: str = Query(..., min_length=1),
    limit: int = Query(default=5, le=20),
    db: AsyncSession = Depends(get_db),
):
    """
    Search within a specific meeting's transcript.
    """
    query_embedding = generate_embedding(query)

    result = await db.execute(
        text("""
            SELECT
                tc.meeting_id,
                tc.content as chunk_content,
                tc.start_time,
                tc.end_time,
                m.title as meeting_title,
                1 - (tc.embedding <=> :embedding::vector) as similarity
            FROM transcript_chunks tc
            JOIN meetings m ON tc.meeting_id = m.id
            WHERE tc.meeting_id = :meeting_id
              AND tc.embedding IS NOT NULL
            ORDER BY tc.embedding <=> :embedding::vector
            LIMIT :limit
        """),
        {
            "meeting_id": str(meeting_id),
            "embedding": str(query_embedding),
            "limit": limit,
        },
    )

    rows = result.fetchall()

    results = [
        SearchResult(
            meeting_id=row.meeting_id,
            meeting_title=row.meeting_title,
            chunk_content=row.chunk_content,
            start_time=row.start_time,
            end_time=row.end_time,
            similarity=float(row.similarity),
        )
        for row in rows
    ]

    return SearchResponse(query=query, results=results)
