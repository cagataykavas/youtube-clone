"""Deterministic sample catalog and watch history for demos and smoke tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .models import Video, WatchEvent
from .repository import VideoRepository


def seed_demo(repository: VideoRepository) -> None:
    now = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    channels = {
        "ch-ai": "Applied Intelligence",
        "ch-data": "Data Systems",
        "ch-game": "Game Engineering",
    }
    for channel_id, name in channels.items():
        repository.add_channel(channel_id, name)
    for user_id in ("alice", "bob", "carol"):
        repository.add_user(user_id, now - timedelta(days=120))

    videos = [
        Video(
            "v-rag", "ch-ai", "RAG evaluation beyond hit rate", "ai", 720, now - timedelta(days=8)
        ),
        Video(
            "v-xai", "ch-ai", "Activation patching in practice", "ai", 900, now - timedelta(days=3)
        ),
        Video(
            "v-stream",
            "ch-data",
            "Event-time streaming fundamentals",
            "data",
            840,
            now - timedelta(days=15),
        ),
        Video(
            "v-sql",
            "ch-data",
            "Designing replay-safe SQL pipelines",
            "data",
            660,
            now - timedelta(days=5),
        ),
        Video(
            "v-rl", "ch-game", "Training a parking agent", "games", 780, now - timedelta(days=25)
        ),
    ]
    for video in videos:
        repository.add_video(video)

    events = [
        WatchEvent("e1", "alice", "v-rag", 700, now - timedelta(days=2), "s1"),
        WatchEvent("e2", "alice", "v-stream", 300, now - timedelta(days=1), "s1"),
        WatchEvent("e3", "bob", "v-rag", 680, now - timedelta(days=4), "s2"),
        WatchEvent("e4", "bob", "v-xai", 850, now - timedelta(days=2), "s2"),
        WatchEvent("e5", "carol", "v-sql", 600, now - timedelta(days=1), "s3"),
        WatchEvent("e6", "carol", "v-xai", 810, now - timedelta(hours=8), "s3"),
    ]
    for event in events:
        repository.record_watch(event)
