import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from broadwai.api import create_app
from broadwai.config import Settings
from broadwai.discovery import validate_source
from broadwai.llm import BudgetExceeded, RunBudget
from broadwai.models import IngestRequest
from broadwai.network import Download, RetrievalError
from broadwai.retrieval import Collector
from broadwai.website import article_links, website_article
from tests.admin_fakes import AdminStore
from tests.fakes import MemoryStore, ScriptedModel, article, decision
from tests.test_pipeline import pipeline, request
from tests.test_retrieval import FEED

ROOT = "https://example.com/blog/"
TEXT = "Les outils ouverts permettent de construire des applications fiables et accessibles. " * 12


def page(body, url=ROOT, content_type="text/html"):
    return Download(url, body.encode(), content_type)


def story(url="https://example.com/posts/first", *, text=TEXT, extra=""):
    return page(
        '<html lang="fr-FR"><head><meta charset="utf-8">'
        '<title>Des outils ouverts pour tous</title><meta property="og:type" content="article">'
        '<meta property="article:published_time" content="2026-01-12T10:00:00Z">'
        f'<meta name="description" content="{TEXT[:160]}">{extra}</head>'
        f"<body><nav>Menu du journal</nav><article><h1>Des outils ouverts pour tous</h1>"
        f"<p>{text}</p></article></body></html>",
        url,
    )


LISTING = page(
    '<h1>Derniers articles</h1><article><h2><a href="/posts/first">'
    "Des outils ouverts pour tous</a></h2></article>"
)


def fetcher_for(downloads):
    async def get(url):
        result = downloads[url]
        if isinstance(result, Exception):
            raise result
        return result

    return SimpleNamespace(get=AsyncMock(side_effect=get))


def test_links_prioritize_articles_resolve_redirect_base_and_filter_navigation():
    listing = page(
        """<html><body>
        <nav><a href="/world">Actualités internationales</a></nav>
        <footer><a href="/legal">Les informations légales</a></footer>
        <a href="/ordinary-post">Un titre hors des balises article</a>
        <article><h2><a href="first?utm_source=blog#top">Premier article</a></h2>
        <a href="first">Lire la suite</a><h2><a href="/second?id=42">Deuxième article</a></h2>
        </article>
        <h2><a href="http://127.0.0.1/private">Lien privé</a></h2>
        <h2><a href="https://elsewhere.example/story">Lien externe</a></h2>
        <h2><a href="https://user:pass@example.com/secret">Identifiants</a></h2>
        <h2><a href="mailto:test@example.com">Contact</a></h2>
        <h2><a href="/subscribe">Abonnement</a></h2><h2><a href="/tag/python">Un tag</a></h2>
        <h2><a href="/image.pdf">PDF</a></h2><h2><a href="#top">Haut de page</a></h2>
        <h2><a href="http://[invalid">URL malformée</a></h2>
        </body></html>""",
        "https://www.example.com/blog/",
    )
    assert article_links(listing, 10) == [
        "https://www.example.com/blog/first",
        "https://www.example.com/second?id=42",
        "https://www.example.com/ordinary-post",
    ]
    assert article_links(listing, 1) == ["https://www.example.com/blog/first"]


def test_structured_lists_and_malformed_json():
    data = {
        "@graph": [
            {
                "@type": "ItemList",
                "itemListElement": [
                    {"@type": "ListItem", "item": {"@type": "NewsArticle", "url": "/posts/one"}},
                    {"@type": "BlogPosting", "url": "/posts/two"},
                ],
            }
        ]
    }
    listing = page(
        '<html><head><script type="application/ld+json">broken</script>'
        f'<script type="application/ld+json">{json.dumps(data)}</script></head><body></body></html>'
    )
    assert article_links(listing, 10) == [
        "https://example.com/posts/one",
        "https://example.com/posts/two",
    ]


def test_heading_navigation_does_not_displace_article_permalinks():
    listing = page(
        '<html><body><h2><span class="section-nav"><a href="/entries/">Entries</a>'
        '<a href="/notes/">Notes</a></span></h2><h3><a rel="bookmark" href="/post">'
        "Un nouvel article</a></h3></body></html>"
    )
    assert article_links(listing, 2) == ["https://example.com/post"]


def test_archive_with_incorrect_article_metadata_is_rejected():
    listing = page(
        "<html><head><title>Mon journal</title>"
        '<meta property="og:site_name" content="Mon journal">'
        '<meta property="og:type" content="article"></head><body>'
        f"<h1>Mon journal</h1><p>{TEXT}</p></body></html>"
    )
    with pytest.raises(RetrievalError, match="archives"):
        website_article(listing, ROOT)


