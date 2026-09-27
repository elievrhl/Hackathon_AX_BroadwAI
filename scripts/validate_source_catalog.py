"""Check curated public feeds with the production fetcher and export importable sources.

No database writes or LLM calls. Failed checks remain documented in the catalogue.
"""

import argparse
import asyncio
import hashlib
import json
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

import feedparser

from broadwai.models import canonical_url, utcnow
from broadwai.network import PublicFetcher, RetrievalError
from broadwai.retrieval import parse_feed
from broadwai.sources import SourceInput
from broadwai.website import article_links, website_article


def export_sources(catalog: dict, topics: set[str] | None = None) -> list[dict]:
    known_topics = {topic["id"] for topic in catalog["topics"]}
    if topics and topics - known_topics:
        raise ValueError(f"Sujets inconnus : {', '.join(sorted(topics - known_topics))}")
    sources = []
    seen = set()
    for entry in catalog["sources"]:
        if entry.get("editorial_status") == "excluded":
            continue
        if entry.get("verification", {}).get("status") != "ok":
            continue
        if topics and not topics.intersection(entry["topics"]):
            continue
        source = SourceInput.model_validate(entry["source"])
        key = (source.kind, source.url)
        if source.enabled and key not in seen:
            sources.append(source.model_dump())
            seen.add(key)
    return sources


def mark_duplicates(catalog: dict) -> int:
    """Keep the first feed; retain aliases in the audit with their duplicate target."""
    seen = {}
    count = 0
    generic_titles = {"bbc news", "bbc sport", "news", "actualités", "actualites", "rss"}
    for entry in catalog["sources"]:
        verification = entry.get("verification", {})
        if verification.get("status") != "ok" or entry.get("editorial_status") == "excluded":
            continue
        kind = entry["source"]["kind"]
        resolved = canonical_url(verification.get("resolved_url") or entry["source"]["url"])
        keys = [("url", kind, resolved)]
        if kind in {"rss", "podcast"}:
            if fingerprint := verification.get("content_fingerprint"):
                keys.append(("content", kind, fingerprint))
            title = verification.get("feed_title", "").strip().casefold()
            homepage = verification.get("feed_homepage")
            # Generic titles can be reused by genuinely distinct rubrics (e.g. BBC).
            if homepage and title and title not in generic_titles:
                parts = urlsplit(homepage)
                identity = (parts.hostname or "").removeprefix("www.") + parts.path.rstrip("/")
                keys.append(("identity", kind, identity, title))
        original = next((seen[key] for key in keys if key in seen), None)
        if original:
            verification.update(
                status="duplicate",
                duplicate_of=original["id"],
                error=(
                    "Même flux, même identité ou même échantillon de publications que "
                    f"{original['source']['name']}."
                ),
            )
            count += 1
        else:
            for key in keys:
                seen[key] = entry
    return count


