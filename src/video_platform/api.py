"""FastAPI boundary for catalog, event ingestion, analytics and recommendations."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

from .models import WatchEvent
from .recommendations import recommend
from .repository import VideoRepository


class WatchEventRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    video_id: str = Field(min_length=1, max_length=128)
    watched_seconds: int = Field(ge=0, le=86_400)
    occurred_at: datetime
    session_id: str = Field(min_length=1, max_length=128)


def create_app(database_path: str | Path | None = None) -> FastAPI:
    resolved_path = database_path or os.getenv("VIDEO_PLATFORM_DATABASE", "video-platform.db")
    repository = VideoRepository(resolved_path)
    repository.initialize()
    app = FastAPI(
        title="Video Platform Systems",
        version="0.1.0",
        description="Idempotent watch ingestion, analytics and explainable recommendations.",
    )
    app.state.repository = repository

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/videos")
    def videos() -> list[dict[str, object]]:
        return repository.list_videos()

    @app.post("/events/watch", status_code=status.HTTP_202_ACCEPTED)
    def ingest_watch(payload: WatchEventRequest) -> dict[str, object]:
        if payload.occurred_at.tzinfo is None:
            raise HTTPException(status_code=422, detail="occurred_at must include a timezone")
        try:
            created = repository.record_watch(WatchEvent(**payload.model_dump()))
        except sqlite3.IntegrityError as error:
            if "FOREIGN KEY" in str(error).upper():
                raise HTTPException(status_code=404, detail="unknown user or video") from error
            raise
        return {"accepted": created, "duplicate": not created, "event_id": payload.event_id}

    @app.get("/analytics/videos/{video_id}")
    def video_analytics(video_id: str) -> dict[str, object]:
        result = repository.video_analytics(video_id)
        if result is None:
            raise HTTPException(status_code=404, detail="video not found")
        return result

    @app.get("/recommendations/{user_id}")
    def recommendations(
        user_id: str,
        limit: int = Query(default=10, ge=1, le=100),
    ) -> list[dict[str, object]]:
        return [item.__dict__ for item in recommend(repository, user_id, limit=limit)]

    return app


app = create_app()
