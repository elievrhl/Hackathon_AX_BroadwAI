import asyncio
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from broadwai.api import create_app
from broadwai.config import Settings
from broadwai.images import ArticleImages, article_image, raster_type
from broadwai.models import ArticleImage, utcnow
from broadwai.network import Download, RetrievalError
from tests.fakes import MemoryStore, article


def test_image_prefers_publisher_metadata_and_resolves_relative_urls():
    result = article_image(
        '<meta property="og:image" content="../photos/main.jpg">'
        '<meta property="og:image:alt" content="Le jardin au printemps">'
        '<meta name="twitter:image" content="/second.jpg">'
        '<article><img src="/third.jpg"></article>',
        "https://publisher.example/story/page",
    )
    assert result == ArticleImage(
        url="https://publisher.example/photos/main.jpg", alt="Le jardin au printemps"
    )


@pytest.mark.parametrize(
    "unsafe", ["http://127.0.0.1/a.jpg", "http://localhost/a.jpg", "data:image/png,a", "/a.svg"]
)
def test_image_ignores_unsafe_or_active_metadata_and_tries_next_candidate(unsafe):
    result = article_image(
        f'<meta property="og:image" content="{unsafe}">'
        '<meta name="twitter:image" content="//cdn.example/photo.webp">',
        "https://publisher.example/story",
    )
    assert result.url == "https://cdn.example/photo.webp"


def test_jsonld_uses_article_image_and_ignores_organisation_and_related_articles():
    document = """<script type="application/ld+json">broken JSON</script>
    <script type="application/ld+json">{"@graph":[
      {"@type":"Organization","image":"/logo.png"},
      {"@type":[{}],"image":"/malformed.jpg"},
      {"@type":"Article","url":"/other","image":"/related.jpg"},
      {"@type":"NewsArticle","mainEntityOfPage":{"@id":"https://site.example/story"},
       "image":[{"contentUrl":"/photo.jpg","caption":"Une légende"}]}
    ]}</script>"""
    assert article_image(document, "https://site.example/story") == ArticleImage(
        url="https://site.example/photo.jpg", alt="Une légende"
    )


def test_article_body_fallback_skips_navigation_logos_and_tracking_pixels():
    document = """<header><img src="/header.jpg"></header><article>
      <aside><img src="/advert.jpg"></aside><img src="/logo.jpg" alt="Logo">
      <img src="/pixel.jpg" width="1"><img src="/placeholder.svg"
      data-src="/garden.jpg" alt="Un jardin" width="800" height="600"></article>"""
    assert article_image(document, "https://site.example/story") == ArticleImage(
        url="https://site.example/garden.jpg", alt="Un jardin"
    )
    assert article_image(b"", "https://site.example/story") is None


@pytest.mark.parametrize(
    "logo",
    ["/logo-sq.png", "/brand-logo.png", "/assets/logos/brand.png", "/favicon.jpg", "/%6cogo.png"],
)
def test_publisher_logo_in_share_metadata_is_skipped_for_article_artwork(logo):
    document = (
        f'<meta property="og:image" content="{logo}"><article><img src="/photo.jpg"></article>'
    )
    assert (
        article_image(document, "https://site.example/story").url
        == "https://site.example/photo.jpg"
    )
    assert (
        article_image(f'<meta property="og:image" content="{logo}">', "https://site.example/story")
        is None
    )
    assert article_image(
        '<meta property="og:image" content="/sociology.jpg">', "https://site.example/story"
    ).url.endswith("/sociology.jpg")


async def test_previously_saved_logo_is_rediscovered_without_display_or_model_call():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    item = article().model_copy(
        update={
            "image": ArticleImage(url="https://site.example/logo-sq.png"),
            "image_checked_at": utcnow(),
        }
    )
    store = MemoryStore([item])
    fetcher = Fetcher(
        {item.url: (b'<meta property="og:image" content="/logo-sq.png">', "text/html")}
    )
    reviewer = SimpleNamespace(check=AsyncMock(), close=AsyncMock())
    images = ArticleImages(store, fetcher, reviewer)
    assert await images.get(item.id) is None
    assert store.get_article(item.id).image is None
    assert fetcher.calls == [item.url]
    reviewer.check.assert_not_awaited()
    await images.close()


