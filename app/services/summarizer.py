"""
Summarization service for meeting transcripts.

Generates summaries and extracts action items from transcripts.
Uses a local LLM (can be swapped for OpenAI API).
"""

import logging
import re
from dataclasses import dataclass

from transformers import pipeline

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Cache pipelines globally
_summarizer = None
_generator = None


def get_summarizer():
    """Load and cache the summarization pipeline."""
    global _summarizer
    if _summarizer is None:
        logger.info("Loading summarization model...")
        _summarizer = pipeline(
            "summarization",
            model="facebook/bart-large-cnn",
            device=-1,  # CPU, use 0 for GPU
        )
        logger.info("Summarization model loaded")
    return _summarizer


def get_text_generator():
    """Load and cache a text generation pipeline for action items."""
    global _generator
    if _generator is None:
        logger.info("Loading text generation model...")
        # Using a smaller model for action item extraction
        _generator = pipeline(
            "text2text-generation",
            model="google/flan-t5-base",
            device=-1,  # CPU, use 0 for GPU
        )
        logger.info("Text generation model loaded")
    return _generator


@dataclass
class ActionItem:
    """An extracted action item from the meeting."""
    text: str
    assignee: str | None = None
    due_date: str | None = None


@dataclass
class MeetingSummary:
    """Summary and insights from a meeting transcript."""
    summary: str
    action_items: list[ActionItem]
    key_topics: list[str]


def chunk_text(text: str, max_chunk_size: int = 1000) -> list[str]:
    """Split text into chunks for processing by models with token limits."""
    words = text.split()
    chunks = []
    current_chunk = []
    current_size = 0

    for word in words:
        if current_size + len(word) + 1 > max_chunk_size:
            chunks.append(" ".join(current_chunk))
            current_chunk = [word]
            current_size = len(word)
        else:
            current_chunk.append(word)
            current_size += len(word) + 1

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks


def summarize_transcript(transcript: str) -> str:
    """
    Generate a summary of the meeting transcript.

    Args:
        transcript: The full meeting transcript text

    Returns:
        A concise summary of the meeting
    """
    if not transcript or len(transcript.strip()) < 50:
        return "Meeting transcript too short to summarize."

    logger.info(f"Summarizing transcript ({len(transcript)} chars)")

    summarizer = get_summarizer()

    # Handle long transcripts by chunking
    chunks = chunk_text(transcript, max_chunk_size=1000)

    if len(chunks) == 1:
        # Short transcript - summarize directly
        result = summarizer(
            transcript,
            max_length=150,
            min_length=30,
            do_sample=False,
        )
        return result[0]["summary_text"]

    # Long transcript - summarize chunks then combine
    chunk_summaries = []
    for i, chunk in enumerate(chunks):
        logger.debug(f"Summarizing chunk {i + 1}/{len(chunks)}")
        result = summarizer(
            chunk,
            max_length=100,
            min_length=20,
            do_sample=False,
        )
        chunk_summaries.append(result[0]["summary_text"])

    # Combine chunk summaries into final summary
    combined = " ".join(chunk_summaries)
    if len(combined) > 1000:
        result = summarizer(
            combined,
            max_length=200,
            min_length=50,
            do_sample=False,
        )
        return result[0]["summary_text"]

    return combined


def extract_action_items(transcript: str) -> list[ActionItem]:
    """
    Extract action items from the meeting transcript.

    Args:
        transcript: The full meeting transcript text

    Returns:
        List of action items mentioned in the meeting
    """
    if not transcript or len(transcript.strip()) < 50:
        return []

    logger.info("Extracting action items from transcript")

    generator = get_text_generator()

    # Use a prompt to extract action items
    prompt = f"""Extract action items from this meeting transcript.
List each action item on a new line starting with "- ".
If no action items are found, respond with "No action items found."

Transcript:
{transcript[:2000]}

Action items:"""

    result = generator(
        prompt,
        max_length=300,
        do_sample=False,
    )

    output = result[0]["generated_text"]

    # Parse the output into action items
    action_items = []
    for line in output.split("\n"):
        line = line.strip()
        if line.startswith("- ") or line.startswith("• "):
            text = line[2:].strip()
            if text and "no action items" not in text.lower():
                action_items.append(ActionItem(text=text))

    logger.info(f"Extracted {len(action_items)} action items")
    return action_items


def extract_key_topics(transcript: str) -> list[str]:
    """
    Extract key topics discussed in the meeting.

    Args:
        transcript: The full meeting transcript text

    Returns:
        List of main topics discussed
    """
    if not transcript or len(transcript.strip()) < 50:
        return []

    logger.info("Extracting key topics from transcript")

    generator = get_text_generator()

    prompt = f"""List the main topics discussed in this meeting.
Provide 3-5 key topics, one per line starting with "- ".

Transcript:
{transcript[:2000]}

Key topics:"""

    result = generator(
        prompt,
        max_length=150,
        do_sample=False,
    )

    output = result[0]["generated_text"]

    # Parse topics
    topics = []
    for line in output.split("\n"):
        line = line.strip()
        if line.startswith("- ") or line.startswith("• "):
            topic = line[2:].strip()
            if topic:
                topics.append(topic)

    logger.info(f"Extracted {len(topics)} key topics")
    return topics


def analyze_transcript(transcript: str) -> MeetingSummary:
    """
    Full analysis of a meeting transcript.

    Args:
        transcript: The full meeting transcript text

    Returns:
        MeetingSummary with summary, action items, and key topics
    """
    logger.info("Starting full transcript analysis")

    summary = summarize_transcript(transcript)
    action_items = extract_action_items(transcript)
    key_topics = extract_key_topics(transcript)

    return MeetingSummary(
        summary=summary,
        action_items=action_items,
        key_topics=key_topics,
    )


def action_items_to_json(action_items: list[ActionItem]) -> list[dict]:
    """Convert action items to JSON-serializable format."""
    return [
        {
            "text": item.text,
            "assignee": item.assignee,
            "due_date": item.due_date,
        }
        for item in action_items
    ]
