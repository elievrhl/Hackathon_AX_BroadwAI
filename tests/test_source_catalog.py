import json
import re
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from broadwai.models import utcnow
from broadwai.network import Download, RetrievalError
from broadwai.sources import SourceInput
from scripts.validate_source_catalog import check_source, export_sources, mark_duplicates, verify

ROOT = Path(__file__).resolve().parents[1]


def catalog_entry(status="ok", **overrides):
    return {
        "source": {"name": "Test", "kind": "rss", "url": "https://example.org/feed"},
        "topics": ["science"],
        "verification": {"status": status},
        **overrides,
    }


def test_curated_export_covers_the_actual_onboarding_topics_and_is_api_compatible():
    catalog = json.loads((ROOT / "examples/source-catalog.json").read_text(encoding="utf-8"))
    imported = json.loads((ROOT / "examples/sources-all-topics.json").read_text(encoding="utf-8"))
    ui = (ROOT / "frontend/src/reader.js").read_text(encoding="utf-8")
    topic_ids = set(re.findall(r"id: '([^']+)', label:", ui))
    assert {topic["id"] for topic in catalog["topics"]} == topic_ids
    assert imported == export_sources(catalog)
    assert len({entry["id"] for entry in catalog["sources"]}) == len(catalog["sources"])
    good = [entry for entry in catalog["sources"] if entry["verification"]["status"] == "ok"]
    for topic in topic_ids:
        entries = [entry for entry in good if topic in entry["topics"]]
        assert len(entries) >= 6, topic
        assert sum("fr" in entry["languages"] for entry in entries) >= 3, topic
        assert any("en" in entry["languages"] for entry in entries), topic
    for entry in catalog["sources"]:
        SourceInput.model_validate(entry["source"])
        assert set(entry["topics"]) <= topic_ids
        assert entry["selection_reason"] and entry["access_note"]
        assert entry["verification"].get("checked_at")


def test_export_filters_unverified_disabled_and_duplicate_sources_and_unknown_topics():
    enabled = catalog_entry()
    paused = deepcopy(enabled)
    paused["source"].update(enabled=False, url="https://paused.example.org/rss")
    catalog = {
        "topics": [{"id": "science"}, {"id": "art"}],
        "sources": [
            enabled,
            deepcopy(enabled),
            paused,
            catalog_entry("pending"),
            catalog_entry("failed"),
            catalog_entry("stale"),
            catalog_entry("review_required"),
            catalog_entry("ok", editorial_status="excluded"),
        ],
    }
    assert len(export_sources(catalog, {"science"})) == 1
    assert export_sources(catalog, {"art"}) == []
    with pytest.raises(ValueError, match="inconnus"):
        export_sources(catalog, {"missing"})


def test_redirect_and_content_aliases_are_excluded_but_bbc_sections_stay_distinct():
    def entry(id_, **verification):
        return catalog_entry(
            id=id_,
            source={"name": id_, "kind": "rss", "url": f"https://example.org/{id_}"},
            verification={"status": "ok", **verification},
        )

    original = entry(
        "original", resolved_url="https://example.org/canonical", content_fingerprint="abc"
    )
    redirect = entry("redirect", resolved_url="https://example.org/canonical")
    content = entry("content", content_fingerprint="abc")
    bbc_one = entry("science", feed_title="BBC News", feed_homepage="https://bbc.co.uk")
    bbc_two = entry("world", feed_title="BBC News", feed_homepage="https://bbc.co.uk")
    catalog = {
        "topics": [{"id": "science"}],
        "sources": [original, redirect, content, bbc_one, bbc_two],
    }
    assert mark_duplicates(catalog) == 2
    assert redirect["verification"]["duplicate_of"] == "original"
    assert len(export_sources(catalog)) == 3
    assert mark_duplicates(catalog) == 0


