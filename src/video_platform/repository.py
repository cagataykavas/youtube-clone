"""SQLite persistence with idempotent event ingestion boundaries."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import Video, WatchEvent

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS channels (
    channel_id TEXT PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL REFERENCES channels(channel_id),
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL CHECK(duration_seconds > 0),
    published_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1))
);
CREATE TABLE IF NOT EXISTS watch_events (
    event_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    video_id TEXT NOT NULL REFERENCES videos(video_id),
    watched_seconds INTEGER NOT NULL CHECK(watched_seconds >= 0),
    occurred_at TEXT NOT NULL,
    session_id TEXT NOT NULL,
    ingested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS outbox_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_watch_user_time ON watch_events(user_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_watch_video_time ON watch_events(video_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_video_category ON videos(category, active);
CREATE INDEX IF NOT EXISTS idx_outbox_unpublished
    ON outbox_events(created_at) WHERE published_at IS NULL;
"""


class VideoRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def add_channel(self, channel_id: str, name: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO channels(channel_id, name) VALUES (?, ?)",
                (channel_id, name),
            )

    def add_user(self, user_id: str, created_at: datetime) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO users(user_id, created_at) VALUES (?, ?)",
                (user_id, created_at.isoformat()),
            )

    def add_video(self, video: Video) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO videos(
                    video_id, channel_id, title, category, duration_seconds, published_at, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    video.video_id,
                    video.channel_id,
                    video.title,
                    video.category,
                    video.duration_seconds,
                    video.published_at.isoformat(),
                    int(video.active),
                ),
            )

    def record_watch(self, event: WatchEvent) -> bool:
        """Store a watch event once and atomically stage its outbox record."""
        with self.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO watch_events(
                    event_id, user_id, video_id, watched_seconds, occurred_at, session_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.user_id,
                    event.video_id,
                    event.watched_seconds,
                    event.occurred_at.isoformat(),
                    event.session_id,
                ),
            )
            if cursor.rowcount == 0:
                return False
            connection.execute(
                """
                INSERT INTO outbox_events(event_id, event_type, aggregate_id, payload)
                VALUES (?, 'watch.recorded', ?, ?)
                """,
                (
                    f"outbox:{event.event_id}",
                    event.video_id,
                    json.dumps(
                        {
                            "event_id": event.event_id,
                            "user_id": event.user_id,
                            "video_id": event.video_id,
                            "watched_seconds": event.watched_seconds,
                            "occurred_at": event.occurred_at.isoformat(),
                        },
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                ),
            )
            return True

    def list_videos(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        query = """SELECT video_id, channel_id, title, category, duration_seconds,
                          published_at, active FROM videos"""
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY published_at DESC, video_id"
        with self.connect() as connection:
            rows = connection.execute(query).fetchall()
        return [dict(row) for row in rows]

    def video_analytics(self, video_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT v.video_id, v.title, v.duration_seconds,
                       COUNT(w.event_id) AS views,
                       COUNT(DISTINCT w.user_id) AS unique_viewers,
                       COALESCE(SUM(MIN(w.watched_seconds, v.duration_seconds)), 0)
                           AS watch_seconds,
                       COALESCE(AVG(
                           MIN(CAST(w.watched_seconds AS REAL) / v.duration_seconds, 1.0)
                       ), 0.0) AS average_completion_rate,
                       COALESCE(AVG(
                           CASE WHEN CAST(w.watched_seconds AS REAL) / v.duration_seconds >= 0.8
                                THEN 1.0 ELSE 0.0 END
                       ), 0.0) AS completion_rate
                FROM videos v
                LEFT JOIN watch_events w ON w.video_id = v.video_id
                WHERE v.video_id = ?
                GROUP BY v.video_id
                """,
                (video_id,),
            ).fetchone()
        return dict(row) if row else None

    def recommendation_features(self, user_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                WITH user_categories AS (
                    SELECT v.category,
                           SUM(MIN(CAST(w.watched_seconds AS REAL) / v.duration_seconds, 1.0))
                               AS affinity
                    FROM watch_events w JOIN videos v ON v.video_id = w.video_id
                    WHERE w.user_id = ? GROUP BY v.category
                ),
                popularity AS (
                    SELECT v.video_id, COUNT(DISTINCT w.user_id) AS unique_viewers,
                           COALESCE(AVG(
                               MIN(CAST(w.watched_seconds AS REAL) / v.duration_seconds, 1.0)
                           ), 0.0) AS average_completion
                    FROM videos v LEFT JOIN watch_events w ON w.video_id = v.video_id
                    GROUP BY v.video_id
                )
                SELECT v.video_id, v.title, v.category, v.published_at,
                       COALESCE(uc.affinity, 0.0) AS category_affinity,
                       p.unique_viewers, p.average_completion
                FROM videos v JOIN popularity p ON p.video_id = v.video_id
                LEFT JOIN user_categories uc ON uc.category = v.category
                WHERE v.active = 1 AND NOT EXISTS (
                    SELECT 1 FROM watch_events seen
                    WHERE seen.user_id = ? AND seen.video_id = v.video_id
                )
                ORDER BY v.video_id
                """,
                (user_id, user_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def pending_outbox(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT event_id, event_type, aggregate_id, payload, created_at
                   FROM outbox_events WHERE published_at IS NULL ORDER BY created_at, event_id"""
            ).fetchall()
        return [dict(row) for row in rows]
