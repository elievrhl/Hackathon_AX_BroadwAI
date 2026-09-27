import asyncio
import base64
import json
from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import APIConnectionError
from PIL import Image

from broadwai.api import create_app
from broadwai.config import Settings
from broadwai.image_review import ImageReviewer, compress_for_review
from broadwai.images import ArticleImages
from broadwai.models import ArticleImage, utcnow
from tests.fakes import MemoryStore, article
from tests.test_images import Fetcher


def photo(color="green", size=(1600, 900), format="PNG", **kwargs):
    output = BytesIO()
    Image.new("RGB", size, color).save(output, format=format, **kwargs)
    return output.getvalue()


def client(verdict="keep", *, status="completed"):
    response = SimpleNamespace(
        id="test-response",
        status=status,
        output_text=json.dumps({"verdict": verdict}),
        usage=SimpleNamespace(
            input_tokens=500,
            output_tokens=7,
            input_tokens_details=SimpleNamespace(cached_tokens=0),
            output_tokens_details=SimpleNamespace(reasoning_tokens=0),
        ),
    )
    return SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(return_value=response)), close=AsyncMock()
    )


@pytest.mark.parametrize("format", ["PNG", "JPEG", "WEBP", "AVIF"])
def test_thumbnail_is_small_jpeg_and_never_enlarges(format):
    thumb = compress_for_review(photo(format=format))
    assert thumb.width == 768 and thumb.height == 432
    assert len(thumb.body) <= 100_000
    with Image.open(BytesIO(thumb.body)) as image:
        assert image.format == "JPEG" and image.mode == "RGB"
    small = compress_for_review(photo(size=(180, 120)))
    assert (small.width, small.height) == (180, 120)


def test_thumbnail_discards_metadata_applies_orientation_and_flattens_transparency():
    exif = Image.Exif()
    exif[274] = 6
    exif[315] = "Sensitive camera owner"
    thumb = compress_for_review(photo(size=(600, 300), format="JPEG", exif=exif))
    with Image.open(BytesIO(thumb.body)) as image:
        assert image.size == (300, 600)
        assert not image.getexif()
        assert "icc_profile" not in image.info
    output = BytesIO()
    Image.new("RGBA", (300, 200), (0, 0, 0, 0)).save(output, format="PNG")
    with Image.open(BytesIO(compress_for_review(output.getvalue()).body)) as image:
        assert image.getpixel((50, 50)) == (255, 255, 255)


def test_detailed_noisy_photo_stays_under_byte_limit():
    output = BytesIO()
    Image.effect_noise((1500, 1500), 100).convert("RGB").save(output, format="PNG")
    thumb = compress_for_review(output.getvalue())
    assert len(thumb.body) <= 100_000
    assert max(thumb.width, thumb.height) <= 768


def test_invalid_tiny_oversized_and_animated_images_never_reach_the_model():
    for body in [b"not an image", photo(size=(1, 1)), photo(size=(5000, 4001))]:
        with pytest.raises(ValueError):
            compress_for_review(body)
    output = BytesIO()
    Image.new("RGB", (300, 200), "red").save(
        output,
        format="GIF",
        save_all=True,
        append_images=[Image.new("RGB", (300, 200), "blue")],
        duration=100,
        loop=0,
    )
    with pytest.raises(ValueError, match="Animated"):
        compress_for_review(output.getvalue())


async def test_compact_request_excludes_alt_and_urls_limits_output_and_records_usage():
    item = article().model_copy(
        update={
            "image": ArticleImage(
                url="https://cdn.example/secret-query?token=private", alt="WRONG CAPTION"
            ),
            "text": "Useful context " * 1000,
        }
    )
    store = MemoryStore([item])
    model = client()
    reviewer = ImageReviewer(store, "unused", client=model)
    assert await reviewer.check(item, photo())
    kwargs = model.responses.create.call_args.kwargs
    assert kwargs["model"] == "gpt-5.4-nano"
    assert kwargs["max_output_tokens"] == 32
    assert kwargs["reasoning"] == {"effort": "none"}
    assert kwargs["store"] is False
    content = kwargs["input"][0]["content"]
    assert content[1]["detail"] == "low"
    assert content[1]["image_url"].startswith("data:image/jpeg;base64,")
    assert len(base64.b64decode(content[1]["image_url"].split(",")[1])) <= 100_000
    assert len(json.loads(content[0]["text"])["excerpt"]) == 1000
    assert "WRONG CAPTION" not in json.dumps(kwargs) and "secret-query" not in json.dumps(kwargs)
    schema = kwargs["text"]["format"]["schema"]
    assert list(schema["properties"]) == ["verdict"] and schema["additionalProperties"] is False
    record = next(iter(store.image_reviews.values()))
    assert record["status"] == "completed" and record["verdict"] == "keep"
    assert record["cost"]["estimated_usd"] > 0
    assert record["usage"]["output_tokens"] == 7
    assert "base64" not in json.dumps(record, default=str)
    await reviewer.close()
    model.close.assert_awaited_once()


