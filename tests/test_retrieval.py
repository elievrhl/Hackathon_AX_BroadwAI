import asyncio
import socket
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from broadwai.models import Article, IngestRequest, canonical_url
from broadwai.network import Download, PublicFetcher, PublicResolver, RetrievalError
from broadwai.retrieval import Collector, parse_feed
from tests.fakes import MemoryStore

FEED = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<title>Example</title><language>fr</language>
<item><title>Python &amp; RSS</title><link>https://example.com/post?utm_source=rss</link>
<description>Une description assez longue pour comprendre le sujet de cet article.
</description>
<pubDate>Sat, 26 Sep 2026 10:00:00 GMT</pubDate></item>
<item><title>Internal</title><link>http://127.0.0.1/private</link></item>
</channel></rss>"""


def test_rss_dates_canonical_urls_and_local_links():
    articles = parse_feed(FEED, "https://example.com/rss", 10)
    assert len(articles) == 1
    assert articles[0].title == "Python & RSS"
    assert articles[0].url == "https://example.com/post"
    assert articles[0].published_at.isoformat() == "2026-09-26T10:00:00+00:00"


def test_atom_relative_link():
    body = b"""<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom</title>
    <entry><title>Article</title><link href="/post"/><summary>Contenu</summary></entry></feed>"""
    assert parse_feed(body, "https://example.com/feed", 2)[0].url == "https://example.com/post"


def test_canonicalization_preserves_semantic_query_parameters():
    assert (
        canonical_url("https://EXAMPLE.com/x?id=2&utm_source=a#top") == "https://example.com/x?id=2"
    )
    assert canonical_url("https://example.com/x?id=2") != canonical_url(
        "https://example.com/x?id=3"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://169.254.169.254/",
        "http://10.1.1.1/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://localhost/",
        "file:///etc/passwd",
        "https://user:password@example.com",
        "http://example.com:8080",
    ],
)
async def test_unsafe_destinations_never_download(url):
    with pytest.raises(RetrievalError):
        await PublicFetcher().get(url)


async def test_dns_rebinding_private_resolution_is_rejected(monkeypatch):
    async def fake_dns(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fake_dns)
    with pytest.raises(RetrievalError):
        await PublicResolver().resolve("attacker.example", 80)


async def test_ingestion_is_idempotent_and_partial_failures_are_reported():
    class Fetcher:
        async def get(self, url):
            if "broken" in url:
                raise RetrievalError("Indisponible")
            return Download(url, FEED, "application/rss+xml")

    store = MemoryStore()
    collector = Collector(store, Fetcher())
    req = IngestRequest(feed_urls=["https://example.com/rss", "https://broken.example/rss"])
    first = await collector.ingest(req)
    await collector.ingest(req)
    assert len(store.articles()) == 1
    assert first["collected"] == 1
    assert len(first["errors"]) == 1


async def test_extract_article_body_without_navigation():
    text = "Python permet de construire des systèmes distribués fiables. " * 20

    class Fetcher:
        async def get(self, url):
            return Download(
                url,
                '<html><body><nav><a href="https://nav.example/">Menu</a></nav>'
                f"<article><h1>Python</h1><p>{text} Selon "
                '<a href="https://study.example/report">le rapport du laboratoire</a>, '
                "ces systèmes sont plus fiables.</p></article></body></html>".encode(),
                "text/html",
            )

    store = MemoryStore()
    article = Article.create("https://example.com/post", "Python")
    extracted = await Collector(store, Fetcher()).extract(article)
    assert extracted.extraction_status == "extracted"
    assert "systèmes distribués" in extracted.text
    assert "Menu" not in extracted.text
    assert [link.url for link in extracted.content_links] == ["https://study.example/report"]
    assert "https://study.example" not in extracted.text


async def test_extract_rejects_interstitial_and_preserves_excerpt():
    class Fetcher:
        async def get(self, url):
            return Download(
                url,
                b"JavaScript is disabled in your browser. Please enable JavaScript to proceed. "
                b"A required part of this site could not load. Please check your connection.",
                "text/plain",
            )

    store = MemoryStore()
    article = Article.create("https://example.com/post", "Article", excerpt="Extrait RSS")
    store.put_article(article)
    with pytest.raises(RetrievalError, match="blocage"):
        await Collector(store, Fetcher()).extract(article)
    assert store.get_article(article.id).extraction_status == "excerpt"
    assert store.get_article(article.id).excerpt == "Extrait RSS"


async def test_web_discovery_preserves_typed_links_and_catalog_identity(monkeypatch):
    from broadwai.models import ArticleLink

    original = Article.create(
        "https://example.com/original",
        "Search result",
        discovery={"provider": "openai_web_search", "query": "fermentation"},
    )
    extracted = Article.create(
        "https://redirect.example/article",
        "Extracted title",
        text="A practical explanation of fermentation. " * 20,
        extraction_status="extracted",
        content_links=[ArticleLink(label="Study", url="https://study.example/paper")],
    )
    monkeypatch.setattr("broadwai.retrieval.website_article", lambda *_: extracted)

    class Fetcher:
        async def get(self, url):
            return Download(url, b"<article>Content</article>", "text/html")

    store = MemoryStore()
    result = await Collector(store, Fetcher()).extract(original)
    assert (result.id, result.url, result.source) == (original.id, original.url, original.source)
    assert result.discovery == original.discovery
    assert result.title == extracted.title
    assert result.content_links[0].url == "https://study.example/paper"
    assert result.content_hash == extracted.content_hash
    result.model_dump(warnings="error")


def mock_http(monkeypatch, responses):
    import aiohttp

    calls = []

    class Session:
        def __init__(self, **kwargs):
            self.connector = kwargs["connector"]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            await self.connector.close()

        @asynccontextmanager
        async def get(self, url, **kwargs):
            calls.append(url)
            yield responses.pop(0)

    monkeypatch.setattr(aiohttp, "ClientSession", Session)
    return calls


async def test_redirect_to_private_network_is_blocked_before_second_request(monkeypatch):
    redirect = SimpleNamespace(status=302, headers={"Location": "http://10.0.0.1/admin"})
    calls = mock_http(monkeypatch, [redirect])
    with pytest.raises(RetrievalError):
        await PublicFetcher().get("https://example.com/post")
    assert calls == ["https://example.com/post"]


async def test_decompressed_response_size_is_bounded(monkeypatch):
    class Content:
        async def iter_chunked(self, size):
            yield b"a" * 80
            yield b"b" * 80

    response = SimpleNamespace(
        status=200, headers={}, content=Content(), raise_for_status=lambda: None
    )
    mock_http(monkeypatch, [response])
    with pytest.raises(RetrievalError, match="volumineux"):
        await PublicFetcher(max_bytes=100).get("https://example.com/post")
