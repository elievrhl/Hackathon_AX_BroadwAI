from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from xml.sax.saxutils import escape

import pytest
from fastapi.testclient import TestClient

from broadwai.api import create_app
from broadwai.collections import CollectionInput, Collections
from broadwai.config import Settings
from broadwai.images import ArticleImages
from broadwai.llm import summary_cache_version
from broadwai.models import Article, Brief, EditorialPick, Interest, Profile, utcnow
from broadwai.network import Download, RetrievalError
from broadwai.podcasts import duration_seconds
from broadwai.ranking import Ranked
from broadwai.reader_memory import ArticleLike
from broadwai.retrieval import Collector, parse_feed, refresh_media_sources
from broadwai.sources import SourceInput
from tests.admin_fakes import AdminStore
from tests.fakes import FakeSearch, MemoryStore, ScriptedModel, article, finalize_first
from tests.test_images import Fetcher
from tests.test_pipeline import pipeline, request

FEED = "https://publisher.example/podcast.xml"
DESCRIPTION = (
    "Un épisode sur Python et les systèmes distribués, "
    "les performances et la fiabilité des applications."
)


def entry(id_=1, *, link=None, duration="01:02:03", published=None, extra="", audio=None):
    link = f"<link>{escape(link)}</link>" if link else ""
    published = published or (utcnow() - timedelta(hours=1)).isoformat()
    return f'''<item><title>Python et systèmes distribués : épisode {id_}</title>{link}
    <guid isPermaLink="false">episode-{id_}</guid><description>{DESCRIPTION}</description>
    <pubDate>{published}</pubDate><itunes:duration>{duration}</itunes:duration>
    <enclosure url="{escape(audio or f"https://audio.example/{id_}.mp3")}" type="audio/mpeg"/>
    {extra}</item>'''


def feed(*entries):
    return (
        """<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel>
    <title>Sciences à écouter</title><link>https://publisher.example/</link><language>fr</language>
    <itunes:author>Un producteur</itunes:author>
    <itunes:image href="https://images.example/show-logo.jpg"/>"""
        + "".join(entries)
        + "</channel></rss>"
    ).encode()


def episode(id_=1):
    return parse_feed(feed(entry(id_, link=f"https://publisher.example/episode/{id_}")), FEED, 1)[0]


def test_episode_metadata_duration_artwork_and_no_invented_transcript():
    item = episode()
    assert item.format == "podcast" and item.url == "https://publisher.example/episode/1"
    assert item.source == "publisher.example" and item.language == "fr"
    assert item.media["show_title"] == "Sciences à écouter"
    assert item.media["audio_url"] == "https://audio.example/1.mp3"
    assert item.media["duration_seconds"] == 3723 and item.media["guid"] == "episode-1"
    assert item.image.url == "https://images.example/show-logo.jpg"
    assert item.extraction_status == "excerpt" and not item.text and not item.transcript
    assert item.reading_time_minutes is None


@pytest.mark.parametrize(
    "value, expected",
    [
        ("3600", 3600),
        ("59:02", 3542),
        ("01:02:03", 3723),
        ("", None),
        ("-1", None),
        ("01:99", None),
        ("1h", None),
        ("999999", None),
    ],
)
def test_duration_only_uses_valid_feed_values(value, expected):
    assert duration_seconds(value) == expected


def test_shared_homepages_and_missing_links_keep_distinct_playable_episodes():
    items = parse_feed(
        feed(
            entry(1, link="https://publisher.example/show"),
            entry(2, link="https://publisher.example/show"),
            entry(3),
        ),
        FEED,
        10,
    )
    assert len({item.id for item in items}) == 3
    assert [item.url for item in items] == [f"https://audio.example/{n}.mp3" for n in (1, 2, 3)]
    assert all(item.source == "publisher.example" for item in items)


def test_episode_artwork_precedes_show_and_unsafe_urls_are_ignored():
    body = feed(entry(extra='<itunes:image href="https://images.example/episode.jpg"/>'))
    assert parse_feed(body, FEED, 1)[0].image.url.endswith("/episode.jpg")
    body = feed(entry(extra='<itunes:image href="http://localhost/private"/>'))
    assert parse_feed(body, FEED, 1)[0].image.url.endswith("/show-logo.jpg")
    assert not parse_feed(feed(entry(audio="http://127.0.0.1/private.mp3")), FEED, 1)


