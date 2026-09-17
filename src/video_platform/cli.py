"""Command line demo for the complete local pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .recommendations import recommend
from .repository import VideoRepository
from .seed import seed_demo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Video platform systems demo")
    parser.add_argument("--database", type=Path, default=Path("video-platform.db"))
    parser.add_argument("--user", default="alice")
    parser.add_argument("--limit", type=int, default=5)
    return parser


def main() -> None:
    values = build_parser().parse_args()
    repository = VideoRepository(values.database)
    repository.initialize()
    seed_demo(repository)
    result = {
        "user_id": values.user,
        "recommendations": [
            item.__dict__ for item in recommend(repository, values.user, limit=values.limit)
        ],
        "analytics": [
            repository.video_analytics(video["video_id"]) for video in repository.list_videos()
        ],
        "pending_outbox_events": len(repository.pending_outbox()),
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
