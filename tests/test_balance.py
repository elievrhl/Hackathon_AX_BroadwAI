from collections import Counter
from unittest.mock import AsyncMock

from broadwai.balance import interest_balance
from broadwai.editorial import preview_pool
from broadwai.models import EditorialIntent, EditorialPick, Interest, Selection
from broadwai.ranking import Ranked
from tests.fakes import MemoryStore, ScriptedModel, article
from tests.test_pipeline import pipeline, request


def mixed_request():
    req = request(size=18, notes="J'aime la littérature russe")
    req.profile.interests = [Interest(topic="Littérature"), Interest(topic="Tech et IA")]
    req.profile.reading_memory = {
        "liked_articles_count": 20,
        "topics": [{"topic": "Dostoïevski", "likes": 20}],
    }
    return req


async def test_literary_likes_cannot_erase_explicit_tech_interest():
    model = ScriptedModel([])
    model.interpret = AsyncMock(
        return_value=EditorialIntent.model_validate(
            {
                "needs": [
                    {
                        "topic": "Littérature russe",
                        "query": "littérature russe",
                        "priority": "primary",
                        "level": "expert",
                        "evidence": "littérature russe",
                    }
                ],
                "constraints": [],
            }
        )
    )
    runner = pipeline(MemoryStore(), model)
    await runner._interpret(mixed_request())
    assert {n["topic"] for n in runner.intent["needs"]} >= {"Littérature", "Tech et IA"}
    assert runner.balance["max_per_interest"] == 9
    assert runner.balance["minimum_per_interest"] == 2


def test_balanced_allocation_preserves_tech_even_after_many_literary_candidates():
    runner = pipeline(MemoryStore(), ScriptedModel([]))
    req = mixed_request()
    runner.balance = interest_balance(req.profile, req.size)
    selections = []
    for index in range(24):
        row = article(
            index, title=f"unique{index} subject{index} detail{index}", source=f"source{index}.test"
        )
        runner.articles[row.id] = row
        runner.picks[row.id] = EditorialPick(
            article_id=row.id,
            interest_id="interest-1" if index < 15 else "interest-2",
            section="Lettres" if index % 2 else "Analyses",
            score=85,
            reason="Pertinent",
            matches_profile=True,
            evergreen=True,
        )
        selections.append(Selection(article_id=row.id, section="Analyses", reason="Pertinent"))
    kept, removed = runner._allocate(selections, req)
    counts = Counter(runner._interest(s.article_id) for s in kept)
    assert counts == {"interest-1": 9, "interest-2": 9}
    assert runner._interest(kept[0].article_id) != runner._interest(kept[1].article_id)
    assert any("Quota de rubrique" in row["reason"] for row in removed)
    only_literature, _ = runner._allocate(selections[:15], req)
    assert len(only_literature) == 9
    runner.candidates = {s.article_id: object() for s in selections}
    errors = runner._validate(only_literature, req)
    assert any("Diversité" in error and "Tech et IA" in error for error in errors)


def test_preview_reserves_tech_even_when_literature_has_higher_scores():
    ranked = []
    for index in range(30):
        topic = "Littérature" if index < 28 else "Tech et IA"
        row = article(
            index, title=f"unique{index} subject{index} detail{index}", source=f"source{index}.test"
        )
        ranked.append(Ranked(row, 100 if index < 28 else 1, [topic], {"interests": {topic: 1}}))
    pool = preview_pool(ranked, 12, ["Littérature", "Tech et IA"])
    assert any("Tech et IA" in row.matched_interests for row in pool)
    assert len(pool) <= 12


def test_three_interests_limit_one_topic_to_a_third():
    req = mixed_request()
    req.profile.interests.append(Interest(topic="Économie"))
    assert interest_balance(req.profile, 18)["max_per_interest"] == 6
