from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from broadwai.api import create_app
from broadwai.collections import CollectionInput, Collections
from broadwai.config import Settings
from broadwai.images import ArticleImages
from broadwai.models import Article, ArticleImage, Interest, Profile, utcnow
from broadwai.network import Download, RetrievalError
from broadwai.reader_memory import ArticleLike
from broadwai.retrieval import Collector, parse_feed, refresh_media_sources
from broadwai.sources import SourceInput
from broadwai.youtube import channel_feed, thumbnail, video_id
from tests.admin_fakes import AdminStore
from tests.fakes import (
    FakeCollector,
    FakeSearch,
    MemoryStore,
    ScriptedModel,
    article,
    finalize_first,
)
from tests.test_images import Fetcher
from tests.test_pipeline import pipeline, request

CHANNEL = "UCwI-JbGNsojunnHbFAc0M4Q"
ID = "LgNCc3Y0tgM"
FEED = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL}"


def video(index=0):
    item = article(index, extracted=False)
    return Article.create(
        url=f"https://www.youtube.com/watch?v={ID[:-1]}{index}",
        title=[
            "Python concurrency explained",
            "Rust ownership and lifetimes",
            "Comment fonctionne un ordinateur quantique",
            "Mars : l'eau et les roches",
        ][index],
        excerpt=item.excerpt,
        published_at=utcnow(),
        language="en",
        format="video",
        media={"provider": "youtube", "channel_title": "Science", "duration_seconds": 622},
    )


def test_youtube_atom_becomes_video_with_description_and_thumbnail():
    xml = f"""<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/">
      <title>ARTE</title><entry><yt:videoId>{ID}</yt:videoId>
      <yt:channelId>{CHANNEL}</yt:channelId><title>Original English title</title>
      <link href="https://www.youtube.com/shorts/{ID}"/>
      <published>2026-09-27T10:00:00Z</published><author><name>ARTE</name></author>
      <media:group><media:description>A documented subject, not a transcript.</media:description>
      <media:thumbnail url="http://localhost/spoofed"/></media:group>
      </entry></feed>"""
    item = parse_feed(xml.encode(), FEED, 15)[0]
    assert item.format == "video" and item.title == "Original English title"
    assert item.url == f"https://www.youtube.com/watch?v={ID}"
    assert item.image.url == f"https://i.ytimg.com/vi/{ID}/hqdefault.jpg"
    assert item.media["channel_title"] == "ARTE"
    assert item.extraction_status == "excerpt" and item.text == "" and not item.transcript
    assert item.reading_time_minutes is None
    assert item.excerpt == "A documented subject, not a transcript."


@pytest.mark.parametrize(
    "url",
    [
        f"https://youtu.be/{ID}?t=3",
        f"https://www.youtube.com/watch?v={ID}&feature=shared",
        f"https://m.youtube.com/shorts/{ID}",
        f"https://youtube.com/embed/{ID}",
    ],
)
def test_watch_aliases_share_identity(url):
    assert video_id(url) == ID
    xml = (
        "<rss><channel><item><title>Title</title><link>"
        + url.replace("&", "&amp;")
        + "</link></item></channel></rss>"
    )
    assert (
        parse_feed(xml.encode(), FEED, 1)[0].id
        == Article.create(url=f"https://www.youtube.com/watch?v={ID}", title="Title").id
    )


@pytest.mark.parametrize(
    "url",
    [
        f"https://youtube.com.evil.example/watch?v={ID}",
        f"https://youtube.com@evil.example/{ID}",
        f"https://www.youtube.com:444/watch?v={ID}",
        "https://youtube.com/watch?v=bad",
        f"https://evil.example/?v={ID}",
        f"javascript://youtube.com/watch?v={ID}",
    ],
)
def test_untrusted_urls_do_not_get_youtube_privileges(url):
    assert video_id(url) is None
    assert thumbnail(video().model_copy(update={"url": url})) is None


def test_channel_source_is_normalized_for_admin():
    source = SourceInput(name="ARTE", kind="website", url=f"https://youtube.com/channel/{CHANNEL}")
    assert source.url == FEED and source.kind == "rss"
    assert channel_feed(FEED) == FEED
    assert channel_feed(FEED.replace("youtube.com", "youtube.com.evil.example")) is None


async def test_video_extraction_never_reads_watch_page_as_transcript():
    item = video()
    fetcher = SimpleNamespace(get=AsyncMock(side_effect=AssertionError("No watch-page scraping")))
    result = await Collector(MemoryStore([item]), fetcher).extract(item)
    assert result.text == "" and result.extraction_status == "excerpt"
    fetcher.get.assert_not_awaited()


async def test_refresh_respects_disabled_channels_ttl_and_survives_failure():
    store = AdminStore()
    data = SourceInput(name="ARTE", url=FEED).model_dump()
    for name in ("due", "recent", "disabled"):
        row = store.save_source({**data, "name": name, "url": FEED + "&tag=" + name})
        store.sources[row["id"]]["enabled"] = name != "disabled"
        store.sources[row["id"]]["last_collected_at"] = (
            utcnow() - timedelta(minutes=5) if name == "recent" else None
        )
    collector = SimpleNamespace(ingest=AsyncMock(side_effect=RetrievalError("offline")))
    result = await refresh_media_sources(store, collector)
    assert len(result) == 1 and result[0]["errors"]
    assert collector.ingest.await_count == 1
    assert await refresh_media_sources(store, collector) == []


