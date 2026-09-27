"""Generate real, persisted editions and retain diagnostics, including on timeout.

Explicit invocation makes paid model calls. Runs are sequential and share the normal cache.
"""

import argparse
import asyncio
import hashlib
import json
from collections import Counter
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from broadwai.config import Settings
from broadwai.llm import OpenAILanguageModel
from broadwai.models import CoverRequest
from broadwai.network import PublicFetcher
from broadwai.pipeline import CoverPipeline
from broadwai.retrieval import Collector
from broadwai.store import Store
from broadwai.web_search import OpenAIWebSearch
from scripts.evaluation_snapshot import clone_catalog, scoped_url
from scripts.evaluation_spend import SpendGuard


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def metrics(cover, request):
    events = cover.diagnostics.get("events", [])
    sources = Counter(item.source for item in cover.items)
    violations = []
    if len({item.article_id for item in cover.items}) != len(cover.items):
        violations.append("duplicate_article")
    if max(sources.values(), default=0) > request.max_per_source:
        violations.append("source_quota")
    for item in cover.items:
        if request.profile.languages and item.brief.language not in request.profile.languages:
            violations.append(f"language:{item.article_id}:{item.brief.language}")
        if item.reading_kind == "current":
            age = (
                (cover.created_at - item.published_at).total_seconds() / 86400
                if item.published_at
                else None
            )
            limit = cover.diagnostics.get("settings", {}).get("max_article_age_days", 7)
            if age is None or age > limit or age < -1:
                violations.append(f"news_date:{item.article_id}")
    return {
        "id": cover.id,
        "status": cover.status,
        "count": len(cover.items),
        "target": request.size,
        "sources": dict(sources),
        "sections": dict(Counter(item.section for item in cover.items)),
        "languages": dict(Counter(item.brief.language for item in cover.items)),
        "exploration": sum(item.selection_kind == "exploration" for item in cover.items),
        "excerpt_only": sum(item.extraction_status != "extracted" for item in cover.items),
        "seconds": round(cover.diagnostics.get("duration_ms", 0) / 1000, 1),
        "cost": cover.usage.get("cost"),
        "counts": cover.usage.get("calls"),
        "cache_hits": cover.usage.get("summary_cache_hits"),
        "violations": violations,
        "uncovered_needs": cover.diagnostics.get("uncovered_needs", []),
        "rejections": dict(
            Counter(e.get("reason", "") for e in events if e["kind"] == "candidate_skipped")
        ),
        "searches": cover.diagnostics.get("search_history", []),
        "warnings": cover.warnings,
    }


async def checkpoint(runner, path, label):
    while True:
        await asyncio.sleep(20)
        write_json(path, {"diagnostics": runner.audit, "usage": runner.budget.report()})
        print(
            json.dumps(
                {
                    "progress": label,
                    "seconds": round(perf_counter() - runner.started),
                    "prepared": len(runner.candidates),
                    "last_event": runner.audit["events"][-1]["kind"]
                    if runner.audit["events"]
                    else "intent",
                }
            ),
            flush=True,
        )


async def run(args):
    settings = Settings(_env_file=args.env_file)
    if not settings.llm_ready:
        raise SystemExit("Configuration LLM absente")
    database_url = settings.database_url.get_secret_value()
    if args.schema:
        clone_catalog(database_url, args.snapshot_from, args.schema)
        database_url = scoped_url(database_url, args.schema)
    profiles = json.loads(args.profiles.read_text(encoding="utf-8"))
    if args.only:
        profiles = [p for p in profiles if p["name"] in args.only]
        if {p["name"] for p in profiles} != set(args.only):
            raise SystemExit("Profil inconnu")
    requests = [
        (
            p["name"],
            CoverRequest(
                profile=p["profile"],
                size=args.size,
                max_per_source=3,
                discover_web=True,
                discover_sources=True,
            ),
        )
        for p in profiles
    ]
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(
        args.output / "manifest.json",
        {
            "started_at": datetime.now(UTC).isoformat(),
            "models": {"summary": settings.summary_model, "editor": settings.editor_model},
            "database_schema": args.schema,
            "snapshot_from": args.snapshot_from,
            "timeout_seconds": args.timeout,
            "source_hashes": {
                str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in Path("broadwai").glob("*.py")
            },
            "requests": {label: req.model_dump(mode="json") for label, req in requests},
            "note": (
                "Générations séquentielles persistées ; catalogue et cache partagés, "
                "aucun réessai automatique."
            ),
        },
    )
    store = Store(database_url)
    store.pool.open(wait=True, timeout=10)
    model = OpenAILanguageModel(
        settings.openai_api_key.get_secret_value(),
        settings.summary_model,
        settings.editor_model,
        settings.max_article_chars,
    )
    guard = (
        SpendGuard(args.spend_ledger, args.max_usd, args.spend_ceiling)
        if args.spend_ledger
        else None
    )
    if guard:
        guard.attach(model)
    results = []
    try:
        write_json(args.output / "catalog-before.json", store.stats())
        for label, req in requests:
            print(f"START {label}", flush=True)
            runner = CoverPipeline(
                store,
                Collector(
                    store, PublicFetcher(settings.request_timeout, settings.max_download_bytes)
                ),
                OpenAIWebSearch(model, settings.web_search_enabled),
                model,
                settings,
            )
            monitor = asyncio.create_task(
                checkpoint(runner, args.output / f"{label}-progress.json", label)
            )
            try:
                async with asyncio.timeout(args.timeout):
                    cover = await runner.run(req)
                write_json(args.output / f"{label}.json", cover.model_dump(mode="json"))
                result = {
                    "profile": label,
                    **metrics(cover, req),
                    "persisted": store.get_cover(cover.id) is not None,
                }
            except Exception as exc:
                result = {
                    "profile": label,
                    "error": type(exc).__name__,
                    "seconds": round(perf_counter() - runner.started, 1),
                    "cost": runner.budget.report().get("cost"),
                }
                write_json(
                    args.output / f"{label}-error.json",
                    {**result, "diagnostics": runner.audit, "usage": runner.budget.report()},
                )
            finally:
                monitor.cancel()
                with suppress(asyncio.CancelledError):
                    await monitor
            results.append(result)
            write_json(args.output / "results.json", results)
            print(json.dumps(result, ensure_ascii=True), flush=True)
        write_json(args.output / "catalog-after.json", store.stats())
    finally:
        await model.close()
        store.close()
        if guard:
            guard.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=Path, default=Path("examples/evaluation-profiles.json"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/evaluation") / datetime.now().strftime("%Y%m%d-%H%M%S"),
    )
    parser.add_argument("--only", nargs="+")
    parser.add_argument("--size", type=int, default=18)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--schema", help="New isolated audit_ schema; production stays unchanged")
    parser.add_argument("--snapshot-from", default="public")
    parser.add_argument("--spend-ledger", type=Path)
    parser.add_argument("--max-usd", type=float, default=3.0)
    parser.add_argument("--spend-ceiling", type=float, help="Cumulative ceiling for this pass")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