def test_trailers_and_future_releases_do_not_take_the_episode_limit():
    body = feed(
        entry(1, extra="<itunes:episodeType>trailer</itunes:episodeType>"),
        entry(2, published=(utcnow() + timedelta(days=1)).isoformat()),
        entry(3),
    )
    result = parse_feed(body, FEED, 1)
    assert len(result) == 1 and result[0].media["guid"] == "episode-3"


async def test_no_audio_download_for_collection_or_editorial_extraction():
    body = feed(entry())
    fetcher = SimpleNamespace(
        get=AsyncMock(return_value=Download(FEED, body, "application/rss+xml"))
    )
    store = MemoryStore()
    collector = Collector(store, fetcher)
    from broadwai.models import IngestRequest

    result = await collector.ingest(IngestRequest(feed_urls=[FEED]))
    item = store.get_article(result["article_ids"][0])
    assert (await collector.extract(item)).extraction_status == "excerpt"
    assert fetcher.get.await_count == 1 and fetcher.get.call_args.args == (FEED,)


async def test_podcast_cover_uses_bounded_image_proxy_without_photo_review():
    item = episode()
    body = b"\xff\xd8\xff" + b"image"
    fetcher = Fetcher({item.image.url: (body, "image/jpeg")})
    reviewer = SimpleNamespace(check=AsyncMock(return_value=False), close=AsyncMock())
    images = ArticleImages(MemoryStore([item]), fetcher, reviewer, require_review=True)
    assert await images.get(item.id) == (body, "image/jpeg")
    reviewer.check.assert_not_awaited()
    await images.close()


async def test_description_is_labeled_and_podcast_quota_survives_bad_finalization():
    episodes = [episode(i) for i in (1, 2, 3)]
    titles = ["Python concurrency explained", "Distributed database consistency", "Rust ownership"]
    for item, title in zip(episodes, titles, strict=True):
        item.title = title
    cover = await pipeline(MemoryStore(episodes), ScriptedModel([finalize_first])).run(
        request(size=3)
    )
    assert len(cover.items) == 2
    assert all(
        item.format == "podcast" and item.reading_time_minutes is None for item in cover.items
    )
    assert all("sans transcription" in item.brief.caveats[0] for item in cover.items)


async def test_profile_exclusions_languages_and_disabled_podcasts_are_honored():
    for update in (
        {"max_podcasts": 0},
        {
            "profile": Profile(
                user_id="alice", interests=[Interest(topic="Python")], languages=["en"]
            )
        },
        {
            "profile": Profile(
                user_id="alice",
                interests=[Interest(topic="Python")],
                excluded_sources=["publisher.example"],
            )
        },
    ):
        cover = await pipeline(
            MemoryStore([episode(), article().model_copy(update={"language": "en"})]),
            ScriptedModel([finalize_first]),
        ).run(request().model_copy(update=update))
        assert not any(item.format == "podcast" for item in cover.items)


@pytest.mark.parametrize(
    "kind,status,accepted",
    [
        ("evergreen", "durable", True),
        ("news", "time_sensitive", False),
        ("evergreen", "uncertain", False),
    ],
)
async def test_old_description_is_reassessed_without_bypassing_temporal_checks(
    kind, status, accepted
):
    item = episode().model_copy(update={"published_at": utcnow() - timedelta(days=160)})
    store = MemoryStore([item])
    model = ScriptedModel()
    old = Brief(
        headline=item.title,
        summary=DESCRIPTION,
        key_points=["Systèmes distribués et fiabilité"],
        topics=["Python"],
        content_type="other",
        level="intermediate",
        language="fr",
        caveats=[],
        validity={
            "kind": "news",
            "status": "uncertain",
            "reason": "Absence de transcription",
            "evidence": DESCRIPTION,
        },
    )
    store.put_brief(item, model.summary_version, old)
    revised = old.model_copy(
        update={
            "validity": old.validity.model_copy(
                update={"kind": kind, "status": status, "reason": "Temporalité du sujet annoncé"}
            )
        }
    )
    model.summarize = AsyncMock(return_value=revised)
    pipe = pipeline(store, model)
    pipe.picks[item.id] = EditorialPick(
        article_id=item.id,
        section="Technique",
        score=85,
        reason="Entretien de fond",
        matches_profile=True,
        evergreen=True,
        temporal_kind="evergreen",
    )
    row = Ranked(item, 1, ["Python"])
    assert await pipe._prepare(row, request(), set()) is accepted
    model.summarize.assert_awaited_once()
    assert store.get_brief(item, model.summary_version) == old
    assert store.get_brief(
        item, summary_cache_version(item, model.summary_version)
    ) == revised.model_copy(
        update={"caveats": ["Fiche fondée sur la description de l’épisode, sans transcription."]}
    )
    # The corrected cache is reused on the next generation, even for a rejection.
    retry = pipeline(store, model)
    retry.picks = pipe.picks.copy()
    assert await retry._prepare(row, request(), set()) is accepted
    model.summarize.assert_awaited_once()


