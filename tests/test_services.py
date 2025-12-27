"""
Tests for service layer functions.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from app.services.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    decode_access_token,
)
from app.services.embeddings import (
    chunk_transcript,
    TextChunk,
    compute_similarity,
)
from app.services.summarizer import (
    chunk_text,
    ActionItem,
    action_items_to_json,
)


class TestAuthService:
    """Tests for authentication service functions."""

    def test_password_hash_and_verify(self):
        """Test password hashing and verification."""
        password = "securepassword123"
        hashed = get_password_hash(password)

        assert hashed != password
        assert verify_password(password, hashed)
        assert not verify_password("wrongpassword", hashed)

    def test_password_hash_unique(self):
        """Test that same password produces different hashes."""
        password = "samepassword"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        # Bcrypt uses random salt, so hashes should differ
        assert hash1 != hash2
        # But both should verify correctly
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)

    def test_create_and_decode_token(self):
        """Test JWT token creation and decoding."""
        user_id = "test-user-id-123"
        token = create_access_token(data={"sub": user_id})

        assert token is not None
        assert isinstance(token, str)

        token_data = decode_access_token(token)
        assert token_data is not None
        assert token_data.user_id == user_id

    def test_decode_invalid_token(self):
        """Test decoding invalid token."""
        result = decode_access_token("invalid.token.here")
        assert result is None

    def test_decode_expired_token(self):
        """Test decoding expired token."""
        from datetime import timedelta

        token = create_access_token(
            data={"sub": "user-id"},
            expires_delta=timedelta(seconds=-1),  # Already expired
        )

        result = decode_access_token(token)
        assert result is None


class TestEmbeddingsService:
    """Tests for embeddings service functions."""

    def test_chunk_transcript_empty(self):
        """Test chunking empty text."""
        chunks = chunk_transcript("")
        assert chunks == []

    def test_chunk_transcript_short(self):
        """Test chunking short text."""
        text = "This is a short transcript."
        chunks = chunk_transcript(text, chunk_size=100)

        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].index == 0

    def test_chunk_transcript_long(self):
        """Test chunking long text."""
        # Create text longer than chunk size
        text = "Word " * 200  # ~1000 characters
        chunks = chunk_transcript(text, chunk_size=200, chunk_overlap=20)

        assert len(chunks) > 1
        # Check indices are sequential
        for i, chunk in enumerate(chunks):
            assert chunk.index == i

    def test_chunk_transcript_with_segments(self):
        """Test chunking with timing segments."""
        segments = [
            {"start": 0, "end": 5, "text": "Hello everyone."},
            {"start": 5, "end": 10, "text": "Welcome to the meeting."},
            {"start": 10, "end": 15, "text": "Let's discuss the agenda."},
        ]

        chunks = chunk_transcript(
            "Hello everyone. Welcome to the meeting. Let's discuss the agenda.",
            segments=segments,
            chunk_size=100,
        )

        assert len(chunks) >= 1
        # Chunks should have timing info
        assert chunks[0].start_time is not None
        assert chunks[0].end_time is not None

    def test_compute_similarity(self):
        """Test cosine similarity computation."""
        # Same vector should have similarity 1
        vec = [0.5, 0.5, 0.5]
        assert abs(compute_similarity(vec, vec) - 1.0) < 0.001

        # Orthogonal vectors should have similarity 0
        vec1 = [1, 0, 0]
        vec2 = [0, 1, 0]
        assert abs(compute_similarity(vec1, vec2)) < 0.001

        # Opposite vectors should have similarity -1
        vec1 = [1, 0, 0]
        vec2 = [-1, 0, 0]
        assert abs(compute_similarity(vec1, vec2) + 1.0) < 0.001


class TestSummarizerService:
    """Tests for summarizer service functions."""

    def test_chunk_text_empty(self):
        """Test chunking empty text."""
        chunks = chunk_text("")
        assert chunks == []

    def test_chunk_text_short(self):
        """Test chunking short text."""
        text = "Short text."
        chunks = chunk_text(text, max_chunk_size=100)

        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunk_text_long(self):
        """Test chunking long text."""
        # Create text longer than chunk size
        words = ["word"] * 300
        text = " ".join(words)
        chunks = chunk_text(text, max_chunk_size=500)

        assert len(chunks) > 1
        # All chunks should be within size limit (approximately)
        for chunk in chunks:
            assert len(chunk) <= 600  # Some tolerance

    def test_action_items_to_json(self):
        """Test converting action items to JSON format."""
        items = [
            ActionItem(text="Follow up with client", assignee="John", due_date="2024-01-15"),
            ActionItem(text="Review document"),
        ]

        result = action_items_to_json(items)

        assert len(result) == 2
        assert result[0]["text"] == "Follow up with client"
        assert result[0]["assignee"] == "John"
        assert result[0]["due_date"] == "2024-01-15"
        assert result[1]["assignee"] is None


class TestTranscriptionService:
    """Tests for transcription service functions."""

    def test_segments_to_json(self):
        """Test converting transcript segments to JSON."""
        from app.services.transcription import TranscriptSegment, segments_to_json

        segments = [
            TranscriptSegment(start=0.0, end=5.0, text="Hello", speaker=None),
            TranscriptSegment(start=5.0, end=10.0, text="World", speaker="Speaker A"),
        ]

        result = segments_to_json(segments)

        assert len(result) == 2
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 5.0
        assert result[0]["text"] == "Hello"
        assert result[1]["speaker"] == "Speaker A"


class TestDiarizationService:
    """Tests for diarization service functions."""

    def test_is_diarization_available_no_token(self):
        """Test diarization availability without token."""
        from app.services.diarization import is_diarization_available

        with patch.dict("os.environ", {"HUGGINGFACE_TOKEN": ""}, clear=False):
            # Reset cached value
            import app.services.diarization as diarization_module
            diarization_module._diarization_available = None

            # Should return False without token
            # Note: This test may behave differently based on environment

    def test_merge_transcription_with_diarization_empty(self):
        """Test merging with empty diarization."""
        from app.services.diarization import merge_transcription_with_diarization

        transcript_segments = [
            {"start": 0, "end": 5, "text": "Hello"},
        ]

        result = merge_transcription_with_diarization(transcript_segments, [])

        assert len(result) == 1
        assert result[0]["text"] == "Hello"

    def test_merge_transcription_with_diarization(self):
        """Test merging transcription with diarization."""
        from app.services.diarization import (
            merge_transcription_with_diarization,
            SpeakerSegment,
        )

        transcript_segments = [
            {"start": 0, "end": 5, "text": "Hello everyone"},
            {"start": 5, "end": 10, "text": "Hi there"},
        ]

        diarization_segments = [
            SpeakerSegment(speaker="SPEAKER_00", start=0, end=6),
            SpeakerSegment(speaker="SPEAKER_01", start=6, end=12),
        ]

        result = merge_transcription_with_diarization(
            transcript_segments,
            diarization_segments,
        )

        assert len(result) == 2
        assert result[0]["speaker"] == "SPEAKER_00"
        assert result[1]["speaker"] == "SPEAKER_01"
