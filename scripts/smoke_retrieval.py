"""Read-only network smoke check; no database or LLM calls."""

import asyncio
import json

import trafilatura

from broadwai.network import PublicFetcher, RetrievalError
from broadwai.retrieval import parse_feed


async def main():
    fetcher = PublicFetcher(timeout=20)
    feed = await fetcher.get("https://hnrss.org/newest")
    articles = parse_feed(feed.body, feed.url, 3)
    print(json.dumps({"rss_articles": len(articles)}))
    if not articles:
        raise SystemExit("Aucun article récupéré")
    for article in articles:
        try:
            document = await fetcher.get(article.url)
            text = trafilatura.extract(document.body, include_comments=False)
            if text and len(text) >= 100:
                print(
                    json.dumps(
                        {"extraction": "ok", "characters": len(text), "source": article.source}
                    )
                )
                return
        except RetrievalError:
            continue
    raise SystemExit("RSS valide mais aucune extraction exploitable parmi les 3 candidats")


if __name__ == "__main__":
    asyncio.run(main())