class Fetcher:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def get(self, url):
        self.calls.append(url)
        await asyncio.sleep(0)
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return Download(url, *response)


PNG = b"\x89PNG\r\n\x1a\n" + b"test-raster"


async def test_old_articles_discover_images_once_without_changing_summary_identity():
    item = article()
    store = MemoryStore([item])
    image_url = "https://cdn.example/photo.png"
    fetcher = Fetcher(
        {
            item.url: (f'<meta property="og:image" content="{image_url}">'.encode(), "text/html"),
            image_url: (PNG, "image/png"),
        }
    )
    images = ArticleImages(store, fetcher)
    first, second = await asyncio.gather(images.get(item.id), images.get(item.id))
    assert first == second == (PNG, "image/png")
    assert await images.get(item.id) == first
    assert fetcher.calls == [item.url, image_url]
    persisted = store.get_article(item.id)
    assert persisted.image.url == image_url
    assert persisted.image_checked_at is not None
    assert persisted.text == item.text and persisted.content_hash == item.content_hash
    await images.close()


async def test_missing_images_are_recorded_and_recent_misses_do_not_refetch_pages():
    item = article()
    store = MemoryStore([item])
    fetcher = Fetcher({item.url: (b"<article>No image</article>", "text/html")})
    images = ArticleImages(store, fetcher)
    assert await images.get(item.id) is None
    assert await images.get(item.id) is None
    assert store.get_article(item.id).image_checked_at is not None
    images.cache.clear()
    assert await images.get(item.id) is None
    assert fetcher.calls == [item.url]
    store.set_article_image(item.id, None, utcnow() - timedelta(days=8))
    images.cache.clear()
    assert await images.get(item.id) is None
    assert fetcher.calls == [item.url, item.url]


@pytest.mark.parametrize(
    "response",
    [
        (b"<html>blocked</html>", "image/png"),
        (PNG, "text/html"),
        (b"<svg></svg>", "image/svg+xml"),
        RetrievalError("unreachable"),
    ],
)
async def test_unavailable_or_non_raster_image_is_a_cached_miss(response):
    picture = ArticleImage(url="https://cdn.example/image")
    item = article().model_copy(update={"image": picture})
    fetcher = Fetcher({picture.url: response})
    images = ArticleImages(MemoryStore([item]), fetcher)
    assert await images.get(item.id) is None
    assert await images.get(item.id) is None
    assert fetcher.calls == [picture.url]


async def test_unknown_articles_do_not_fetch_and_cache_is_bounded():
    images = ArticleImages(MemoryStore(), Fetcher({}))
    for index in range(150):
        assert await images.get(str(index)) is None
    assert len(images.cache) == 128 and images.cache_bytes == 0
    assert images.fetcher.calls == []


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (PNG, "image/png"),
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"GIF89a", "image/gif"),
        (b"RIFF1234WEBP", "image/webp"),
        (b"1234ftypavif", "image/avif"),
        (b"", None),
    ],
)
def test_raster_signature(body, expected):
    assert raster_type(body) == expected


def test_image_endpoint_serves_only_catalog_images_with_cache_and_nosniff():
    picture = ArticleImage(url="https://cdn.example/photo.png")
    item = article().model_copy(update={"image": picture})
    app = create_app(
        Settings(_env_file=None, image_review_enabled=False), store=MemoryStore([item])
    )
    with TestClient(app) as client:
        app.state.images.fetcher = Fetcher({picture.url: (PNG, "image/png")})
        response = client.get(f"/v1/articles/{item.id}/image")
        assert response.status_code == 200 and response.content == PNG
        assert response.headers["content-type"] == "image/png"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "max-age=21600" in response.headers["cache-control"]
        assert client.get("/v1/articles/unknown/image").status_code == 404