def test_description_cache_does_not_invalidate_articles_or_transcripts():
    for kind in ("podcast", "video", "article"):
        item = episode().model_copy(update={"format": kind})
        assert (summary_cache_version(item, "v1") != "v1") is (kind != "article")
        transcript = item.model_copy(update={"text": DESCRIPTION, "extraction_status": "extracted"})
        assert summary_cache_version(transcript, "v1") == "v1"


async def test_refresh_only_enabled_podcasts_and_failures_are_isolated():
    store = AdminStore()
    for name, enabled in [("active", True), ("paused", False)]:
        store.save_source(
            SourceInput(
                name=name, kind="podcast", url=FEED + "?" + name, enabled=enabled
            ).model_dump()
        )
    collector = SimpleNamespace(ingest=AsyncMock(side_effect=RetrievalError("offline")))
    reports = await refresh_media_sources(store, collector, videos=False, podcasts=True)
    assert len(reports) == 1 and reports[0]["errors"]
    assert await refresh_media_sources(store, collector, videos=False, podcasts=True) == []


def test_admin_source_collection_then_generation_api():
    store = AdminStore()
    fetcher = SimpleNamespace(get=AsyncMock(return_value=Download(FEED, feed(entry()), "text/xml")))
    app = create_app(
        Settings(_env_file=None),
        store=store,
        collector=Collector(store, fetcher),
        search=FakeSearch(),
        model=ScriptedModel([finalize_first]),
    )
    with TestClient(app) as client:
        source = client.post(
            "/v1/sources", json={"name": "Science", "kind": "podcast", "url": FEED}
        )
        assert source.status_code == 201
        assert (
            client.post(f"/v1/sources/{source.json()['id']}/collect").json()["results"][0][
                "collected"
            ]
            == 1
        )
        response = client.post(
            "/v1/covers", json=request().model_dump(mode="json") | {"discover_podcasts": True}
        )
        assert response.status_code == 200
        assert response.json()["items"][0]["format"] == "podcast"
    assert fetcher.get.await_count == 1  # the API respects the previous collection's TTL


async def test_postgres_podcast_source_likes_collections_and_legacy_transition(pg_store):
    pg_store.save_source(SourceInput(name="Science", kind="podcast", url=FEED).model_dump())
    item = episode()
    # A previously extracted episode webpage must not be mistaken for a transcript.
    legacy = Article.create(
        url=item.url, title=item.title, text="Old webpage", extraction_status="extracted"
    )
    pg_store.put_article(legacy)
    saved = pg_store.put_article(item)
    assert saved.format == "podcast" and saved.extraction_status == "excerpt" and saved.text == ""
    pg_store.put_article(item)
    assert len(pg_store.articles()) == 1
    cover = await pipeline(pg_store, ScriptedModel([finalize_first])).run(request())
    pg_store.set_like(
        ArticleLike(user_id="alice", cover_id=cover.id, article_id=item.id, liked=True)
    )
    assert pg_store.reading_memory("alice")["media_formats"] == {"podcast": 1}
    collections = Collections(pg_store)
    collection = collections.create("alice", CollectionInput(name="À écouter"))
    result = collections.add("alice", collection["id"], item.id, cover.id)
    assert result["items"][0]["media"]["duration_seconds"] == 3723
    assert result["items"][0]["format"] == "podcast"


def test_rotating_cdn_metadata_does_not_invalidate_the_summary():
    item = episode()
    refreshed = item.model_copy(
        update={
            "media": item.media
            | {
                "audio_url": "https://audio.example/1.mp3?token=next",
                "artwork_url": "https://images.example/new.jpg",
            }
        }
    )
    assert item.content_hash == refreshed.content_hash
    assert (
        item.content_hash != item.model_copy(update={"excerpt": "A changed subject"}).content_hash
    )
