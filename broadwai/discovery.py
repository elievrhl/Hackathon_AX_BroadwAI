"""Validate source proposals through the same public-only fetcher as article collection."""

import asyncio
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from broadwai.models import Article
from broadwai.network import RetrievalError, validate_destination
from broadwai.retrieval import parse_feed
from broadwai.website import HTML_TYPES, article_links, website_article


def is_feed_directory(article):
    title = article.title.lower()
    path = urlsplit(article.url).path.lower().rstrip("/")
    return "rss" in title or "flux atom" in title or path.endswith(("/rss", "/feed", "/feeds"))


class FeedLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
        self.anchor_urls = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if (
            tag == "link"
            and attrs.get("type", "").lower() in {"application/rss+xml", "application/atom+xml"}
            and attrs.get("href")
        ):
            self.urls.append(attrs["href"])
        if tag == "a" and attrs.get("href"):
            href = attrs["href"]
            try:
                path = urlsplit(href).path.lower()
            except ValueError:
                return
            if any(term in path for term in ("rss", "feed", "atom", ".xml")):
                self.anchor_urls.append(href)


async def validate_feed(fetcher, url, budget=None):
    _, source_url = await validate_source(fetcher, url, budget, allow_website=False)
    return source_url


async def source_article_candidates(fetcher, url, budget, limit=3):
    """Validate a source and sample its real links, without activating a subscription."""

    class CachedFetcher:
        def __init__(self):
            self.pages = {}

        async def get(self, target):
            target = validate_destination(target)
            if target not in self.pages:
                budget.take("source_fetch")
                page = await fetcher.get(target)
                self.pages[target] = page
                self.pages[page.url] = page
            return self.pages[target]

    cached = CachedFetcher()
    kind, source_url = await validate_source(cached, url)
    page = await cached.get(source_url)
    if kind == "rss":
        articles = await asyncio.to_thread(parse_feed, page.body, page.url, limit)
    else:
        links = await asyncio.to_thread(article_links, page, limit)
        articles = []
        for link in links:
            # Reuse the article already downloaded when validating an HTML source.
            if link in cached.pages:
                article = await asyncio.to_thread(website_article, cached.pages[link], page.url)
            else:
                article = Article.create(link, "Article à vérifier")
            articles.append(article)
    return kind, source_url, articles


async def validate_source(fetcher, url, budget=None, *, allow_website=True):
    async def download(target):
        if budget:
            budget.take("source_fetch")
        return await fetcher.get(validate_destination(target))

    page = await download(url)
    try:
        if parse_feed(page.body, page.url, 3):
            return "rss", validate_destination(page.url)
    except RetrievalError:
        pass
    if page.content_type not in HTML_TYPES:
        raise RetrievalError("Aucun flux RSS/Atom exploitable trouvé sur cette page")
    parser = FeedLinks()
    parser.feed(page.body.decode("utf-8", errors="replace"))
    links = []
    for link in parser.urls + parser.anchor_urls:
        try:
            target = validate_destination(urljoin(page.url, link))
            if target != page.url and target not in links:
                links.append(target)
        except (ValueError, RetrievalError):
            continue
    attempts = 0
    for link in links[:3]:
        attempts += 1
        try:
            feed = await download(link)
            if parse_feed(feed.body, feed.url, 3):
                return "rss", validate_destination(feed.url)
        except (RetrievalError, ValueError):
            continue
    if allow_website:
        candidates = await asyncio.to_thread(article_links, page, min(3, 4 - attempts))
        for link in candidates:
            try:
                article = await download(link)
                await asyncio.to_thread(website_article, article, page.url)
                return "website", validate_destination(page.url)
            except (RetrievalError, ValueError):
                continue
        raise RetrievalError("Aucun flux ni article exploitable trouvé sur cette page")
    raise RetrievalError("Aucun flux RSS/Atom exploitable trouvé sur cette page")
