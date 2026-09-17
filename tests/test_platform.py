from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from video_platform.api import create_app
from video_platform.models import Video, WatchEvent
from video_platform.recommendations import recommend
from video_platform.repository import VideoRepository
from video_platform.seed import seed_demo


@pytest.fixture
def repository(tmp_path):
    values = VideoRepository(tmp_path / "test.db")
    values.initialize()
    seed_demo(values)
    return values


def test_seed_creates_catalog_and_outbox(repository):
    assert len(repository.list_videos()) == 5
    assert len(repository.pending_outbox()) == 6


def test_event_ingestion_is_idempotent(repository):
    event = WatchEvent("duplicate-event", "alice", "v-xai", 120, datetime.now(UTC), "session")
    assert repository.record_watch(event) is True
    assert repository.record_watch(event) is False
    matching = [row for row in repository.pending_outbox() if "duplicate-event" in row["payload"]]
    assert len(matching) == 1


def test_ingestion_rolls_back_when_reference_is_unknown(repository):
    event = WatchEvent("bad-event", "missing-user", "v-xai", 12, datetime.now(UTC), "session")
    with pytest.raises(Exception, match="FOREIGN KEY"):
        repository.record_watch(event)
    assert all(row["event_id"] != "outbox:bad-event" for row in repository.pending_outbox())


def test_video_analytics_clamps_overwatch(repository):
    repository.record_watch(
        WatchEvent("overwatch", "alice", "v-xai", 90_000, datetime.now(UTC), "session")
    )
    result = repository.video_analytics("v-xai")
    assert result is not None
    assert result["watch_seconds"] <= result["views"] * result["duration_seconds"]
    assert 0 <= result["average_completion_rate"] <= 1
    assert 0 <= result["completion_rate"] <= 1


def test_recommendations_exclude_seen_videos(repository):
    result = recommend(repository, "alice", now=datetime(2026, 9, 2, 12, 0, tzinfo=UTC))
    identifiers = {item.video_id for item in result}
    assert "v-rag" not in identifiers
    assert "v-stream" not in identifiers
    assert "v-xai" in identifiers


def test_recommendations_are_deterministic(repository):
    now = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    assert recommend(repository, "alice", now=now) == recommend(repository, "alice", now=now)


def test_cold_start_returns_explained_ranking(repository):
    result = recommend(repository, "new-user", now=datetime(2026, 9, 2, 12, 0, tzinfo=UTC))
    assert result[0].score >= result[-1].score
    assert all(item.reason for item in result)


@pytest.mark.parametrize("limit", [0, 101])
def test_recommendation_limit_is_bounded(repository, limit):
    with pytest.raises(ValueError, match="limit"):
        recommend(repository, "alice", limit=limit)


def test_model_validation_rejects_invalid_video():
    with pytest.raises(ValueError, match="duration"):
        Video("v", "c", "title", "category", 0, datetime.now(UTC))


def test_api_health_and_catalog(tmp_path):
    app = create_app(tmp_path / "api.db")
    seed_demo(app.state.repository)
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    assert len(client.get("/videos").json()) == 5


def test_api_duplicate_contract(tmp_path):
    app = create_app(tmp_path / "api.db")
    seed_demo(app.state.repository)
    client = TestClient(app)
    payload = {
        "event_id": "api-event",
        "user_id": "alice",
        "video_id": "v-xai",
        "watched_seconds": 100,
        "occurred_at": datetime.now(UTC).isoformat(),
        "session_id": "api-session",
    }
    first = client.post("/events/watch", json=payload)
    second = client.post("/events/watch", json=payload)
    assert first.status_code == 202
    assert first.json()["accepted"] is True
    assert second.json()["duplicate"] is True


def test_api_returns_not_found_for_unknown_video(tmp_path):
    client = TestClient(create_app(tmp_path / "api.db"))
    assert client.get("/analytics/videos/missing").status_code == 404


def test_api_rejects_naive_event_time(tmp_path):
    app = create_app(tmp_path / "api.db")
    seed_demo(app.state.repository)
    client = TestClient(app)
    payload = {
        "event_id": "naive",
        "user_id": "alice",
        "video_id": "v-xai",
        "watched_seconds": 10,
        "occurred_at": datetime.now().replace(microsecond=0).isoformat(),
        "session_id": "api-session",
    }
    assert client.post("/events/watch", json=payload).status_code == 422


def test_freshness_decays_over_time(repository):
    early = recommend(repository, "new-user", now=datetime(2026, 9, 2, tzinfo=UTC))
    late = recommend(
        repository,
        "new-user",
        now=datetime(2026, 9, 2, tzinfo=UTC) + timedelta(days=365),
    )
    assert sum(item.score for item in late) < sum(item.score for item in early)
