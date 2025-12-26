# Meeting Intelligence

Real-time meeting transcription and analysis platform. Upload audio files or stream live meetings to get automatic transcriptions, summaries, action items, and semantic search across all your meetings.

## Features

- **Audio Transcription**: Powered by OpenAI Whisper for accurate speech-to-text
- **Smart Summaries**: AI-generated meeting summaries and key topics
- **Action Items**: Automatic extraction of tasks and follow-ups
- **Semantic Search**: Find relevant moments across all meetings using natural language
- **Speaker Diarization**: Know who said what (coming soon)

## Tech Stack

- **Backend**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL 16 with pgvector for vector search
- **Task Queue**: Celery with Redis
- **ML Models**:
  - OpenAI Whisper (transcription)
  - sentence-transformers (embeddings)
  - LLM for summarization

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development)

### Running with Docker

```bash
# Clone the repo
git clone https://github.com/yourusername/meeting-intelligence.git
cd meeting-intelligence

# Copy environment file
cp .env.example .env

# Start all services
docker compose up -d

# View logs
docker compose logs -f api
```

The API will be available at http://localhost:8000

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -e ".[dev]"

# Start PostgreSQL and Redis with Docker
docker compose up -d db redis

# Run the API
uvicorn app.main:app --reload

# In another terminal, run the Celery worker
celery -A workers.celery_app worker --loglevel=info
```

## API Endpoints

### Health Check
- `GET /health` - Basic health check
- `GET /health/db` - Database connection check

### Meetings
- `POST /meetings/upload` - Upload audio file for transcription
- `GET /meetings` - List all meetings
- `GET /meetings/{id}` - Get meeting details with transcript and insights
- `GET /meetings/{id}/transcript` - Get full transcript
- `GET /meetings/{id}/insights` - Get summary and action items
- `DELETE /meetings/{id}` - Delete a meeting

### Search
- `POST /search` - Semantic search across all transcripts

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
meeting-intelligence/
├── app/
│   ├── main.py              # FastAPI application
│   ├── routers/             # API endpoints
│   │   ├── health.py
│   │   ├── meetings.py
│   │   └── search.py
│   ├── services/            # Business logic
│   │   ├── transcription.py # Whisper integration
│   │   ├── summarizer.py    # LLM summarization
│   │   └── embeddings.py    # Vector embeddings
│   ├── models/              # SQLAlchemy models
│   │   └── meeting.py
│   └── core/                # Configuration
│       ├── config.py
│       └── database.py
├── workers/
│   ├── celery_app.py        # Celery configuration
│   └── tasks.py             # Background tasks
├── tests/
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://postgres:postgres@localhost:5432/meeting_intelligence` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `WHISPER_MODEL` | Whisper model size (tiny/base/small/medium/large) | `base` |
| `UPLOAD_DIR` | Directory for uploaded audio files | `./uploads` |
| `MAX_FILE_SIZE_MB` | Maximum upload file size | `500` |

## Roadmap

- [x] Basic API structure
- [x] File upload and storage
- [x] Database models
- [ ] Whisper transcription integration
- [ ] LLM summarization
- [ ] Embedding generation and vector search
- [ ] Real-time WebSocket streaming
- [ ] Speaker diarization
- [ ] User authentication
- [ ] Frontend UI

## License

MIT
