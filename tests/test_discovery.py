from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from broadwai.discovery import validate_feed
from broadwai.llm import BudgetExceeded, RunBudget
from broadwai.network import Download, RetrievalError
from broadwai.web_search import OpenAIWebSearch, open_web_query
from tests.fakes import FakeCollector, FakeSearch, MemoryStore, ScriptedModel, article, decision
from tests.test_pipeline import pipeline, request
from tests.test_retrieval import FEED


async def test_discovery_option_does_not_force_search_when_catalog_suffices():
    from tests.fakes import finalize_first

    store = MemoryStore([article()])
    model = ScriptedModel(
        [
            finalize_first,
            decision("search_web", query="Python"),
            finalize_first,
        ]
    )
    runner = pipeline(store, model, FakeSearch())
    req = request().model_copy(update={"discover_web": True})
    cover = await runner.run(req)
    assert cover.status == "complete"
    assert [event.action for event in cover.trace] == ["finalize"]
    assert runner.search.queries == []
    assert model.states[0]["research"]["needed"] is False
    assert not cover.usage["calls"].get("search_web")


async def test_hosted_search_imports_only_safe_citations_and_accounts_usage():
    response = SimpleNamespace(
        status="completed",
        usage=SimpleNamespace(input_tokens=100, output_tokens=25),
        model_dump=lambda: {
            "output": [
                {"type": "web_search_call", "status": "completed"},
                {
                    "type": "message",
                    "content": [
                        {
                            "text": "Invented summary",
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "url": "https://example.com/post",
                                    "title": "Article",
                                },
                                {
                                    "type": "url_citation",
                                    "url": "http://127.0.0.1/private",
                                    "title": "Private",
                                },
                                {
                                    "type": "url_citation",
                                    "url": "https://example.com/post",
                                    "title": "Article",
                                },
                            ],
                        }
                    ],
                },
            ]
        },
    )
    create = AsyncMock(return_value=response)
    model = SimpleNamespace(
        editor_model="test", client=SimpleNamespace(responses=SimpleNamespace(create=create))
    )
    budget = RunBudget({"web_model": 1}, 50000)
    results = await OpenAIWebSearch(model).search("Python", budget)
    assert len(results) == 1
    assert results[0].text == results[0].excerpt == ""
    assert budget.input_tokens == 100
    assert budget.counts["hosted_web_calls"] == 1
    assert create.call_args.kwargs["tools"][0]["type"] == "web_search"
    assert create.call_args.kwargs["max_tool_calls"] == 1
    with pytest.raises(BudgetExceeded):
        await OpenAIWebSearch(model).search("Python", budget)
    assert create.await_count == 1


def test_domain_allowlists_are_removed_without_removing_explicit_exclusions():
    query = "Singapore arts (site:reuters.com OR SITE:bbc.com) -site:spam.example"
    assert open_web_query(query) == "Singapore arts -site:spam.example"
    assert open_web_query('Singapore site: "example.com" AND culture') == "Singapore culture"
    assert open_web_query("arts OR culture") == "arts OR culture"
    with pytest.raises(ValueError):
        open_web_query("site:example.com OR site:another.example")


