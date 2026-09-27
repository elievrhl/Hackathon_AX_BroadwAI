import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from broadwai.llm import BudgetExceeded, ModelError, OpenAILanguageModel, RunBudget
from broadwai.models import ArticleLink, Brief, CitedSource, PreparedBrief, ReadingDossier
from tests.fakes import article


def prepared(brief):
    return PreparedBrief(
        **brief.model_dump(exclude={"headline", "validity", "dossier"}),
        dossier=ReadingDossier(
            contribution="Comprendre une méthode",
            angle="Mécanisme et exemple",
            prerequisites="Notions de programmation",
            integrity="clear",
            support="method",
            central_risk=False,
            temporal_kind="evergreen",
            temporal_dependency=None,
            obsolete_explicit=False,
        ),
    )


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
            output_parsed=prepared(brief),
            usage=SimpleNamespace(input_tokens=120, output_tokens=80),
        )
    )
    model.client.responses.parse = parse
    budget = RunBudget(limits={"summary": 1}, max_tokens=50000)
    try:
        result = await model.summarize(article(), budget)
        assert result.summary == brief.summary
        assert result.headline == article().title
        assert result.dossier == prepared(brief).dossier
        assert result.validity is None
        kwargs = parse.call_args.kwargs
        assert kwargs["model"] == "summary-test"
        assert kwargs["text_format"] is PreparedBrief
        assert "today" not in json.loads(kwargs["input"])
        assert "headline" not in kwargs["text_format"].model_fields
        assert "validity" not in kwargs["text_format"].model_fields
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
    evidence = "Selon le rapport du Laboratoire, Python améliore les systèmes distribués."
    item = article().model_copy(
        update={
            "text": evidence + " Voir https://science.example/report pour les résultats.",
            "content_links": [
                ArticleLink(label="Laboratoire", url="https://lab.example/study"),
                ArticleLink(label="Texte hors de la portion fournie", url="https://later.example/"),
            ],
        }
    )
    citations = [
        CitedSource(
            name="Laboratoire",
            url="https://lab.example/study",
            evidence=evidence,
            relevance="Étude originale sur les systèmes distribués.",
        ),
        CitedSource(
            name="Même rapport",
            url="https://lab.example/study",
            evidence=evidence,
            relevance="Doublon de l'étude.",
        ),
        CitedSource(
            name="Source inventée",
            url="https://invented.example/",
            evidence="Citation inventée.",
            relevance="Attribution inventée.",
        ),
        CitedSource(
            name="Laboratoire sans lien",
            url="https://invented.example/",
            evidence=evidence,
            relevance="Apport documenté, mais URL non observée.",
        ),
        CitedSource(
            name="URL dans le texte",
            url="https://science.example/report",
            evidence="Voir https://science.example/report pour les résultats.",
            relevance="Résultats complémentaires de l'étude.",
        ),
        CitedSource(
            name="Racine déduite",
            url="https://science.example",
            evidence="Voir https://science.example/report pour les résultats.",
            relevance="Domaine non fourni tel quel.",
        ),
        CitedSource(
            name="Lien hors contexte",
            url="https://later.example/",
            evidence=evidence,
            relevance="URL dont l'ancre est absente du texte transmis.",
        ),
        CitedSource(
            name="Lien local",
            url="http://127.0.0.1/",
            evidence=evidence,
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
            "evidence": evidence,
        },
        cited_sources=citations,
    )
    model.client.responses.parse = AsyncMock(
        return_value=SimpleNamespace(status="completed", output_parsed=prepared(brief), usage=None)
    )
    try:
        result = await model.summarize(item, RunBudget(limits={"summary": 1}, max_tokens=50000))
        assert [source.name for source in result.cited_sources] == [
            "Laboratoire",
            "Source inventée",
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
        assert model.summary_version.startswith("brief-v7-dossier:")
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
