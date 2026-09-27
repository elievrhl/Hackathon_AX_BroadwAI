import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from broadwai.models import Article, utcnow
from broadwai.network import Download, RetrievalError
from broadwai.ranking import similarity
from broadwai.retrieval import Collector
from broadwai.youtube import summary_video_id, video_metadata
from tests.fakes import FakeSearch, MemoryStore, ScriptedModel, decision, finalize_first
from tests.test_pipeline import pipeline, request

VIDEO_ID = "bLSLN96Gn-w"
SUMMARY_URL = f"https://www.recapcraft.com/v/{VIDEO_ID}/"
WATCH_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"
DESCRIPTION = (
    "Python : la description originale, sans résumé automatique ni transcription. " * 3
).strip()


def summary_article():
    return Article.create(
        SUMMARY_URL,
        "Python - Summary & Key Points",
        text="Un résumé automatique tiers qui ne doit jamais devenir une transcription. " * 20,
        extraction_status="extracted",
        published_at=utcnow(),
    )


def watch_page(duration="PT27M29S", expected_id=VIDEO_ID):
    player = {
        "videoDetails": {
            "videoId": expected_id,
            "title": "Python, la vidéo originale",
            "shortDescription": DESCRIPTION,
            "author": "Créateur original",
            "channelId": "UCQsVmhSa4X-G3lHlUtejzLA",
        }
    }
    body = (
        f'<link rel="canonical" href="{WATCH_URL}">'
        f'<meta itemprop="duration" content="{duration}">'
        f'<meta itemprop="datePublished" content="{utcnow().isoformat()}">'
        f"<script>var ytInitialPlayerResponse = {json.dumps(player)};"
        'var recommendations = {"lengthSeconds": "9000", "title": "Wrong video"};</script>'
    )
    return Download(WATCH_URL, body.encode(), "text/html")


@pytest.mark.parametrize("host", ["www.recapcraft.com", "recapcraft.com"])
def test_summary_permalink_identifies_original_video(host):
    assert summary_video_id(f"https://{host}/v/{VIDEO_ID}/?utm_source=mail") == VIDEO_ID


@pytest.mark.parametrize(
    "url",
    [
        f"https://recapcraft.com.evil.example/v/{VIDEO_ID}/",
        f"https://recapcraft.com@evil.example/v/{VIDEO_ID}/",
        f"https://recapcraft.com:444/v/{VIDEO_ID}/",
        f"https://example.org/article?video={VIDEO_ID}",
        f"javascript://recapcraft.com/v/{VIDEO_ID}/",
        "https://recapcraft.com/v/invalid/",
        "https://recapcraft.com/about/",
    ],
)
def test_regular_articles_and_untrusted_links_are_not_replaced(url):
    assert summary_video_id(url) is None


def test_metadata_must_describe_the_primary_video():
    metadata = video_metadata(watch_page().body, VIDEO_ID)
    assert metadata["title"] == "Python, la vidéo originale"
    assert metadata["excerpt"] == DESCRIPTION
    assert metadata["media"]["duration_seconds"] == 1649
    assert metadata["media"]["channel_title"] == "Créateur original"
    assert metadata["published_at"] is not None
    assert video_metadata(watch_page(expected_id="LgNCc3Y0tgM").body, VIDEO_ID) is None
    assert video_metadata(b'<meta itemprop="duration" content="PT27M29S">', VIDEO_ID) is None


async def test_cached_summary_becomes_original_video_and_preserves_saved_identity():
    summary = summary_article()
    store = MemoryStore([summary])
    fetcher = SimpleNamespace(get=AsyncMock(return_value=watch_page()))
    collector = Collector(store, fetcher)
    original = await collector.extract(summary)
    assert original.id == summary.id
    assert original.url == WATCH_URL and original.source == "www.youtube.com"
    assert original.format == "video" and original.media["duration_seconds"] == 1649
    assert original.title == "Python, la vidéo originale"
    assert original.excerpt == DESCRIPTION
    assert not original.text and not original.transcript and not original.content_links
    assert original.extraction_status == "excerpt" and original.reading_time_minutes is None
    assert original.discovery["original_summary_url"] == SUMMARY_URL
    assert original.image.url == f"https://i.ytimg.com/vi/{VIDEO_ID}/hqdefault.jpg"
    assert await collector.extract(summary) == original
    fetcher.get.assert_awaited_once_with(WATCH_URL)


@pytest.mark.parametrize(
    ("duration", "max_videos", "count"),
    [
        ("PT27M29S", 3, 1),
        ("PT5M", 3, 0),
        ("", 3, 0),
        ("PT27M29S", 0, 0),
    ],
)
async def test_original_video_keeps_video_duration_and_quota_rules(duration, max_videos, count):
    store = MemoryStore([summary_article()])
    fetcher = SimpleNamespace(get=AsyncMock(return_value=watch_page(duration)))
    model = ScriptedModel(
        [lambda state: finalize_first(state) if state["candidates"] else decision(selections=[])]
    )
    req = request().model_copy(update={"max_videos": max_videos})
    cover = await pipeline(store, model, collector=Collector(store, fetcher)).run(req)
    assert len(cover.items) == count
    assert model.summary_calls == count
    if count:
        item = cover.items[0]
        assert item.url == WATCH_URL and item.format == "video"
        assert item.brief.summary == DESCRIPTION and item.reading_time_minutes is None
        assert "sans transcription" in item.brief.caveats[0]


async def test_unavailable_original_never_falls_back_to_cached_summary():
    store = MemoryStore([summary_article()])
    fetcher = SimpleNamespace(get=AsyncMock(side_effect=RetrievalError("offline")))
    model = ScriptedModel([decision(selections=[])])
    cover = await pipeline(store, model, collector=Collector(store, fetcher)).run(request())
    assert not cover.items and model.summary_calls == 0
    assert any("offline" in warning for warning in cover.warnings)


async def test_web_discovered_youtube_url_gets_metadata_before_duration_filter():
    found = Article.create(WATCH_URL, "Python from search")
    store = MemoryStore()
    fetcher = SimpleNamespace(get=AsyncMock(return_value=watch_page()))
    model = ScriptedModel([decision("search_web", query="Python"), finalize_first])
    cover = await pipeline(
        store, model, FakeSearch([found]), collector=Collector(store, fetcher)
    ).run(request())
    assert len(cover.items) == 1
    assert cover.items[0].url == WATCH_URL and cover.items[0].format == "video"
    assert cover.items[0].media["duration_seconds"] == 1649


def test_summary_and_original_are_the_same_story_even_when_the_titles_differ():
    original = Article.create(WATCH_URL, "A completely different original title")
    assert similarity(summary_article(), original) == 1.0


async def test_replacement_persists_in_postgres_without_losing_the_existing_id(pg_store):
    summary = pg_store.put_article(summary_article())
    fetcher = SimpleNamespace(get=AsyncMock(return_value=watch_page()))
    original = await Collector(pg_store, fetcher).extract(summary)
    saved = pg_store.get_article(summary.id)
    assert saved == original and saved.url == WATCH_URL and saved.format == "video"
    assert saved.media["duration_seconds"] == 1649