async def test_provider_sources_complement_citations_with_domain_diversity_and_real_extraction():
    response = SimpleNamespace(
        status="completed",
        usage=None,
        model_dump=lambda: {
            "output": [
                {
                    "type": "web_search_call",
                    "status": "completed",
                    "action": {
                        "sources": [
                            {
                                "url": "https://blog.example/essay",
                                "title": "Singapore culture essay",
                            },
                            {"url": "https://paper.example/story2"},
                            {"url": "https://paper.example/story3"},
                            {"url": "https://artist.example/notes"},
                            {"url": "https://blog.example/"},
                            {"url": "https://blog.example/category/culture"},
                            {"url": "https://blog.example/image.jpg"},
                            {"url": "http://127.0.0.1/private"},
                        ]
                    },
                },
                {
                    "type": "message",
                    "content": [
                        {
                            "text": "Invented prose",
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "url": "https://paper.example/story1",
                                    "title": "Story",
                                },
                            ],
                        }
                    ],
                },
            ]
        },
    )
    create = AsyncMock(return_value=response)
    model = SimpleNamespace(
        editor_model="test", client=SimpleNamespace(responses=SimpleNamespace(create=create))
    )
    results = await OpenAIWebSearch(model).search(
        "Singapore culture site:paper.example",
        RunBudget({"web_model": 1}, 50000),
        limit=8,
        context={"strategy": "independent", "profile": {"notes": "Singapore"}},
    )
    assert [a.url for a in results] == [
        "https://paper.example/story1",
        "https://blog.example/essay",
        "https://paper.example/story2",
        "https://artist.example/notes",
    ]
    assert all(a.text == a.excerpt == "" for a in results)
    assert results[1].discovery["reference_kind"] == "search_source"
    args = create.call_args.kwargs
    assert "site:paper.example" not in args["input"]
    assert "independent" in args["input"] and "Singapore" in args["input"]
    assert "filters" not in args["tools"][0]


async def test_feed_autodiscovery_validates_actual_feed():
    class Fetcher:
        async def get(self, url):
            if url.endswith("/feed"):
                return Download(url, FEED, "application/rss+xml")
            return Download(url, b'<link type="application/rss+xml" href="/feed">', "text/html")

    assert await validate_feed(Fetcher(), "https://example.com/") == "https://example.com/feed"


async def test_feed_proposal_rejects_non_feed():
    fetcher = SimpleNamespace(
        get=AsyncMock(
            return_value=Download(
                "https://example.com/", b"<html>Ordinary page</html>", "text/html"
            )
        )
    )
    with pytest.raises(RetrievalError, match="Aucun flux"):
        await validate_feed(fetcher, "https://example.com/")


async def test_rss_directory_is_available_for_proposal_but_not_imported():
    store = MemoryStore()
    directory = article(title="RSS feeds", source="example.com")
    runner = pipeline(store, ScriptedModel(), FakeSearch([directory]))
    result = await runner._act(decision("search_web", query="RSS économie"), request(), set())
    assert result["added_ids"] == []
    assert directory.id in runner.discovered
    assert store.articles() == []


async def test_discovery_limit_and_provenance_are_enforced():
    store = MemoryStore()
    runner = pipeline(
        store, ScriptedModel(), FakeSearch([article(1), article(2)]), max_discovered_articles=1
    )
    result = await runner._act(decision("search_web", query="Python"), request(), set())
    assert len(store.articles()) == 1
    assert store.articles()[0].discovery["provider"] == "openai_web_search"
    assert len(result["import_errors"]) == 1


async def test_failed_download_does_not_store_generated_search_content():
    store = MemoryStore()
    collector = FakeCollector(store)
    collector.extract = AsyncMock(side_effect=RetrievalError("Blocked"))
    runner = pipeline(store, ScriptedModel(), FakeSearch([article()]), collector)
    result = await runner._act(decision("search_web", query="Python"), request(), set())
    assert store.articles() == []
    assert result["import_errors"]


async def test_agent_can_only_propose_observed_sources_and_respects_budget():
    store = MemoryStore()
    store.propose_source = lambda url, name, reason, origin, kind="rss": {
        "id": "proposal",
        "url": url,
        "status": "proposed",
    }
    collector = FakeCollector(store)
    collector.fetcher = SimpleNamespace(
        get=AsyncMock(
            return_value=Download("https://example.com/feed", FEED, "application/rss+xml")
        )
    )
    runner = pipeline(store, ScriptedModel(), collector=collector, max_source_proposals=2)
    runner.discovered = {"test": article(source="example.com")}
    with pytest.raises(ValueError, match="découvert"):
        await runner._act(
            decision("propose_source", source_url="https://unknown.example/"), request(), set()
        )
    result = await runner._act(
        decision("propose_source", source_url="https://example.com/"), request(), set()
    )
    assert result["status"] == "proposed"
    with pytest.raises(BudgetExceeded):
        await runner._act(
            decision("propose_source", source_url="https://example.com/"), request(), set()
        )
