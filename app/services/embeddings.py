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
        _model = SentenceTransformer(settings.embedding_model)
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
        return _chunk_with_segments(segments, chunk_size)

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
) -> list[TextChunk]:
    """
    Chunk transcript using segment timing information.

    Groups segments together until reaching target size while preserving timing.
    """
    chunks = []
    current_chunk_text = []
    current_chunk_start = None
    current_chunk_end = None
    current_size = 0
    index = 0

    for seg in segments:
        seg_text = seg.get("text", "").strip()
        if not seg_text:
            continue

        seg_start = seg.get("start", 0)
        seg_end = seg.get("end", 0)

        # Start new chunk if adding this segment would exceed target size
        if current_size + len(seg_text) > target_chunk_size and current_chunk_text:
            chunks.append(
                TextChunk(
                    text=" ".join(current_chunk_text),
                    start_time=current_chunk_start,
                    end_time=current_chunk_end,
                    index=index,
                )
            )
            index += 1
            current_chunk_text = []
            current_chunk_start = None
            current_size = 0

        # Add segment to current chunk
        current_chunk_text.append(seg_text)
        if current_chunk_start is None:
            current_chunk_start = seg_start
        current_chunk_end = seg_end
        current_size += len(seg_text) + 1

    # Don't forget the last chunk
    if current_chunk_text:
        chunks.append(
            TextChunk(
                text=" ".join(current_chunk_text),
                start_time=current_chunk_start,
                end_time=current_chunk_end,
                index=index,
            )
        )

    logger.info(f"Created {len(chunks)} chunks from {len(segments)} segments")
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
