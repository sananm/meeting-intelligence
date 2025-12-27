"""
Embedding service for semantic search.

Generates vector embeddings for transcript chunks using sentence-transformers.
"""

import logging
from dataclasses import dataclass

from sentence_transformers import SentenceTransformer

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Cache the model globally
_model = None

# Embedding dimension for all-MiniLM-L6-v2 is 384
EMBEDDING_DIMENSION = 384


def get_embedding_model() -> SentenceTransformer:
    """Load and cache the sentence transformer model."""
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {settings.embedding_model}")
        # Force CPU to avoid MPS issues with Celery's fork-based multiprocessing on macOS
        _model = SentenceTransformer(settings.embedding_model, device="cpu")
        logger.info("Embedding model loaded")
    return _model


@dataclass
class TextChunk:
    """A chunk of text with optional timing information."""
    text: str
    start_time: float | None = None
    end_time: float | None = None
    index: int = 0


def chunk_transcript(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    segments: list[dict] | None = None,
) -> list[TextChunk]:
    """
    Split transcript into overlapping chunks for embedding.

    Args:
        text: The full transcript text
        chunk_size: Target size of each chunk in characters
        chunk_overlap: Number of characters to overlap between chunks
        segments: Optional list of transcript segments with timing info

    Returns:
        List of TextChunk objects
    """
    if not text:
        return []

    # If we have segments with timing, use them for smarter chunking
    if segments:
        return _chunk_with_segments(segments, chunk_size, chunk_overlap)

    # Simple character-based chunking
    chunks = []
    start = 0
    index = 0

    while start < len(text):
        end = start + chunk_size

        # Try to break at a sentence boundary
        if end < len(text):
            # Look for sentence endings near the chunk boundary
            for punct in [". ", "? ", "! ", "\n"]:
                last_punct = text.rfind(punct, start + chunk_size // 2, end)
                if last_punct != -1:
                    end = last_punct + 1
                    break

        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(TextChunk(text=chunk_text, index=index))
            index += 1

        start = end - chunk_overlap

    logger.info(f"Created {len(chunks)} chunks from transcript")
    return chunks


def _chunk_with_segments(
    segments: list[dict],
    target_chunk_size: int = 500,
    overlap_size: int = 50,
) -> list[TextChunk]:
    """
    Chunk transcript using segment timing information with configurable overlap.

    Groups segments together until reaching target size while preserving timing.
    Overlap is achieved by keeping trailing segments from the previous chunk.

    Args:
        segments: List of transcript segments with text, start, end
        target_chunk_size: Target size of each chunk in characters
        overlap_size: Target overlap size in characters between chunks
    """
    chunks = []
    current_chunk_segments = []  # Store segment dicts for overlap calculation
    current_chunk_start = None
    current_size = 0
    index = 0

    for seg in segments:
        seg_text = seg.get("text", "").strip()
        if not seg_text:
            continue

        seg_start = seg.get("start", 0)
        seg_end = seg.get("end", 0)

        # Start new chunk if adding this segment would exceed target size
        if current_size + len(seg_text) > target_chunk_size and current_chunk_segments:
            # Create chunk from current segments
            chunk_text = " ".join(s["text"].strip() for s in current_chunk_segments)
            chunk_end = current_chunk_segments[-1].get("end", 0)

            chunks.append(
                TextChunk(
                    text=chunk_text,
                    start_time=current_chunk_start,
                    end_time=chunk_end,
                    index=index,
                )
            )
            index += 1

            # Calculate overlap: keep trailing segments that fit within overlap_size
            overlap_segments = []
            overlap_chars = 0
            for s in reversed(current_chunk_segments):
                s_len = len(s.get("text", "").strip()) + 1
                if overlap_chars + s_len <= overlap_size:
                    overlap_segments.insert(0, s)
                    overlap_chars += s_len
                else:
                    break

            # Start new chunk with overlap segments
            current_chunk_segments = overlap_segments
            current_chunk_start = overlap_segments[0].get("start", 0) if overlap_segments else None
            current_size = overlap_chars

        # Add segment to current chunk
        current_chunk_segments.append({
            "text": seg_text,
            "start": seg_start,
            "end": seg_end,
        })
        if current_chunk_start is None:
            current_chunk_start = seg_start
        current_size += len(seg_text) + 1

    # Don't forget the last chunk
    if current_chunk_segments:
        chunk_text = " ".join(s["text"].strip() for s in current_chunk_segments)
        chunk_end = current_chunk_segments[-1].get("end", 0)

        chunks.append(
            TextChunk(
                text=chunk_text,
                start_time=current_chunk_start,
                end_time=chunk_end,
                index=index,
            )
        )

    logger.info(f"Created {len(chunks)} chunks from {len(segments)} segments (overlap={overlap_size})")
    return chunks


def generate_embedding(text: str) -> list[float]:
    """
    Generate embedding vector for a single text.

    Args:
        text: The text to embed

    Returns:
        List of floats representing the embedding vector
    """
    model = get_embedding_model()
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Generate embedding vectors for multiple texts.

    Args:
        texts: List of texts to embed

    Returns:
        List of embedding vectors
    """
    if not texts:
        return []

    model = get_embedding_model()
    logger.info(f"Generating embeddings for {len(texts)} texts")

    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=True)

    logger.info("Embeddings generated successfully")
    return [emb.tolist() for emb in embeddings]


def compute_similarity(embedding1: list[float], embedding2: list[float]) -> float:
    """
    Compute cosine similarity between two embeddings.

    Args:
        embedding1: First embedding vector
        embedding2: Second embedding vector

    Returns:
        Similarity score between 0 and 1
    """
    import numpy as np

    a = np.array(embedding1)
    b = np.array(embedding2)

    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