def test_generation_api_collects_registered_channel_before_editor_selection():
    store = AdminStore()
    store.save_source(SourceInput(name="ARTE", url=FEED).model_dump())
    xml = f"""<feed xmlns="http://www.w3.org/2005/Atom"><title>ARTE</title>
    <entry><title>Python explained</title><link href="https://youtube.com/watch?v={ID}"/>
    <published>{utcnow().isoformat()}</published><summary>{article().excerpt}</summary>
    <author><name>ARTE</name></author></entry></feed>"""
    fetcher = SimpleNamespace(get=AsyncMock(return_value=Download(FEED, xml.encode(), "text/xml")))
    app = create_app(
        Settings(_env_file=None),
        store=store,
        collector=Collector(store, fetcher),
        search=FakeSearch(),
        model=ScriptedModel([finalize_first]),
    )
    with TestClient(app) as client:
        req = request().model_dump(mode="json") | {"discover_videos": True}
        response = client.post("/v1/covers", json=req)
        assert response.status_code == 200
        assert response.json()["items"][0]["format"] == "video"
        assert response.json()["items"][0]["media"]["channel_title"] == "ARTE"
    assert fetcher.get.await_count == 1


async def test_thumbnail_uses_canonical_video_id_without_paid_image_review():
    item = video().model_copy(update={"image": ArticleImage(url="https://evil.example/logo.jpg")})
    image_url = thumbnail(item).url
    # Same bounded raster proxy as article images, with canonical YouTube artwork.
    body = b"\xff\xd8\xff" + b"thumbnail"
    fetcher = Fetcher({image_url: (body, "image/jpeg")})
    reviewer = SimpleNamespace(check=AsyncMock(return_value=False), close=AsyncMock())
    images = ArticleImages(MemoryStore([item]), fetcher, reviewer, require_review=True)
    assert await images.get(item.id) == (body, "image/jpeg")
    assert fetcher.calls == [image_url]
    reviewer.check.assert_not_awaited()
    await images.close()


async def test_video_runs_through_editor_without_fetch_and_preserves_evidence_limit():
    item = video()
    store = MemoryStore([item])
    collector = FakeCollector(store)
    cover = await pipeline(store, ScriptedModel([finalize_first]), collector=collector).run(
        request()
    )
    assert cover.items[0].format == "video" and cover.items[0].media == item.media
    assert cover.items[0].extraction_status == "excerpt"
    assert "sans transcription" in cover.items[0].brief.caveats[0]
    assert collector.calls == []


async def test_video_cap_is_enforced_even_for_invalid_model_finalization():
    store = MemoryStore([video(i) for i in range(4)])
    req = request(size=4).model_copy(update={"max_per_source": 10})
    cover = await pipeline(store, ScriptedModel([finalize_first])).run(req)
    assert len(cover.items) == 3
    assert all(item.format == "video" for item in cover.items)


async def test_video_recommendations_obey_reader_language_source_and_opt_out():
    for update in (
        {"max_videos": 0},
        {
            "profile": Profile(
                user_id="alice", interests=[Interest(topic="Python")], languages=["fr"]
            )
        },
        {
            "profile": Profile(
                user_id="alice",
                interests=[Interest(topic="Python")],
                excluded_sources=["youtube.com"],
            )
        },
    ):
        store = MemoryStore([video(), article()])
        cover = await pipeline(store, ScriptedModel([finalize_first])).run(
            request().model_copy(update=update)
        )
        assert all(item.format != "video" for item in cover.items)


async def test_video_survives_postgres_cover_like_and_collection_round_trip(pg_store):
    item = pg_store.put_article(video())
    cover = await pipeline(pg_store, ScriptedModel([finalize_first])).run(request())
    pg_store.set_like(
        ArticleLike(user_id="alice", cover_id=cover.id, article_id=item.id, liked=True)
    )
    assert pg_store.reading_memory("alice")["media_formats"] == {"video": 1}
    collections = Collections(pg_store)
    collection = collections.create("alice", CollectionInput(name="À regarder"))
    result = collections.add("alice", collection["id"], item.id, cover.id)
    assert result["items"][0]["format"] == "video"
    assert result["items"][0]["media"] == item.media
    with TestClient(create_app(Settings(_env_file=None), store=pg_store)) as client:
        response = client.get(f"/v1/covers/{cover.id}")
        assert response.status_code == 200
        assert response.json()["items"][0]["format"] == "video"


def test_mixed_feed_does_not_change_text_articles():
    xml = b"<rss><channel><item><title>Text</title><link>https://example.com/post</link></item></channel></rss>"
    result = parse_feed(xml, "https://example.com/rss", 1)[0]
    assert result.format == "article" and result.media is None and result.image is None
