"""Domain models shared by ingestion, analytics and recommendation code."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Video:
    video_id: str
    channel_id: str
    title: str
    category: str
    duration_seconds: int
    published_at: datetime
    active: bool = True

    def __post_init__(self) -> None:
        if not self.video_id or not self.channel_id or not self.title.strip():
            raise ValueError("video_id, channel_id and title are required")
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        if self.published_at.tzinfo is None:
            raise ValueError("published_at must be timezone-aware")


@dataclass(frozen=True)
class WatchEvent:
    event_id: str
    user_id: str
    video_id: str
    watched_seconds: int
    occurred_at: datetime
    session_id: str

    def __post_init__(self) -> None:
        if not all((self.event_id, self.user_id, self.video_id, self.session_id)):
            raise ValueError("event, user, video and session identifiers are required")
        if self.watched_seconds < 0:
            raise ValueError("watched_seconds must be non-negative")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
