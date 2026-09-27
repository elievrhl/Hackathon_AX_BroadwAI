from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from broadwai.models import IngestRequest
from broadwai.network import Download, RetrievalError
from broadwai.ranking import rank
from broadwai.retrieval import Collector
from broadwai.youtube import metadata_duration
from tests.fakes import FakeSearch, MemoryStore, ScriptedModel, article, decision, finalize_first
from tests.test_pipeline import pipeline, request
from tests.test_youtube import FEED, video, watch_page


@pytest.mark.parametrize(
    ("duration", "allowed"),
    [
        (None, False),
        (0, False),
        (-1, False),
        (299.99, False),
        (300, False),
        (300.01, True),
        (301, True),
        (622, True),
        ("622", False),
        (True, False),
        (float("nan"), False),
        (float("inf"), False),
        (float("-inf"), False),
        ([], False),
        ({}, False),
        (10**400, False),
    ],
)
def test_video_duration_is_strictly_over_five_minutes_before_ranking(duration, allowed):
    item = video().model_copy(update={"media": {"duration_seconds": duration}})
    assert bool(rank([item], request().profile)) is allowed


@pytest.mark.parametrize("content_format", ["article", "podcast", "animation"])
def test_video_minimum_does_not_filter_other_formats(content_format):
    item = article().model_copy(update={"format": content_format, "media": None})
    assert [row.article.id for row in rank([item], request().profile)] == [item.id]


def test_legacy_youtube_link_cannot_bypass_duration_check_with_article_format():
    item = video().model_copy(update={"format": "article", "media": None})
    assert rank([item], request().profile) == []


def page_for(item, duration="PT10M22S", *, canonical=None):
    body = (
        f'<html><head><link rel="canonical" href="{canonical or item.url}">'
        f'<meta itemprop="duration" content="{duration}"></head>'
        '<body><script>{"relatedVideo": {"lengthSeconds": "9999"}}</script></body></html>'
    )
    return Download(item.url, body.encode(), "text/html")


@pytest.mark.parametrize(
    ("duration", "seconds"),
    [
        ("PT5M", 300),
        ("PT5M0.5S", 300.5),
        ("PT1H2M3S", 3723),
        ("PT622S", 622),
        ("PT0S", None),
        ("PT", None),
        ("", None),
        ("622", None),
    ],
)
def test_duration_comes_from_primary_video_metadata(duration, seconds):
    item = video()
    assert metadata_duration(page_for(item, duration).body, item.url.split("=")[1]) == seconds


def test_duration_from_another_video_or_consent_page_is_ignored():
    item = video()
    body = page_for(item, canonical=video(1).url).body
    assert metadata_duration(body, item.url.split("=")[1]) is None
    assert metadata_duration(b'<meta itemprop="duration" content="PT30M">', "unknown") is None


@pytest.mark.parametrize("player_options", [{"live": True}, {"status": "LOGIN_REQUIRED"}])
async def test_html_fallback_cannot_restore_an_unavailable_or_live_player_duration(player_options):
    item = video().model_copy(update={"media": {"provider": "youtube"}})
    id_ = item.url.split("=")[1]
    body = page_for(item).body + watch_page(id_, **player_options)
    assert metadata_duration(body, id_) is None
    fetcher = SimpleNamespace(get=AsyncMock(return_value=Download(item.url, body, "text/html")))
    enriched = await Collector(MemoryStore(), fetcher).enrich_media_duration(item)
    assert not enriched.media.get("duration_seconds")


def feed_for(item):
    xml = (
        '<feed xmlns="http://www.w3.org/2005/Atom"><title>Science</title>'
        f'<entry><title>{item.title}</title><link href="{item.url}"/>'
        f"<summary>{item.excerpt}</summary></entry></feed>"
    )
    return Download(FEED, xml.encode(), "text/xml")


@pytest.mark.parametrize("extracted", [False, True])
async def test_collection_keeps_verified_duration_and_imported_transcript(extracted):
    item = video()
    if extracted:
        item = item.model_copy(
            update={
                "text": "A supplied transcript. " * 10,
                "extraction_status": "extracted",
                "transcript": [{"start": 0, "end": 10, "text": "A supplied transcript."}],
                "media": {**item.media, "duration_seconds": None},
            }
        )
    store = MemoryStore([item] if extracted else [])
    fetcher = SimpleNamespace(
        get=AsyncMock(
            side_effect=[
                feed_for(item),
                page_for(item),
                feed_for(item),
            ]
        )
    )
    collector = Collector(store, fetcher)
    for _ in range(2):
        result = await collector.ingest(IngestRequest(feed_urls=[FEED]))
        assert result["collected"] == 1 and not result["errors"]
        saved = store.get_article(item.id)
        assert saved.media["duration_seconds"] == 622
        assert saved.text == item.text and saved.transcript == item.transcript
    assert [call.args[0] for call in fetcher.get.await_args_list] == [FEED, item.url, FEED]


@pytest.mark.parametrize("failure", [RetrievalError("offline"), TimeoutError()])
async def test_missing_duration_does_not_break_collection_or_allow_a_recommendation(failure):
    item = video()
    store = MemoryStore()
    fetcher = SimpleNamespace(get=AsyncMock(side_effect=[feed_for(item), failure]))
    result = await Collector(store, fetcher).ingest(IngestRequest(feed_urls=[FEED]))
    assert result["collected"] == 1 and not result["errors"]
    assert rank(store.articles(), request().profile) == []


@pytest.mark.parametrize("duration", [None, 299, 300, 301])
@pytest.mark.parametrize("discovered", [False, True])
async def test_duration_requirement_holds_for_catalog_and_web_discovery(duration, discovered):
    item = video().model_copy(update={"media": {"duration_seconds": duration}})
    store = MemoryStore([] if discovered else [item])
    decisions = [decision("search_web", query="Python")] if discovered else []
    model = ScriptedModel(
        [
            *decisions,
            lambda state: finalize_first(state) if state["candidates"] else decision(selections=[]),
        ]
    )
    cover = await pipeline(store, model, FakeSearch([item] if discovered else [])).run(request())
    assert [result.article_id for result in cover.items] == ([item.id] if duration == 301 else [])
    assert model.summary_calls == (1 if duration == 301 else 0)


async def test_invalid_model_choice_cannot_restore_a_short_video_in_fallback():
    short = video().model_copy(update={"media": {"duration_seconds": 300}})
    written = article()
    model = ScriptedModel(
        [
            decision(
                selections=[
                    {
                        "article_id": short.id,
                        "section": "Technique",
                        "reason": "Invalid choice",
                    }
                ]
            )
        ]
    )
    cover = await pipeline(MemoryStore([short, written]), model, max_agent_steps=1).run(request())
    assert cover.status == "fallback"
    assert [item.article_id for item in cover.items] == [written.id]
    assert model.summary_calls == 1
