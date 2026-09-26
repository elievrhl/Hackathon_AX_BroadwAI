from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from broadwai.llm import BudgetExceeded, ModelError, OpenAILanguageModel, RunBudget
from broadwai.models import Brief
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
            "evidence": "Python systèmes distribués",
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
        assert kwargs["max_output_tokens"] == 1400
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
