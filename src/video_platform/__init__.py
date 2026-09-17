"""Video platform analytics and recommendation package."""

from .recommendations import Recommendation, recommend
from .repository import VideoRepository

__all__ = ["Recommendation", "VideoRepository", "recommend"]
