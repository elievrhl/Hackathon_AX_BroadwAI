import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from broadwai.llm import BudgetExceeded, ModelError, OpenAILanguageModel, RunBudget
from broadwai.models import ArticleLink, Brief, CitedSource
from tests.fakes import article


def test_budget_rejects_before_spending_and_counts_each_kind():
    budget = RunBudget(limits={"summary": 1, "editor": 2}, max_tokens=100)
    budget.take("summary", 60)
    with pytest.raises(BudgetExceeded):
        budget.take("summary", 1)
    with pytest.raises(BudgetExceeded):
        budget.take("editor", 41)
    assert budget.counts["editor"] == 0
    assert budget.reserved_tokens == 60


async def test_openai_adapter_structured_output_limits_and_usage():
    model = OpenAILanguageModel("test-key", "summary-test", "editor-test", 1000)
    brief = Brief(
        summary="Résumé factuel",
        headline="Un titre français",
        validity={
            "kind": "evergreen",
            "status": "durable",
            "reason": "Méthode durable",
        },
        key_points=["Un point"],
        topics=["Python"],
        content_type="analysis",
        level="expert",
        language="fr",
        caveats=[],
    )
    parse = AsyncMock(
        return_value=SimpleNamespace(
            status="completed",
            output_parsed=brief,
            usage=SimpleNamespace(input_tokens=120, output_tokens=80),
        )
    )
    model.client.responses.parse = parse
    budget = RunBudget(limits={"summary": 1}, max_tokens=50000)
    try:
        assert await model.summarize(article(), budget) == brief
        kwargs = parse.call_args.kwargs
        assert kwargs["model"] == "summary-test"
        assert kwargs["text_format"] is Brief
        assert kwargs["store"] is False
        assert kwargs["max_output_tokens"] == 2400
        assert budget.input_tokens == 120
        assert budget.output_tokens == 80
        call = budget.report()["model_calls"][0]
        assert call["model"] == "summary-test" and call["status"] == "completed"
        assert call["usage"]["input_tokens"] == 120
        assert call["duration_ms"] >= 0
    finally:
        await model.close()


async def test_refused_or_incomplete_model_output_is_explicit_error():
    model = OpenAILanguageModel("test-key", "summary-test", "editor-test", 1000)
    model.client.responses.parse = AsyncMock(
        return_value=SimpleNamespace(
            status="incomplete",
            output_parsed=None,
            usage=None,
        )
    )
    try:
        with pytest.raises(ModelError):
            await model.summarize(article(), RunBudget(limits={"summary": 1}, max_tokens=50000))
    finally:
        await model.close()


async def test_summary_sources_without_quotes_are_deduplicated_and_urls_observed():
    model = OpenAILanguageModel("test-key", "summary-test", "editor-test", 1000)
    source_text = "Selon le rapport du Laboratoire, Python améliore les systèmes distribués."
    item = article().model_copy(
        update={
            "text": source_text + " Voir https://science.example/report pour les résultats.",
            "content_links": [
                ArticleLink(label="Laboratoire", url="https://lab.example/study"),
                ArticleLink(label="Texte hors de la portion fournie", url="https://later.example/"),
            ],
        }
    )
    sources = [
        CitedSource(
            name="Laboratoire",
            url="https://lab.example/study",
            relevance="Étude originale sur les systèmes distribués.",
        ),
        CitedSource(
            name="Même rapport",
            url="https://lab.example/study",
            relevance="Doublon de l'étude.",
        ),
        CitedSource(
            name="Source sans URL observée",
            url="https://invented.example/",
            relevance="Nom de source sans lien fourni.",
        ),
        CitedSource(
            name="Laboratoire sans lien",
            url="https://invented.example/",
            relevance="Apport documenté, mais URL non observée.",
        ),
        CitedSource(
            name="URL dans le texte",
            url="https://science.example/report",
            relevance="Résultats complémentaires de l'étude.",
        ),
        CitedSource(
            name="Racine déduite",
            url="https://science.example",
            relevance="Domaine non fourni tel quel.",
        ),
        CitedSource(
            name="Lien hors contexte",
            url="https://later.example/",
            relevance="URL dont l'ancre est absente du texte transmis.",
        ),
        CitedSource(
            name="Lien local",
            url="http://127.0.0.1/",
            relevance="Ne doit pas conserver ce lien.",
        ),
    ]
    brief = Brief(
        summary="Résumé",
        headline="Un titre",
        key_points=["Un point"],
        topics=[],
        content_type="research",
        level="expert",
        language="fr",
        caveats=[],
        validity={
            "kind": "research",
            "status": "time_sensitive",
            "reason": "Une étude",
        },
        cited_sources=sources,
    )
    model.client.responses.parse = AsyncMock(
        return_value=SimpleNamespace(status="completed", output_parsed=brief, usage=None)
    )
    try:
        result = await model.summarize(item, RunBudget(limits={"summary": 1}, max_tokens=50000))
        assert [source.name for source in result.cited_sources] == [
            "Laboratoire",
            "Source sans URL observée",
            "Laboratoire sans lien",
            "URL dans le texte",
            "Racine déduite",
            "Lien hors contexte",
            "Lien local",
        ]
        assert [source.url for source in result.cited_sources] == [
            "https://lab.example/study",
            None,
            None,
            "https://science.example/report",
            None,
            "https://later.example/",
            None,
        ]
        data = json.loads(model.client.responses.parse.call_args.kwargs["input"])
        assert data["article_url"] == item.url
        assert data["content_links"] == [link.model_dump() for link in item.content_links]
        assert model.summary_version.startswith("brief-v6:")
        # Source lists were absent in older briefs.
        old = brief.model_dump(exclude={"cited_sources"})
        assert Brief.model_validate(old).cited_sources == []
    finally:
        await model.close()


def test_saved_briefs_ignore_legacy_quotes_and_keep_their_content():
    brief = Brief(
        summary="Résumé conservé",
        key_points=["Un point"],
        topics=[],
        content_type="analysis",
        level="intermediate",
        language="fr",
        caveats=[],
        validity={
            "kind": "evergreen",
            "status": "durable",
            "reason": "Méthode durable",
            "evidence": "Ancienne citation absente du texte actuel",
        },
        cited_sources=[
            {
                "name": "Laboratoire",
                "url": "https://lab.example/study",
                "relevance": "Étude utile",
                "evidence": "Ancienne attribution",
            }
        ],
    )
    assert "evidence" not in json.dumps(brief.model_dump())
    assert brief.summary == "Résumé conservé"
    assert brief.cited_sources[0].url == "https://lab.example/study"


def test_editorial_output_schemas_no_longer_request_quotes():
    from broadwai.models import Decision, EditorialIntent, EditorialPlan, PreferenceAssessments

    for schema in (Brief, Decision, EditorialIntent, EditorialPlan, PreferenceAssessments):
        assert '"evidence"' not in json.dumps(schema.model_json_schema())
