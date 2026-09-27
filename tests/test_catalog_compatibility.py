import pytest
from pydantic import ValidationError

from broadwai.models import Article
from tests.fakes import article


def persisted_article(content_format):
    """JSON shape saved by previous versions, independent of current model fields."""
    return {
        **article().model_dump(mode="json"),
        "format": content_format,
        "media": None if content_format == "article" else {
            "url": "https://source1.example/video.webm",
            "provider": "direct",
            "status": "ready",
            "duration_seconds": 42.5,
            "transcript_origin": "import",
        },
        "transcript": [] if content_format == "article" else [
            {"start": 0.0, "end": 4.0, "text": "Python", "speaker": None}
        ],
    }


@pytest.mark.parametrize("content_format", ["article", "animation", "video", "podcast"])
def test_persisted_catalog_fields_survive_validation_and_updates(content_format):
    payload = persisted_article(content_format)
    loaded = Article.model_validate(payload)
    updated = loaded.model_copy(update={"title": "Corrected title"}).model_dump(mode="json")
    for key in ("format", "media", "transcript"):
        assert updated[key] == payload[key]
    assert (loaded.reading_time_minutes is not None) == (content_format == "article")
    # Compatibility must not disable validation for ordinary article fields.
    with pytest.raises(ValidationError):
        Article.model_validate({**payload, "title": ""})


def test_articles_without_multimedia_fields_remain_compatible():
    payload = persisted_article("article")
    for key in ("format", "media", "transcript"):
        payload.pop(key)
    assert Article.model_validate(payload).format == "article"
