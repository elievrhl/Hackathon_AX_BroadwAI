"""Duration requirements for video recommendations, independent of their provider."""

import math

from broadwai.youtube import video_id

MIN_VIDEO_SECONDS = 300


def known_duration(article) -> float | None:
    value = (article.media or {}).get("duration_seconds")
    if type(value) not in {int, float}:
        return None
    try:
        return value if math.isfinite(value) and value > 0 else None
    except OverflowError:
        return None


def duration_allowed(article) -> bool:
    # Legacy or web-discovered YouTube links may still be labelled as articles.
    if article.format != "video" and not video_id(article.url):
        return True
    duration = known_duration(article)
    return duration is not None and duration > MIN_VIDEO_SECONDS