def test_distinct_aliases_with_same_feed_identity_are_excluded():
    source = catalog_entry(
        id="one",
        verification={
            "status": "ok",
            "feed_title": "Example Review",
            "feed_homepage": "https://www.example.org/",
        },
    )
    alias = deepcopy(source)
    alias["id"] = "two"
    alias["source"]["url"] = "https://example.org/other-feed"
    alias["verification"]["feed_homepage"] = "http://example.org/"
    assert mark_duplicates({"sources": [source, alias]}) == 1


def test_curated_videos_and_podcasts_have_auditable_provenance():
    catalog = json.loads((ROOT / "examples/source-catalog.json").read_text(encoding="utf-8"))
    selected = [e for e in catalog["sources"] if e["verification"]["status"] == "ok"]
    assert len(selected) >= 1000
    videos = [e for e in selected if e.get("format") == "youtube"]
    assert len(videos) == 8
    for entry in videos:
        assert entry["provenance_url"].startswith("https://")
        assert len(entry["quality_notes"]) >= 2
        assert entry["verification"]["feed_title"] == entry["expected_feed_title"]
    podcasts = [e for e in selected if e["source"]["kind"] == "podcast"]
    assert len(podcasts) == 6
    for entry in podcasts:
        proof = entry["provenance_verification"]
        assert proof["matches_feed"]
        assert proof["official_page"].startswith("https://www.radiofrance.fr/")
        assert proof["rss_link"] == entry["verification"]["resolved_url"]


def feed_download(title="Science", days_ago=1):
    date = (utcnow() - timedelta(days=days_ago)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    body = f"""<rss version="2.0"><channel><title>{title}</title>
    <item><title>Discovery</title><link>https://example.org/discovery</link>
    <description>Scientific findings</description><pubDate>{date}</pubDate></item>
    </channel></rss>"""
    return Download("https://example.org/feed", body.encode(), "application/rss+xml")


@pytest.mark.parametrize("days_ago,status", [(1, "ok"), (400, "stale"), (-5, "failed")])
async def test_validation_distinguishes_live_archived_and_future_dated_feeds(days_ago, status):
    fetcher = SimpleNamespace(get=AsyncMock(return_value=feed_download(days_ago=days_ago)))
    result = await check_source(catalog_entry(), fetcher)
    assert result["status"] == status


async def test_feed_identity_change_requires_editorial_review():
    fetcher = SimpleNamespace(get=AsyncMock(return_value=feed_download("Unrelated topic")))
    result = await check_source(catalog_entry(expected_feed_title="Science"), fetcher)
    assert result["status"] == "review_required"


async def test_technical_recheck_cannot_reactivate_editorially_excluded_source(monkeypatch):
    checker = AsyncMock(return_value={"status": "ok"})
    monkeypatch.setattr("scripts.validate_source_catalog.check_source", checker)
    entry = catalog_entry("review_required", editorial_status="excluded")
    await verify({"sources": [entry]})
    checker.assert_not_awaited()
    assert entry["verification"]["status"] == "review_required"


async def test_regular_feed_cannot_be_mislabeled_as_podcast():
    entry = catalog_entry()
    entry["source"]["kind"] = "podcast"
    fetcher = SimpleNamespace(get=AsyncMock(return_value=feed_download()))
    assert (await check_source(entry, fetcher))["status"] == "failed"


async def test_download_errors_remain_in_audit_and_are_not_exported():
    fetcher = SimpleNamespace(get=AsyncMock(side_effect=RetrievalError("Unavailable")))
    result = await check_source(catalog_entry(), fetcher)
    assert result["status"] == "failed"
    assert result["error"] == "Unavailable"


async def test_website_navigation_link_is_not_enough_to_pass_validation():
    entry = catalog_entry(
        source={"name": "School", "kind": "website", "url": "https://example.org/"},
        article_path_prefix="/news/",
    )
    listing = Download(
        "https://example.org/", b'<h2><a href="/sign-up">Sign up here</a></h2>', "text/html"
    )
    signup = Download(
        "https://example.org/sign-up", b"<h1>Subscribe</h1><form></form>", "text/html"
    )
    fetcher = SimpleNamespace(get=AsyncMock(side_effect=[listing, signup]))
    assert (await check_source(entry, fetcher))["status"] == "failed"
