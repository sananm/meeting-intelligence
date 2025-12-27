# Meeting Intelligence

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)
![Next.js](https://img.shields.io/badge/Next.js-14+-black.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

**AI-powered meeting transcription and analysis platform**

[Features](#features) • [Quick Start](#quick-start) • [Tech Stack](#tech-stack) • [API Reference](#api-reference)

</div>

---

## Overview

Meeting Intelligence transforms your audio recordings into actionable insights. Upload meeting recordings or stream live audio to get automatic transcriptions, AI-generated summaries, action item extraction, and semantic search across all your meetings.

## Features

| Feature | Description |
|---------|-------------|
| **Audio Transcription** | Powered by OpenAI Whisper for accurate speech-to-text conversion |
| **AI Summaries** | Google Gemini-powered meeting summaries with key topics extraction |
| **Action Items** | Automatic extraction of tasks, assignees, and due dates |
| **Semantic Search** | Find relevant moments across all meetings using natural language queries |
| **Live Recording** | Real-time transcription via WebSocket streaming from your browser |
| **Vector Search** | pgvector-powered similarity search for intelligent content discovery |

## Tech Stack

### Backend
- **Framework**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL 16 with pgvector extension
- **Task Queue**: Celery with Redis
- **AI/ML**:
  - OpenAI Whisper (transcription)
  - Google Gemini 2.0 Flash (summarization)
  - sentence-transformers (embeddings)

### Frontend
- **Framework**: Next.js 14 (React)
- **Styling**: Tailwind CSS
- **Icons**: Lucide React

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- FFmpeg (for audio processing)
- Google Gemini API key

### 1. Clone & Setup

```bash
git clone https://github.com/yourusername/meeting-intelligence.git
cd meeting-intelligence
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:

```env
# Database (Docker uses port 5433 to avoid conflicts)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/meeting_intelligence

# Redis
REDIS_URL=redis://localhost:6379/0

# Google Gemini API (for AI summaries)
GEMINI_API_KEY=your_api_key_here

# ML Models
WHISPER_MODEL=base  # Options: tiny, base, small, medium, large
```

### 3. Start Services

```bash
# Start PostgreSQL and Redis
docker compose up -d

# Install Python dependencies
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"

# Run database migrations
alembic upgrade head

# Start the API server
uvicorn app.main:app --reload --port 8000

# In a new terminal, start the Celery worker
celery -A workers.celery_app worker --loglevel=info
```

### 4. Start Frontend

```bash
cd frontend
npm install
npm run dev
```

### 5. Access the Application

- **Frontend**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Reference

### Meetings

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/meetings/upload` | Upload audio/video file for transcription |
| `GET` | `/meetings` | List all meetings |
| `GET` | `/meetings/{id}` | Get meeting with transcript and insights |
| `PATCH` | `/meetings/{id}` | Update meeting title |
| `DELETE` | `/meetings/{id}` | Delete a meeting |

### Search

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/search` | Semantic search across all transcripts |
| `GET` | `/search/meetings/{id}` | Search within a specific meeting |

### Live Streaming

| Method | Endpoint | Description |
|--------|----------|-------------|
| `WebSocket` | `/streaming/live` | Real-time audio transcription |
| `POST` | `/streaming/live/{session_id}/save` | Save streaming session |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Basic health check |
| `GET` | `/health/db` | Database connection status |

## Project Structure

```
meeting-intelligence/
├── app/
│   ├── main.py                 # FastAPI application entry
│   ├── routers/                # API route handlers
│   │   ├── meetings.py         # Meeting CRUD operations
│   │   ├── search.py           # Semantic search endpoints
│   │   └── streaming.py        # WebSocket live transcription
│   ├── services/               # Business logic layer
│   │   ├── transcription.py    # Whisper integration
│   │   ├── summarizer.py       # Gemini AI summarization
│   │   ├── embeddings.py       # Vector embeddings
│   │   └── streaming.py        # Real-time audio processing
│   ├── models/                 # SQLAlchemy ORM models
│   └── core/                   # Configuration & database
├── workers/
│   ├── celery_app.py           # Celery configuration
│   └── tasks.py                # Background processing tasks
├── frontend/
│   ├── app/                    # Next.js app router
│   │   ├── page.tsx            # Home page
│   │   ├── live/               # Live recording page
│   │   └── meetings/           # Meeting detail pages
│   └── components/             # React components
├── docker-compose.yml
└── pyproject.toml
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `GEMINI_API_KEY` | Google Gemini API key for summaries | Required |
| `WHISPER_MODEL` | Whisper model size | `base` |
| `UPLOAD_DIR` | Audio file storage directory | `./uploads` |
| `MAX_FILE_SIZE_MB` | Maximum upload file size | `500` |

## Supported File Formats

- **Audio**: MP3, WAV, M4A, FLAC, OGG
- **Video**: MP4, MOV, WebM, MKV

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Code Formatting

```bash
ruff check --fix .
ruff format .
```

### Type Checking

```bash
mypy app/
```

## Acknowledgments

- [OpenAI Whisper](https://github.com/openai/whisper) for speech recognition
- [Google Gemini](https://ai.google.dev/) for AI summarization
- [pgvector](https://github.com/pgvector/pgvector) for vector similarity search
- [sentence-transformers](https://www.sbert.net/) for text embeddings

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<div align="center">
  <sub>Built with FastAPI, Next.js, and AI</sub>
</div>
