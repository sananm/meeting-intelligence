from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import engine, Base
from app.routers import auth, health, meetings, search, streaming

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Enable pgvector extension and create tables
    from sqlalchemy import text
    async with engine.begin() as conn:
        # Enable pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown: Clean up
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description="Real-time meeting transcription and analysis platform",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["health"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(meetings.router, prefix="/meetings", tags=["meetings"])
app.include_router(search.router, prefix="/search", tags=["search"])
app.include_router(streaming.router, prefix="/streaming", tags=["streaming"])
