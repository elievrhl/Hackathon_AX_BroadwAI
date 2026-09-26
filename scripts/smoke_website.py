"""Read a real website without database writes or model calls."""

import argparse
import asyncio
import json
from pathlib import Path

from broadwai.models import Article, IngestRequest
from broadwai.network import PublicFetcher
from broadwai.retrieval import Collector


class SampleStore:
    def __init__(self):
        self.articles = {}

    def put_article(self, article):
        self.articles[article.id] = article
        return article


async def main(url, limit, save_pages=None):
    class SampleFetcher(PublicFetcher):
        async def get(self, target):
            download = await super().get(target)
            if save_pages:
                save_pages.mkdir(parents=True, exist_ok=True)
                file = save_pages / (Article.create(download.url, "Sample").id + ".html")
                file.write_bytes(download.body)
                print(json.dumps({"url": download.url, "saved": str(file)}))
            return download

    store = SampleStore()
    report = await Collector(store, SampleFetcher()).ingest(
        IngestRequest(website_urls=[url], limit_per_source=limit)
    )
    print(
        json.dumps(
            {
                **report,
                "articles": [
                    {
                        "title": a.title,
                        "url": a.url,
                        "status": a.extraction_status,
                        "text_chars": len(a.text),
                    }
                    for a in store.articles.values()
                ],
            },
            ensure_ascii=True,
            indent=2,
        )
    )
    return 0 if report["collected"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--limit", type=int, choices=range(1, 51), default=2)
    parser.add_argument("--save-pages", type=Path, help="Save downloaded HTML for local inspection")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.url, args.limit, args.save_pages)))