async def check_source(entry: dict, fetcher: PublicFetcher) -> dict:
    checked_at = utcnow()
    result = {"checked_at": checked_at.isoformat(), "status": "failed"}
    try:
        source = SourceInput.model_validate(entry["source"])
        download = await fetcher.get(source.url)
        result.update(resolved_url=download.url, content_type=download.content_type)
        if source.kind == "website":
            links = await asyncio.to_thread(article_links, download, 20)
            if prefix := entry.get("article_path_prefix"):
                links = [url for url in links if urlsplit(url).path.startswith(prefix)]
            if not links:
                raise RetrievalError("Page sans lien d'article exploitable")
            sample = None
            for url in links[:3]:
                try:
                    page = await fetcher.get(url)
                    sample = await asyncio.to_thread(website_article, page, download.url)
                    break
                except (RetrievalError, ValueError):
                    continue
            if sample is None:
                raise RetrievalError("Aucun article exploitable parmi les trois premiers liens.")
            result.update(
                status="ok",
                article_count=len(links),
                sample_urls=[sample.url],
                sample_extraction_status=sample.extraction_status,
                scope="Liens détectés et un article extrait ; autres articles non vérifiés.",
            )
        elif source.kind == "hacker_news":
            ids = json.loads(download.body)
            if not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids):
                raise RetrievalError("Liste Hacker News invalide")
            result.update(status="ok", article_count=len(ids), scope="Liste des identifiants.")
        else:
            articles = await asyncio.to_thread(parse_feed, download.body, download.url, 50)
            if source.kind == "podcast":
                articles = [article for article in articles if article.format == "podcast"]
            if not articles:
                raise RetrievalError("Flux sans article ou épisode exploitable")
            feed = await asyncio.to_thread(feedparser.parse, download.body)
            expected_title = entry.get("expected_feed_title")
            if (
                expected_title
                and feed.feed.get("title", "").casefold() != expected_title.casefold()
            ):
                result.update(
                    status="review_required",
                    feed_title=feed.feed.get("title", ""),
                    error="Le titre du flux a changé ; vérifier son identité avant import.",
                )
                return result
            dates = [article.published_at for article in articles if article.published_at]
            past_dates = [date for date in dates if date <= checked_at + timedelta(days=1)]
            latest = max(past_dates) if past_dates else None
            result.update(
                status="ok",
                feed_title=feed.feed.get("title", ""),
                feed_homepage=feed.feed.get("link", ""),
                observed_language=feed.feed.get("language", ""),
                article_count=len(articles),
                articles_with_excerpt=sum(bool(article.excerpt) for article in articles),
                latest_published_at=latest.isoformat() if latest else None,
                sample_urls=[article.url for article in articles[:2]],
                article_url_sample=[article.url for article in articles[:12]],
                content_fingerprint=(
                    hashlib.sha256(
                        "\n".join(sorted(article.url for article in articles[:12])).encode()
                    ).hexdigest()
                    if len(articles) >= 4
                    else None
                ),
                scope="Flux parsé ; disponibilité du texte intégral non garantie.",
            )
            if latest and checked_at - latest > timedelta(days=365):
                result.update(status="stale", error="Aucune publication depuis plus d'un an.")
            elif dates and not past_dates:
                result.update(status="failed", error="Toutes les dates sont futures.")
    except (RetrievalError, ValueError, TypeError) as exc:
        result["error"] = str(exc)
    return result


async def verify(
    catalog: dict, *, failed_only: bool = False, pending_only: bool = False, concurrency: int = 8
):
    semaphore = asyncio.Semaphore(concurrency)
    hosts = defaultdict(lambda: asyncio.Semaphore(1))
    fetcher = PublicFetcher()

    async def one(entry):
        # Technical availability must not silently override an editorial exclusion.
        if entry.get("editorial_status") == "excluded":
            return
        if pending_only and entry.get("verification", {}).get("status") != "pending":
            return
        if failed_only and entry.get("verification", {}).get("status") in {
            "ok",
            "duplicate",
            "review_required",
        }:
            return
        host = urlsplit(entry["source"]["url"]).hostname
        async with hosts[host], semaphore:
            entry["verification"] = await check_source(entry, fetcher)
        print(
            json.dumps(
                {
                    "source": entry["source"]["name"],
                    **entry["verification"],
                },
                ensure_ascii=True,
            ),
            flush=True,
        )

    await asyncio.gather(*(one(entry) for entry in catalog["sources"]))
    catalog["last_checked_at"] = utcnow().isoformat()


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path("examples/source-catalog.json"))
    parser.add_argument("--export", type=Path, default=Path("examples/sources-all-topics.json"))
    parser.add_argument("--export-only", action="store_true", help="Réutiliser les vérifications.")
    parser.add_argument(
        "--failed-only", action="store_true", help="Revérifier les échecs seulement."
    )
    parser.add_argument(
        "--pending-only", action="store_true", help="Vérifier les nouveaux candidats seulement."
    )
    parser.add_argument(
        "--topic", action="append", help="Filtrer l'export par identifiant de sujet."
    )
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    # Validate requested topic IDs before making requests or changing the catalogue.
    export_sources(catalog, set(args.topic or []))
    if not args.export_only:
        asyncio.run(verify(catalog, failed_only=args.failed_only, pending_only=args.pending_only))
        mark_duplicates(catalog)
        write_json(args.catalog, catalog)
    sources = export_sources(catalog, set(args.topic or []))
    write_json(args.export, sources)
    coverage = Counter(
        topic
        for entry in catalog["sources"]
        if entry.get("verification", {}).get("status") == "ok" and entry["source"]["enabled"]
        for topic in entry["topics"]
    )
    print(json.dumps({"exported": len(sources), "coverage": dict(coverage)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
