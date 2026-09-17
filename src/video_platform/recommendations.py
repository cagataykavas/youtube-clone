"""Deterministic, explainable ranking over repository-generated candidates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import log1p

from .repository import VideoRepository


@dataclass(frozen=True)
class Recommendation:
    video_id: str
    title: str
    category: str
    score: float
    reason: str


def _normalise(values: list[float]) -> list[float]:
    if not values:
        return []
    maximum = max(values)
    return [value / maximum for value in values] if maximum > 0 else [0.0 for _ in values]


def recommend(
    repository: VideoRepository,
    user_id: str,
    *,
    limit: int = 10,
    now: datetime | None = None,
) -> list[Recommendation]:
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    candidates = repository.recommendation_features(user_id)
    affinity_values = _normalise([float(row["category_affinity"]) for row in candidates])
    popularity_values = _normalise(
        [
            log1p(int(row["unique_viewers"])) * (0.25 + 0.75 * float(row["average_completion"]))
            for row in candidates
        ]
    )

    ranked: list[Recommendation] = []
    for row, affinity, popularity in zip(
        candidates, affinity_values, popularity_values, strict=True
    ):
        published_at = datetime.fromisoformat(str(row["published_at"]))
        age_days = max(0.0, (now - published_at).total_seconds() / 86_400)
        freshness = 1.0 / (1.0 + age_days / 30.0)
        score = 0.45 * popularity + 0.35 * affinity + 0.20 * freshness
        if affinity >= 0.5:
            reason = f"Strong match for your {row['category']} watch history"
        elif popularity >= 0.5:
            reason = "High completion among viewers"
        else:
            reason = "Fresh catalog candidate"
        ranked.append(
            Recommendation(
                video_id=str(row["video_id"]),
                title=str(row["title"]),
                category=str(row["category"]),
                score=round(score, 6),
                reason=reason,
            )
        )
    ranked.sort(key=lambda item: (-item.score, item.video_id))
    return ranked[:limit]
