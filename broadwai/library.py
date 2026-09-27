"""Saved editions for the local demo; user IDs are not authentication credentials."""

from hashlib import sha256

from broadwai.models import Cover


def artwork(cover: Cover) -> dict:
    """A stable collage recipe using article photographs, never generated imagery."""
    candidates = sorted(cover.items, key=lambda item: item.image is None)
    photos = list(
        dict.fromkeys(
            item.article_id for item in candidates if item.image or not item.image_checked
        )
    )[:3]
    return {
        "version": 1,
        "palette": int(sha256(cover.id.encode()).hexdigest()[:8], 16) % 5,
        "photos": photos,
        "sections": list(dict.fromkeys(item.section for item in cover.items))[:4],
    }