def test_listing_with_embedded_article_schemas_is_not_itself_an_article():
    data = {
        "@graph": [
            {"@type": "NewsArticle", "url": "/first"},
            {"@type": "NewsArticle", "url": "/second"},
        ]
    }
    listing = page(
        "<html><head><title>Rubrique</title>"
        f'<script type="application/ld+json">{json.dumps(data)}</script></head>'
        f"<body><article><p>{TEXT}</p></article><article>{TEXT}</article></body></html>"
    )
    with pytest.raises(RetrievalError, match="identifiable"):
        website_article(listing, ROOT)


def test_article_metadata_text_and_untrusted_canonical():
    item = website_article(
        story(extra='<link rel="canonical" href="http://localhost/private">'), ROOT
    )
    assert item.url == "https://example.com/posts/first"
    assert item.title == "Des outils ouverts pour tous"
    assert item.language == "fr"
    assert item.published_at.isoformat().startswith("2026-01-12")
    assert item.extraction_status == "extracted"
    assert "outils ouverts" in item.text and "Menu du journal" not in item.text
    assert item.discovery["source_url"] == ROOT


def test_metadata_excerpt_survives_unavailable_article_body():
    item = website_article(story(text="Abonnez-vous pour lire la suite."), ROOT)
    assert item.extraction_status == "excerpt"
    assert item.excerpt and not item.text


def test_article_retains_content_links_without_navigation_and_invalid_urls():
    item = website_article(
        story(
            text=TEXT + ' Selon <a href="/study?utm_source=ref">le rapport</a>, '
            'les outils sont utiles. <a href="/study">Même étude</a> '
            '<a href="http://127.0.0.1/private">Lien interne</a> '
            '<a href="javascript:alert(1)">Action</a>'
        ),
        ROOT,
    )
    assert [link.model_dump() for link in item.content_links] == [
        {"label": "le rapport", "url": "https://example.com/study"}
    ]
    assert "Selon le rapport" in item.text
    assert item.content_hash != item.model_copy(update={"content_links": []}).content_hash


@pytest.mark.parametrize(
    "download",
    [
        page("<h1>Rubrique</h1><p>Actualités</p><article>Un</article><article>Deux</article>"),
        page("<h1>Application</h1><script>loadArticles()</script>"),
        page("not html", content_type="application/pdf"),
        story(url="https://elsewhere.example/article"),
        page(
            "<title>Verify you are human</title><article><h1>Verify you are human</h1>"
            f"<p>{'Verify you are human. ' * 10}</p></article>"
        ),
    ],
)
def test_non_articles_and_blocked_pages_are_rejected(download):
    with pytest.raises(RetrievalError):
        website_article(download, ROOT)


async def test_collection_partial_failures_limits_and_repeat_import():
    listing = page(
        "".join(f'<h2><a href="/posts/{i}">Article numéro {i}</a></h2>' for i in range(10))
    )
    fetcher = fetcher_for(
        {
            ROOT: listing,
            **{
                f"https://example.com/posts/{i}": story(f"https://example.com/posts/{i}")
                if i
                else RetrievalError("Indisponible")
                for i in range(4)
            },
        }
    )
    store = MemoryStore()
    collector = Collector(store, fetcher)
    req = IngestRequest(website_urls=[ROOT], limit_per_source=2)
    report = await collector.ingest(req)
    assert report["collected"] == 2
    assert len(report["errors"]) == 1
    assert len(fetcher.get.call_args_list) == 5  # listing + at most twice the requested limit
    again = await collector.ingest(req)
    assert again["article_ids"] == report["article_ids"]
    assert len(store.articles()) == 2


async def test_empty_website_does_not_prevent_other_sources():
    fetcher = fetcher_for(
        {
            ROOT: page("<html><body><h1>Blog</h1></body></html>"),
            "https://example.com/rss": Download(
                "https://example.com/rss",
                FEED,
                "application/rss+xml",
            ),
        }
    )
    report = await Collector(MemoryStore(), fetcher).ingest(
        IngestRequest(
            website_urls=[ROOT],
            feed_urls=["https://example.com/rss"],
        )
    )
    assert report["collected"] == 1
    assert "Aucun lien" in report["errors"][0]["error"]