@pytest.mark.parametrize("verdict", ["keep", "reject", "uncertain"])
async def test_each_verdict_survives_a_new_reviewer_without_paying_again(verdict):
    item = article()
    store = MemoryStore([item])
    first = client(verdict)
    assert await ImageReviewer(store, "unused", client=first).check(item, photo()) == (
        verdict == "keep"
    )
    second = client()
    assert await ImageReviewer(store, "unused", client=second).check(item, photo()) == (
        verdict == "keep"
    )
    first.responses.create.assert_awaited_once()
    second.responses.create.assert_not_awaited()


async def test_hames_publisher_illustration_reuses_uncertain_verdict_without_new_model_call():
    # Minimal public markup from the reported page. Its illustration is explicitly
    # declared, not an arbitrary image found elsewhere in the page.
    url = "https://richardhames.com/musings/the-hames-report/everything-except-their-names"
    image_url = (
        "https://substackcdn.com/image/fetch/$s_!s193!,f_auto,q_auto:good,fl_progressive:steep/"
        "https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F"
        "2b18a6d9-b741-4c7f-8fc4-db6f71381780_1536x1024.png"
    )
    item = article().model_copy(
        update={
            "url": url,
            "title": "Everything Except Their Names - Richard David Hames",
            "image": ArticleImage(url=image_url),
            "image_checked_at": utcnow(),
        }
    )
    body = photo()
    store = MemoryStore([item])
    model = client("uncertain")
    reviewer = ImageReviewer(store, "unused", client=model)
    assert not await reviewer.check(item, body)
    fetcher = Fetcher(
        {
            image_url: (body, "image/png"),
            url: (f'<meta property="og:image" content="{image_url}">'.encode(), "text/html"),
        }
    )
    service = ArticleImages(store, fetcher, reviewer)
    assert await service.get(item.id) == (body, "image/png")
    assert fetcher.calls == [image_url, url]
    model.responses.create.assert_awaited_once()
    assert next(iter(store.image_reviews.values()))["verdict"] == "uncertain"
    await service.close()


@pytest.mark.parametrize("verdict", ["reject", "uncertain"])
async def test_rejected_publisher_or_uncertain_body_image_does_not_prevent_next_image(verdict):
    item = article().model_copy(update={"url": "https://site.example/story"})
    store = MemoryStore([item])
    first, second = photo(color="red"), photo(color="green")
    markup = (
        '<meta property="og:image" content="/first.png">'
        if verdict == "reject"
        else '<article><img src="/first.png"></article>'
    ) + '<article><img src="/second.png"></article>'
    fetcher = Fetcher(
        {
            item.url: (markup.encode(), "text/html"),
            "https://site.example/first.png": (first, "image/png"),
            "https://site.example/second.png": (second, "image/png"),
        }
    )
    model = client()
    model.responses.create.side_effect = [
        client(verdict).responses.create.return_value,
        client("keep").responses.create.return_value,
    ]
    service = ArticleImages(store, fetcher, ImageReviewer(store, "unused", client=model))
    assert await service.get(item.id) == (second, "image/png")
    assert model.responses.create.await_count == 2
    assert store.get_article(item.id).image.url.endswith("/second.png")
    await service.close()


