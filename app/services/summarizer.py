"""
Summarization service for meeting transcripts.

Uses Google Gemini API for high-quality summaries, with fallback to local models.
"""

import logging
from dataclasses import dataclass

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Gemini client (lazy loaded)
_gemini_client = None


def get_gemini_client():
    """Get the Gemini client."""
    global _gemini_client
    if _gemini_client is None and settings.gemini_api_key:
        from google import genai
        _gemini_client = genai.Client(api_key=settings.gemini_api_key)
        logger.info("Gemini client initialized")
    return _gemini_client


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


def summarize_with_gemini(transcript: str) -> str:
    """Generate summary using Gemini API."""
    client = get_gemini_client()
    if not client:
        return None

    prompt = f"""Summarize this meeting transcript in 2-3 concise sentences. Focus on the main discussion points and any decisions made.

Transcript:
{transcript[:8000]}

Summary:"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini summarization error: {e}")
        return None


def extract_action_items_with_gemini(transcript: str) -> list[ActionItem]:
    """Extract action items using Gemini API."""
    client = get_gemini_client()
    if not client:
        return []

    prompt = f"""Extract action items from this meeting transcript.
For each action item, provide:
- The task that needs to be done
- Who it's assigned to (if mentioned)
- Any deadline (if mentioned)

Format each as: "- [Task] | Assignee: [name or None] | Due: [date or None]"

If no action items are found, respond with "No action items found."

Transcript:
{transcript[:8000]}

Action items:"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        output = response.text.strip()

        action_items = []
        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("- ") and "no action items" not in line.lower():
                # Parse the formatted line
                parts = line[2:].split("|")
                text = parts[0].strip()
                assignee = None
                due_date = None

                for part in parts[1:]:
                    part = part.strip()
                    if part.lower().startswith("assignee:"):
                        assignee = part[9:].strip()
                        if assignee.lower() == "none":
                            assignee = None
                    elif part.lower().startswith("due:"):
                        due_date = part[4:].strip()
                        if due_date.lower() == "none":
                            due_date = None

                if text:
                    action_items.append(ActionItem(text=text, assignee=assignee, due_date=due_date))

        logger.info(f"Extracted {len(action_items)} action items with Gemini")
        return action_items
    except Exception as e:
        logger.error(f"Gemini action item extraction error: {e}")
        return []


def extract_key_topics_with_gemini(transcript: str) -> list[str]:
    """Extract key topics using Gemini API."""
    client = get_gemini_client()
    if not client:
        return []

    prompt = f"""List 3-5 key topics discussed in this meeting. Be specific and concise.

Format: One topic per line, starting with "- "

Transcript:
{transcript[:8000]}

Key topics:"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        output = response.text.strip()

        topics = []
        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("• "):
                topic = line[2:].strip()
                if topic:
                    topics.append(topic)

        logger.info(f"Extracted {len(topics)} key topics with Gemini")
        return topics
    except Exception as e:
        logger.error(f"Gemini topic extraction error: {e}")
        return []


def summarize_transcript(transcript: str) -> str:
    """Generate a summary of the meeting transcript."""
    if not transcript or len(transcript.strip()) < 50:
        return "Meeting transcript too short to summarize."

    logger.info(f"Summarizing transcript ({len(transcript)} chars)")

    # Try Gemini first
    if settings.gemini_api_key:
        summary = summarize_with_gemini(transcript)
        if summary:
            return summary
        logger.warning("Gemini summarization failed, falling back to local model")

    # Fallback to local model
    return _summarize_with_local_model(transcript)


def _summarize_with_local_model(transcript: str) -> str:
    """Fallback summarization using local FLAN-T5 model."""
    from transformers import pipeline

    logger.info("Using local FLAN-T5 for summarization")
    generator = pipeline(
        "text2text-generation",
        model="google/flan-t5-base",
        device=-1,
    )

    prompt = f"""Summarize this meeting transcript in 1-2 sentences:

{transcript[:2000]}

Summary:"""

    result = generator(prompt, max_length=150, do_sample=False)
    return result[0]["generated_text"].strip()


def extract_action_items(transcript: str) -> list[ActionItem]:
    """Extract action items from the meeting transcript."""
    if not transcript or len(transcript.strip()) < 50:
        return []

    logger.info("Extracting action items from transcript")

    # Try Gemini first
    if settings.gemini_api_key:
        items = extract_action_items_with_gemini(transcript)
        if items is not None:
            return items

    # Fallback: return empty list (local models aren't great at this)
    return []


def extract_key_topics(transcript: str) -> list[str]:
    """Extract key topics discussed in the meeting."""
    if not transcript or len(transcript.strip()) < 50:
        return []

    logger.info("Extracting key topics from transcript")

    # Try Gemini first
    if settings.gemini_api_key:
        topics = extract_key_topics_with_gemini(transcript)
        if topics:
            return topics

    # Fallback: return empty list
    return []


def analyze_transcript(transcript: str) -> MeetingSummary:
    """Full analysis of a meeting transcript."""
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
