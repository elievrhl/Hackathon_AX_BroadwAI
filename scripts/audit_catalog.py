"""Inspect the real catalogue; optionally extract a bounded sample without using an LLM."""

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

from broadwai.config import Settings
from broadwai.network import PublicFetcher, RetrievalError
from broadwai.retrieval import Collector
from broadwai.store import Store


async def main(sample_size: int):
    settings = Settings()
    store = Store(settings.database_url.get_secret_value())
    try:
        store.open()
        sources = store.list_sources()
        articles = store.articles(settings.max_catalog_articles)
        collector = Collector(store, PublicFetcher())
        # Spread the sample across publishers instead of repeatedly testing one feed.
        picked = {}
        for article in articles:
            if article.source not in picked and len(picked) < sample_size:
                picked[article.source] = article
        results = []
        for article in picked.values():
            try:
                extracted = await collector.extract(article)
                result = {
                    "article_id": article.id,
                    "source": article.source,
                    "status": "extracted",
                    "characters": len(extracted.text),
                }
            except RetrievalError as exc:
                result = {
                    "article_id": article.id,
                    "source": article.source,
                    "status": "failed",
                    "error": str(exc),
                }
            results.append(result)
            print(json.dumps(result), flush=True)
        articles = store.articles(settings.max_catalog_articles)
        report = {
            "sources": len(sources),
            "active_sources": sum(s["enabled"] for s in sources),
            "catalog": store.stats(),
            "publisher_domains": len({a.source for a in articles}),
            "articles_with_publication_date": sum(a.published_at is not None for a in articles),
            "articles_with_excerpt": sum(bool(a.excerpt) for a in articles),
            "extraction_status": dict(Counter(a.extraction_status for a in articles)),
            "latest_collection_errors": [
                s["name"] for s in sources if s["last_report"] and s["last_report"]["errors"]
            ],
            "sample_extractions": results,
        }
        Path("data").mkdir(exist_ok=True)
        Path("data/catalog-audit.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(report), flush=True)
    finally:
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract-sample", type=int, choices=range(0, 21), default=0)
    asyncio.run(main(parser.parse_args().extract_sample))