async def test_content_image_model_and_version_changes_invalidate_the_decision(monkeypatch):
    item = article()
    store = MemoryStore([item])
    model = client()
    reviewer = ImageReviewer(store, "unused", client=model)
    await reviewer.check(item, photo())
    await reviewer.check(item.model_copy(update={"title": "Changed subject"}), photo())
    await reviewer.check(item, photo(color="red"))
    await ImageReviewer(store, "unused", model="another-model", client=model).check(item, photo())
    monkeypatch.setattr("broadwai.image_review.REVIEW_VERSION", "new-version")
    await reviewer.check(item, photo())
    assert model.responses.create.await_count == 5


@pytest.mark.parametrize("failure", ["incomplete", "malformed", "refusal", "network"])
async def test_errors_hide_images_and_do_not_repeat_paid_attempts_on_refresh(failure):
    item = article()
    store = MemoryStore([item])
    model = client()
    if failure == "network":
        model.responses.create.side_effect = APIConnectionError(
            request=httpx.Request("POST", "https://api.openai.com/v1/responses")
        )
    elif failure == "incomplete":
        model.responses.create.return_value.status = "incomplete"
    else:
        model.responses.create.return_value.output_text = "" if failure == "refusal" else "bad JSON"
    reviewer = ImageReviewer(store, "unused", client=model)
    assert not await reviewer.check(item, photo())
    assert not await ImageReviewer(store, "unused", client=model).check(item, photo())
    model.responses.create.assert_awaited_once()
    record = next(iter(store.image_reviews.values()))
    assert record["status"] == "error" and record["retry_after"] > utcnow()
    assert not await reviewer.check(item, photo(), publisher_selected=True)
    model.responses.create.assert_awaited_once()
    record["retry_after"] = utcnow() - timedelta(seconds=1)
    assert not await reviewer.check(item, photo())
    assert model.responses.create.await_count == 2


async def test_concurrent_reviewers_make_one_paid_call():
    item = article()
    store = MemoryStore([item])
    model = client()
    started = asyncio.Event()
    release = asyncio.Event()
    response = model.responses.create.return_value

    async def delayed(**kwargs):
        started.set()
        await release.wait()
        return response

    model.responses.create.side_effect = delayed
    first = asyncio.create_task(ImageReviewer(store, "unused", client=model).check(item, photo()))
    await started.wait()
    assert not await ImageReviewer(store, "unused", client=model).check(item, photo())
    release.set()
    assert await first
    model.responses.create.assert_awaited_once()


async def test_image_service_reviews_before_serving_and_only_selected_articles():
    picture = ArticleImage(url="https://cdn.example/photo.png")
    item = article().model_copy(update={"image": picture})
    store = MemoryStore([item])
    fetcher = Fetcher({picture.url: (photo(), "image/png")})
    model = client("reject")
    service = ArticleImages(
        store, fetcher, ImageReviewer(store, "unused", client=model), require_review=True
    )
    assert await service.get(item.id) is None
    assert fetcher.calls == []
    service.cache.clear()
    store.covers["edition"] = SimpleNamespace(items=[SimpleNamespace(article_id=item.id)])
    assert await service.get(item.id) is None
    assert store.get_article(item.id).image == picture
    model.responses.create.assert_awaited_once()
    service.cache.clear()
    assert await service.get(item.id) is None
    model.responses.create.assert_awaited_once()
    await service.close()


@pytest.mark.parametrize("verdict, status", [("keep", 200), ("reject", 404), ("uncertain", 404)])
def test_api_returns_only_approved_images(verdict, status):
    picture = ArticleImage(url="https://cdn.example/photo.png")
    item = article().model_copy(update={"image": picture})
    store = MemoryStore([item])
    store.covers["edition"] = SimpleNamespace(items=[SimpleNamespace(article_id=item.id)])
    app = create_app(Settings(_env_file=None), store=store)
    body = photo()
    with TestClient(app) as http:
        app.state.images.fetcher = Fetcher({picture.url: (body, "image/png")})
        # Missing configuration must not expose unchecked images.
        assert http.get(f"/v1/articles/{item.id}/image").status_code == 404
        app.state.images.cache.clear()
        model = client(verdict)
        app.state.images.reviewer = ImageReviewer(store, "unused", client=model)
        response = http.get(f"/v1/articles/{item.id}/image?v=review-1")
        assert response.status_code == status
        if status == 200:
            assert response.content == body  # Original display quality; only AI input is reduced.
        model.responses.create.assert_awaited_once()
