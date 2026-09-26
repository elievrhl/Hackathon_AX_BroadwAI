import pytest
from fastapi.testclient import TestClient

from broadwai.api import create_app
from broadwai.config import Settings
from broadwai.models import Cover
from tests.fakes import MemoryStore, ScriptedModel, article, finalize_first
from tests.test_pipeline import pipeline, request


async def test_journal_records_scores_summary_cache_and_exact_decisions():
    item = article()
    store = MemoryStore([item])
    model = ScriptedModel([finalize_first, finalize_first])
    first = await pipeline(store, model).run(request())
    second = await pipeline(store, model).run(request())
    events = first.diagnostics["events"]
    kinds = [e["kind"] for e in events]
    assert kinds.index("shortlist") < kinds.index("summary_requested")
    assert kinds.index("summary_completed") < kinds.index("editor_requested")
    assert kinds[-1] == "cover_completed"
    shortlist = next(e for e in events if e["kind"] == "shortlist")
    assert shortlist["shortlisted_ids"] == [item.id]
    score = shortlist["ranked"][0]
    parts = score["score_details"]
    assert score["score"] == pytest.approx(
        sum(parts["interests"].values())
        + parts["query_bonus"]
        + parts["freshness"]
        + sum(parts["needs"].values())
        + 2 * parts["notes"]
    )
    assert first.diagnostics["candidates"][0]["brief"] == first.items[0].brief.model_dump()
    assert "summary_cache_hit" in [e["kind"] for e in second.diagnostics["events"]]
    assert "summary_requested" not in [e["kind"] for e in second.diagnostics["events"]]
    assert "openai_api_key" not in first.diagnostics["settings"]
    assert first.diagnostics["request"]["profile"]["user_id"] == "alice"


async def test_history_and_legacy_cover_remain_readable_without_reconstruction():
    store = MemoryStore([article()])
    cover = await pipeline(store, ScriptedModel([finalize_first])).run(request())
    old = cover.model_dump()
    old.pop("diagnostics")
    old["id"] = "legacy"
    store.put_cover(Cover.model_validate(old))
    with TestClient(create_app(Settings(_env_file=None), store=store)) as client:
        assert client.get("/admin/covers").status_code == 200
        assert client.get("/v1/covers?limit=1").json()[0]["item_count"] == 1
        assert client.get("/v1/covers/legacy").json()["diagnostics"] == {}
        assert client.get("/v1/covers?limit=101").status_code == 422