def test_website_source_api_collect_edit_pause_and_direct_ingest():
    store = AdminStore()
    collector = Collector(
        store, fetcher_for({ROOT: LISTING, "https://example.com/posts/first": story()})
    )
    app = create_app(Settings(_env_file=None), store=store, collector=collector)
    with TestClient(app) as client:
        data = {"name": "Blog sans flux", "kind": "website", "url": ROOT, "limit_per_source": 2}
        created = client.post("/v1/sources", json=data)
        assert created.status_code == 201
        source = created.json()
        assert client.post("/v1/sources", json=data).status_code == 409
        result = client.post(f"/v1/sources/{source['id']}/collect").json()["results"][0]
        assert result["collected"] == 1 and result["errors"] == []
        saved = client.get("/v1/sources").json()[0]
        assert saved["kind"] == "website" and saved["article_count"] == 1
        assert client.get(f"/v1/admin/articles?source_id={source['id']}").json()["total"] == 1
        assert (
            client.put(f"/v1/sources/{source['id']}", json={**data, "enabled": False}).status_code
            == 200
        )
        assert client.post("/v1/sources/collect").json()["results"] == []
        direct = client.post("/v1/ingest", json={"website_urls": [ROOT]})
        assert direct.status_code == 200 and direct.json()["collected"] == 1
        assert client.delete(f"/v1/sources/{source['id']}").status_code == 204
        assert len(store.articles()) == 1


@pytest.mark.parametrize("url", ["http://127.0.0.1/blog", "http://localhost/", "file:///test"])
def test_website_source_rejects_non_public_urls(url):
    from broadwai.sources import SourceInput

    with pytest.raises(ValueError):
        SourceInput(name="Blog", kind="website", url=url)


async def test_proposal_verifies_an_article_and_keeps_website_kind():
    store = MemoryStore()
    store.propose_source = lambda url, name, reason, origin, kind: {
        "id": "proposal",
        "url": url,
        "kind": kind,
        "status": "proposed",
    }
    collector = Collector(
        store, fetcher_for({ROOT: LISTING, "https://example.com/posts/first": story()})
    )
    runner = pipeline(store, ScriptedModel(), collector=collector)
    runner.discovered = {"blog": article().model_copy(update={"url": ROOT})}
    result = await runner._act(decision("propose_source", source_url=ROOT), request(), set())
    assert result["kind"] == "website" and result["url"] == ROOT
    assert store.articles() == []  # validation does not activate collection
    assert runner.budget.counts["source_fetch"] == 2


async def test_proposal_prefers_feed_and_website_validation_respects_budget():
    listing = page('<link type="application/rss+xml" href="/feed">' + LISTING.body.decode())
    fetcher = fetcher_for(
        {
            ROOT: listing,
            "https://example.com/feed": Download(
                "https://example.com/feed",
                FEED,
                "application/rss+xml",
            ),
        }
    )
    assert await validate_source(fetcher, ROOT) == ("rss", "https://example.com/feed")
    budget = RunBudget({"source_fetch": 1}, 1000)
    fetcher = fetcher_for({ROOT: LISTING})
    with pytest.raises(BudgetExceeded):
        await validate_source(fetcher, ROOT, budget)
    assert fetcher.get.call_count == 1


async def test_unusable_website_proposal_is_rejected():
    fetcher = fetcher_for(
        {ROOT: LISTING, "https://example.com/posts/first": page("<h1>Login</h1>")}
    )
    with pytest.raises(RetrievalError, match="Aucun flux ni article"):
        await validate_source(fetcher, ROOT)


async def test_broken_and_private_feed_links_do_not_block_website_proposals():
    listing = page(
        '<link type="application/rss+xml" href="http://[broken">'
        '<link type="application/rss+xml" href="http://localhost/feed">'
        '<a href="http://[broken">Invalid</a>' + LISTING.body.decode()
    )
    fetcher = fetcher_for({ROOT: listing, "https://example.com/posts/first": story()})
    assert await validate_source(fetcher, ROOT) == ("website", ROOT)
    assert fetcher.get.call_count == 2


async def test_proposal_fallback_after_broken_feeds_stays_within_five_downloads():
    listing = page(
        "".join(f'<link type="application/rss+xml" href="/feed/{i}">' for i in range(5))
        + LISTING.body.decode()
    )
    fetcher = fetcher_for(
        {
            ROOT: listing,
            "https://example.com/posts/first": story(),
            **{
                f"https://example.com/feed/{i}": RetrievalError("Flux inaccessible")
                for i in range(3)
            },
        }
    )
    budget = RunBudget({"source_fetch": 5}, 1000)
    assert await validate_source(fetcher, ROOT, budget) == ("website", ROOT)
    assert budget.counts["source_fetch"] == fetcher.get.call_count == 5
