import asyncio
import calendar
import html
import json
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin

import feedparser

from broadwai.extraction import extract_content
from broadwai.images import article_image
from broadwai.models import Article, IngestRequest, utcnow
from broadwai.network import PublicFetcher, RetrievalError, validate_destination
from broadwai.podcasts import episode_metadata, public_url
from broadwai.videos import known_duration
from broadwai.website import article_links, website_article
from broadwai.youtube import channel_feed, metadata_duration, thumbnail, video_id


def plain(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", text)).strip()


def parse_feed(body: bytes, base_url: str, limit: int) -> list[Article]:
    feed = feedparser.parse(body)
    articles = []
    if feed.bozo and not feed.entries:
        raise RetrievalError("Flux RSS/Atom illisible")
    links = Counter(public_url(entry.get("link"), base_url) for entry in feed.entries)
    repeated_links = {link for link, count in links.items() if count > 1}
    for entry in feed.entries[: max(limit * 5, 50)]:
        if len(articles) >= limit:
            break
        try:
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            podcast = episode_metadata(entry, feed.feed, base_url, repeated_links)
            url = podcast["url"] if podcast else validate_destination(urljoin(base_url, entry.link))
            youtube_id = video_id(url)
            if youtube_id:
                url = f"https://www.youtube.com/watch?v={youtube_id}"
            article = Article.create(
                url=url,
                title=plain(entry.get("title", "Sans titre"))[:1000],
                excerpt=plain(entry.get("summary", ""))[:12000],
                published_at=datetime.fromtimestamp(calendar.timegm(published), UTC)
                if published
                else None,
                language=feed.feed.get("language", "").split("-")[0] or None,
            )
            if podcast:
                if podcast["media"]["episode_type"] == "trailer" or (
                    article.published_at and article.published_at > utcnow()
                ):
                    continue
                article.format = "podcast"
                article.media = podcast["media"]
                article.source = podcast["source"]
                article.image = podcast["image"]
                article.image_checked_at = utcnow()
                article.discovery = {"kind": "podcast_episode", "feed_url": base_url}
            elif youtube_id:
                article.format = "video"
                article.media = {
                    "provider": "youtube",
                    "video_id": youtube_id,
                    "channel_id": entry.get("yt_channelid"),
                    "channel_title": plain(entry.get("author", feed.feed.get("title", "YouTube"))),
                }
                article.image = thumbnail(article)
                article.image_checked_at = utcnow()
            articles.append(article)
        except (AttributeError, ValueError, RetrievalError, OverflowError):
            continue
    return articles


class Collector:
    def __init__(self, store, fetcher: PublicFetcher):
        self.store = store
        self.fetcher = fetcher
        self.video_slots = asyncio.Semaphore(4)

    async def _store_feed_article(self, article: Article) -> Article:
        youtube_id = video_id(article.url) if article.format == "video" else None
        if youtube_id:
            previous = self.store.get_article(article.id)
            if previous and previous.format == "video":
                # Preserve explicitly imported transcripts and previously verified durations.
                if previous.extraction_status == "extracted":
                    article = previous
                duration = known_duration(previous)
                if duration is not None:
                    article = article.model_copy(
                        update={"media": {**(article.media or {}), "duration_seconds": duration}}
                    )
            if known_duration(article) is None:
                try:
                    async with self.video_slots, asyncio.timeout(3):
                        page = await self.fetcher.get(
                            f"https://www.youtube.com/watch?v={youtube_id}"
                        )
                        if video_id(page.url) == youtube_id and page.content_type in {
                            "text/html",
                            "application/xhtml+xml",
                        }:
                            duration = await asyncio.to_thread(
                                metadata_duration, page.body, youtube_id
                            )
                            if duration is not None:
                                article = article.model_copy(
                                    update={
                                        "media": {
                                            **(article.media or {}),
                                            "duration_seconds": duration,
                                        }
                                    }
                                )
                except (RetrievalError, TimeoutError, ValueError):
                    # Unavailable duration means ineligible, not a failed RSS collection.
                    pass
        return self.store.put_article(article)

    async def ingest(self, request: IngestRequest) -> dict:
        ids: set[str] = set()
        errors = []
        for url in request.feed_urls:
            try:
                download = await self.fetcher.get(url)
                articles = await asyncio.to_thread(
                    parse_feed,
                    download.body,
                    download.url,
                    request.limit_per_source,
                )
                saved = await asyncio.gather(*(self._store_feed_article(a) for a in articles))
                ids.update(article.id for article in saved)
            except RetrievalError as exc:
                errors.append({"source": url, "error": str(exc)})
        for url in request.website_urls:
            await self.collect_website(url, request.limit_per_source, ids, errors)
        if request.hacker_news:
            try:
                download = await self.fetcher.get(
                    "https://hacker-news.firebaseio.com/v0/topstories.json",
                )
                story_ids = json.loads(download.body)[: request.limit_per_source]
                semaphore = asyncio.Semaphore(5)

                async def story(story_id):
                    async with semaphore:
                        try:
                            item = await self.fetcher.get(
                                f"https://hacker-news.firebaseio.com/v0/item/{int(story_id)}.json",
                            )
                            data = json.loads(item.body)
                            if not data or data.get("deleted") or data.get("dead"):
                                return
                            if data.get("type") != "story" or not data.get("url"):
                                return
                            article = Article.create(
                                url=validate_destination(data["url"]),
                                title=plain(data["title"])[:1000],
                                excerpt=plain(data.get("text", ""))[:12000],
                                # HN submission time is NOT the original publication time.
                            )
                            self.store.put_article(article)
                            ids.add(article.id)
                        except (RetrievalError, ValueError, KeyError, TypeError) as exc:
                            errors.append({"source": f"hn:{story_id}", "error": type(exc).__name__})

                await asyncio.gather(*(story(story_id) for story_id in story_ids))
            except (RetrievalError, ValueError, TypeError) as exc:
                errors.append({"source": "hacker_news", "error": type(exc).__name__})
        return {"article_ids": sorted(ids), "collected": len(ids), "errors": errors}

    async def collect_website(self, url, limit, ids, errors):
        found = set()
        try:
            # Keep partial results and leave time for the admin to persist the report.
            async with asyncio.timeout(100):
                page = await self.fetcher.get(validate_destination(url))
                links = await asyncio.to_thread(article_links, page, min(limit * 2, 50))
                if not links:
                    raise RetrievalError(
                        "Aucun lien d'article trouvé ; essayez la page d'une rubrique ou du blog. "
                        "Les pages nécessitant JavaScript ne sont pas prises en charge."
                    )

                async def read(link):
                    try:
                        download = await self.fetcher.get(link)
                        article = await asyncio.to_thread(website_article, download, page.url)
                        return article
                    except (RetrievalError, ValueError) as exc:
                        errors.append({"source": url, "url": link, "error": str(exc)})
                        return None

                # At most five simultaneous downloads; failures leave room for other links.
                for start in range(0, len(links), 5):
                    batch = await asyncio.gather(*(read(link) for link in links[start : start + 5]))
                    for article in batch:
                        if article and len(found) < limit:
                            self.store.put_article(article)
                            found.add(article.id)
                            ids.add(article.id)
                    if len(found) >= limit:
                        break
                if not found:
                    raise RetrievalError("Aucun article exploitable trouvé sur cette page")
        except TimeoutError:
            errors.append({"source": url, "error": "Délai de collecte du site dépassé"})
        except (RetrievalError, ValueError) as exc:
            errors.append({"source": url, "error": str(exc)})

    async def extract(self, article: Article) -> Article:
        if article.format == "podcast":
            # An episode webpage/MP3 is not a transcript. Keep the feed description
            # as an excerpt, preserving any transcript explicitly supplied elsewhere.
            return article
        if video_id(article.url):
            # The HTML of a watch page is not the spoken content. Feed descriptions
            # stay excerpts; only an explicitly supplied transcript may be extracted.
            article = article.model_copy(update={"format": "video"})
            return self.store.put_article(article)
        if article.extraction_status == "extracted":
            return article
        download = await self.fetcher.get(article.url)
        if article.discovery.get("provider") == "openai_web_search":
            # Search citations can point to old stories or section pages. Validate
            # article signals and read the publisher's date before editorial use.
            extracted = await asyncio.to_thread(website_article, download, article.url)
            # model_copy does not validate updates: retain nested ArticleLink objects.
            # model_dump here would turn them into dicts and break content_hash/summary.
            updated = article.model_copy(
                update={
                    name: getattr(extracted, name)
                    for name in type(extracted).model_fields
                    if name
                    not in {
                        "id",
                        "url",
                        "source",
                        "collected_at",
                        "discovery",
                    }
                }
            )
            return self.store.put_article(updated)
        if download.content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
            raise RetrievalError("Format d'article non pris en charge")
        if download.content_type == "text/plain":
            text = download.body.decode("utf-8", errors="replace")
            content_links = []
        else:
            text, content_links = await asyncio.to_thread(
                extract_content, download.body, download.url
            )
        if not text or len(text.strip()) < 100:
            raise RetrievalError("Texte insuffisant : extraction indisponible")
        # Some publishers return an HTTP 200 interstitial instead of article text.
        blocked_messages = (
            "javascript is disabled in your browser",
            "please enable javascript to proceed",
            "verify you are human",
            "checking your browser before accessing",
        )
        if len(text) < 1500 and any(message in text.lower() for message in blocked_messages):
            raise RetrievalError("Page de blocage : texte de l'article indisponible")
        # Preserve catalogue identity across redirects; don't trust HTML canonical links.
        updated = article.model_copy(
            update={
                "text": text,
                "content_links": content_links,
                "extraction_status": "extracted",
                "image": (article_image(download.body, download.url) or article.image)
                if download.content_type != "text/plain"
                else None,
                "image_checked_at": utcnow(),
            }
        )
        return self.store.put_article(updated)


async def refresh_media_sources(store, collector, *, videos=True, podcasts=False) -> list[dict]:
    """Refresh enabled channels/shows hourly, with bounded per-source failures."""
    sources = await asyncio.to_thread(store.list_sources)
    due = [
        s
        for s in sources
        if s["enabled"]
        and (
            (videos and s["kind"] == "rss" and channel_feed(s["url"]))
            or (podcasts and s["kind"] == "podcast")
        )
        and (
            not s.get("last_collected_at") or s["last_collected_at"] < utcnow() - timedelta(hours=1)
        )
    ]
    semaphore = asyncio.Semaphore(4)

    async def refresh(source):
        async with semaphore:
            try:
                async with asyncio.timeout(18):
                    report = await collector.ingest(
                        IngestRequest(
                            feed_urls=[source["url"]],
                            limit_per_source=min(15, source["limit_per_source"]),
                        )
                    )
            except (RetrievalError, TimeoutError):
                report = {
                    "article_ids": [],
                    "collected": 0,
                    "errors": [{"error": "Flux multimédia temporairement indisponible"}],
                }
            await asyncio.to_thread(store.record_collection, source["id"], report)
            return {"source_id": source["id"], **report}

    # Oldest channels first: avoid repeatedly refreshing only the first page.
    due.sort(key=lambda s: s.get("last_collected_at") or datetime.min.replace(tzinfo=UTC))
    # Bound to two batches even when an admin has configured a large catalogue.
    return await asyncio.gather(*(refresh(source) for source in due[:8]))
