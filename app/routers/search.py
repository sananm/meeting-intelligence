import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Meeting, TranscriptChunk
from app.services.embeddings import generate_embedding

logger = logging.getLogger(__name__)
router = APIRouter()


class SearchQuery(BaseModel):
    query: str
    limit: int = 10
    min_similarity: float = 0.15  # Filter out weak matches


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

    # Format embedding for pgvector (no spaces after commas)
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    # Hybrid search: combines semantic similarity with keyword matching
    # - semantic_score: vector similarity (0-1)
    # - keyword_boost: 0.3 bonus if content contains the search term
    # This ensures exact keyword matches rank higher while still allowing semantic matches
    result = await db.execute(
        text("""
            SELECT * FROM (
                SELECT DISTINCT ON (tc.meeting_id)
                    tc.meeting_id,
                    tc.content as chunk_content,
                    tc.start_time,
                    tc.end_time,
                    m.title as meeting_title,
                    1 - (tc.embedding <=> CAST(:embedding AS vector)) as semantic_score,
                    CASE WHEN LOWER(tc.content) LIKE LOWER(:keyword_pattern) THEN 0.3 ELSE 0 END as keyword_boost
                FROM transcript_chunks tc
                JOIN meetings m ON tc.meeting_id = m.id
                WHERE tc.embedding IS NOT NULL
                ORDER BY tc.meeting_id, tc.embedding <=> CAST(:embedding AS vector)
            ) deduped
            WHERE (semantic_score + keyword_boost) >= :min_similarity
            ORDER BY (semantic_score + keyword_boost) DESC
            LIMIT :limit
        """),
        {
            "embedding": embedding_str,
            "keyword_pattern": f"%{search.query}%",
            "limit": search.limit,
            "min_similarity": search.min_similarity,
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
            similarity=float(row.semantic_score) + float(row.keyword_boost),
        )
        for row in rows
    ]

    return SearchResponse(query=search.query, results=results)


@router.get("/meetings/{meeting_id}", response_model=SearchResponse)
async def search_within_meeting(
    meeting_id: uuid.UUID,
    query: str = Query(..., min_length=1),
    limit: int = Query(default=5, le=20),
    min_similarity: float = Query(default=0.15),
    db: AsyncSession = Depends(get_db),
):
    """
    Search within a specific meeting's transcript using hybrid search.
    """
    query_embedding = generate_embedding(query)

    # Format embedding for pgvector (no spaces after commas)
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    # Hybrid search within a single meeting
    result = await db.execute(
        text("""
            SELECT
                tc.meeting_id,
                tc.content as chunk_content,
                tc.start_time,
                tc.end_time,
                m.title as meeting_title,
                1 - (tc.embedding <=> CAST(:embedding AS vector)) as semantic_score,
                CASE WHEN LOWER(tc.content) LIKE LOWER(:keyword_pattern) THEN 0.3 ELSE 0 END as keyword_boost
            FROM transcript_chunks tc
            JOIN meetings m ON tc.meeting_id = m.id
            WHERE tc.meeting_id = CAST(:meeting_id AS uuid)
              AND tc.embedding IS NOT NULL
            ORDER BY (1 - (tc.embedding <=> CAST(:embedding AS vector)) +
                     CASE WHEN LOWER(tc.content) LIKE LOWER(:keyword_pattern) THEN 0.3 ELSE 0 END) DESC
            LIMIT :limit
        """),
        {
            "meeting_id": str(meeting_id),
            "embedding": embedding_str,
            "keyword_pattern": f"%{query}%",
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
            similarity=float(row.semantic_score) + float(row.keyword_boost),
        )
        for row in rows
        if (float(row.semantic_score) + float(row.keyword_boost)) >= min_similarity
    ]

    return SearchResponse(query=query, results=results)
