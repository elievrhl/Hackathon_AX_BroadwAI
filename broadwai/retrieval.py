import asyncio
import calendar
import html
import json
import re
from datetime import UTC, datetime
from urllib.parse import urljoin

import feedparser

from broadwai.extraction import extract_content
from broadwai.images import article_image
from broadwai.models import Article, IngestRequest, utcnow
from broadwai.network import PublicFetcher, RetrievalError, validate_destination
from broadwai.website import article_links, website_article


def plain(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", text)).strip()


def parse_feed(body: bytes, base_url: str, limit: int) -> list[Article]:
    feed = feedparser.parse(body)
    articles = []
    if feed.bozo and not feed.entries:
        raise RetrievalError("Flux RSS/Atom illisible")
    for entry in feed.entries[:limit]:
        try:
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            articles.append(
                Article.create(
                    url=validate_destination(urljoin(base_url, entry.link)),
                    title=plain(entry.get("title", "Sans titre"))[:1000],
                    excerpt=plain(entry.get("summary", ""))[:12000],
                    published_at=datetime.fromtimestamp(calendar.timegm(published), UTC)
                    if published
                    else None,
                    language=feed.feed.get("language", "").split("-")[0] or None,
                )
            )
        except (AttributeError, ValueError, RetrievalError, OverflowError):
            continue
    return articles


class Collector:
    def __init__(self, store, fetcher: PublicFetcher):
        self.store = store
        self.fetcher = fetcher

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
                for article in articles:
                    self.store.put_article(article)
                    ids.add(article.id)
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
