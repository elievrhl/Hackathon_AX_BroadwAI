"""Publisher image discovery and a bounded, public-network-only raster cache."""

import asyncio
import json
import re
from collections import OrderedDict
from datetime import timedelta
from time import monotonic
from urllib.parse import unquote, urljoin, urlsplit

from lxml import html
from lxml.etree import ParserError

from broadwai.models import ArticleImage, canonical_url, utcnow
from broadwai.network import RetrievalError, validate_destination
from broadwai.podcasts import podcast_artwork
from broadwai.youtube import thumbnail


def is_site_artwork(url):
    """Explicit branding filenames are not article illustrations, even in Open Graph."""
    path = unquote(urlsplit(url).path).casefold()
    return bool(re.search(r"(?:^|[/_.-])(?:logos?|favicons?|avatars?)(?:[/_.-]|$)", path))


def article_image(document, base_url):
    """Read declared article artwork, then a substantial image inside the article."""
    try:
        tree = html.fromstring(document) if isinstance(document, (bytes, str)) else document
    except (ValueError, TypeError, ParserError):
        return None

    def candidate(value, alt=""):
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            url = validate_destination(urljoin(base_url, value.strip()))
            if is_site_artwork(url) or urlsplit(url).path.lower().endswith((".svg", ".ico")):
                return None
            return ArticleImage(url=url, alt=str(alt or "")[:500])
        except (ValueError, RetrievalError):
            return None

    for key in ("og:image", "og:image:url", "twitter:image", "twitter:image:src"):
        nodes = tree.xpath("//meta[@property=$key or @name=$key]/@content", key=key)
        alts = tree.xpath(
            "//meta[@property=$key or @name=$key]/@content",
            key="og:image:alt" if key.startswith("og:") else "twitter:image:alt",
        )
        for value in nodes:
            if image := candidate(value, alts[0] if alts else ""):
                return image

    def objects(value):
        if isinstance(value, list):
            for item in value:
                yield from objects(item)
        elif isinstance(value, dict):
            yield value
            yield from objects(value.get("@graph"))

    for script in tree.xpath('//script[@type="application/ld+json"]/text()'):
        try:
            data = json.loads(script)
        except (ValueError, TypeError):
            continue
        for item in objects(data):
            types = item.get("@type", [])
            types = [types] if isinstance(types, str) else types
            if not isinstance(types, list) or not any(
                t
                in {
                    "Article",
                    "NewsArticle",
                    "BlogPosting",
                    "Recipe",
                    "ReportageNewsArticle",
                }
                for t in types
                if isinstance(t, str)
            ):
                continue
            identity = item.get("url") or item.get("mainEntityOfPage")
            if isinstance(identity, dict):
                identity = identity.get("@id") or identity.get("url")
            if isinstance(identity, str):
                try:
                    if canonical_url(urljoin(base_url, identity)) != canonical_url(base_url):
                        continue
                except ValueError:
                    continue
            values = item.get("image", [])
            for value in values if isinstance(values, list) else [values]:
                alt = value.get("caption", "") if isinstance(value, dict) else ""
                value = (
                    value.get("url") or value.get("contentUrl")
                    if isinstance(value, dict)
                    else value
                )
                if image := candidate(value, alt):
                    return image

    for node in tree.xpath("//article//img | //main//figure//img"):
        if node.xpath("ancestor::nav | ancestor::aside | ancestor::footer"):
            continue
        if any(node.get(k, "").isdigit() and int(node.get(k)) < 120 for k in ("width", "height")):
            continue
        label = (node.get("alt", "") + " " + node.get("class", "")).casefold()
        if any(word in label for word in ("avatar", "logo", "tracking", "icon")):
            continue
        for value in (node.get("data-src"), node.get("data-lazy-src"), node.get("src")):
            if image := candidate(value, node.get("alt", "")):
                return image
    return None


def raster_type(body):
    if body.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if body.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "image/webp"
    if body[4:8] == b"ftyp" and body[8:12] in (b"avif", b"avis"):
        return "image/avif"
    return None


class ArticleImages:
    """At most four fetches concurrently; cache 32 MB/128 entries, including misses."""

    def __init__(self, store, fetcher, reviewer=None, *, require_review=False):
        self.store = store
        self.fetcher = fetcher
        self.reviewer = reviewer
        self.require_review = require_review
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.inflight = {}
        self.semaphore = asyncio.Semaphore(4)

    async def get(self, article_id):
        cached = self.cache.get(article_id)
        if cached and cached[0] > monotonic():
            self.cache.move_to_end(article_id)
            return cached[1]
        if article_id not in self.inflight:
            self.inflight[article_id] = asyncio.create_task(self._load(article_id))
        return await asyncio.shield(self.inflight[article_id])

    async def close(self):
        tasks = list(self.inflight.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self.reviewer is not None:
            await self.reviewer.close()

    async def _load(self, article_id):
        result = None
        try:
            async with self.semaphore:
                article = await asyncio.to_thread(self.store.get_article, article_id)
                if article is None:
                    return None
                media_image = thumbnail(article) or podcast_artwork(article)
                if (
                    not media_image
                    and self.require_review
                    and (
                        self.reviewer is None
                        or not await asyncio.to_thread(self.store.article_has_cover, article_id)
                    )
                ):
                    return None
                image = media_image or article.image
                obsolete_artwork = (
                    not media_image and image is not None and is_site_artwork(image.url)
                )
                if obsolete_artwork:
                    image = None
                if article.format == "podcast" and image is None:
                    return None
                if image is None and (
                    obsolete_artwork
                    or article.image_checked_at is None
                    or article.image_checked_at < utcnow() - timedelta(days=7)
                ):
                    page = await self.fetcher.get(article.url)
                    if page.content_type not in {"text/html", "application/xhtml+xml"}:
                        return None
                    image = await asyncio.to_thread(article_image, page.body, page.url)
                    await asyncio.to_thread(
                        self.store.set_article_image, article.id, image, utcnow()
                    )
                if image:
                    download = await self.fetcher.get(image.url)
                    media_type = raster_type(download.body)
                    if media_type and download.content_type in {
                        media_type,
                        "application/octet-stream",
                    }:
                        if (
                            not media_image
                            and self.reviewer is not None
                            and not await self.reviewer.check(article, download.body)
                        ):
                            return None
                        result = (download.body, media_type)
        except (RetrievalError, ValueError):
            pass
        finally:
            previous = self.cache.pop(article_id, None)
            if previous and previous[1]:
                self.cache_bytes -= len(previous[1][0])
            self.cache[article_id] = (monotonic() + (21600 if result else 300), result)
            if result:
                self.cache_bytes += len(result[0])
            while len(self.cache) > 128 or self.cache_bytes > 32_000_000:
                _, (_, evicted) = self.cache.popitem(last=False)
                if evicted:
                    self.cache_bytes -= len(evicted[0])
            self.inflight.pop(article_id, None)
        return result
