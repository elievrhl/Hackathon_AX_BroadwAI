"""Publisher image discovery and a bounded, public-network-only raster cache."""

import asyncio
import json
import re
from collections import OrderedDict
from dataclasses import dataclass
from time import monotonic
from urllib.parse import unquote, urljoin, urlsplit

from lxml import html
from lxml.etree import ParserError

from broadwai.models import ArticleImage, canonical_url, utcnow
from broadwai.network import RetrievalError, validate_destination
from broadwai.podcasts import podcast_artwork
from broadwai.youtube import thumbnail

MAX_IMAGE_CANDIDATES = 5


@dataclass(frozen=True)
class ImageCandidate:
    image: ArticleImage
    # Only explicit article metadata warrants accepting a relevance-only doubt.
    publisher_selected: bool = False


def srcset_urls(value):
    """Read responsive/lazy source sets, preserving commas inside CDN URLs."""
    choices = []
    remaining = value or ""
    while remaining:
        remaining = remaining.lstrip(" \t\n\r,")
        if not remaining:
            break
        parts = remaining.split(None, 1)
        url = parts[0]
        remaining = parts[1] if len(parts) > 1 else ""
        descriptor = ""
        if url.endswith(","):
            url = url.rstrip(",")
        elif remaining:
            descriptor, separator, remaining = remaining.partition(",")
            if not separator:
                remaining = ""
        match = re.fullmatch(r"(\d+(?:\.\d+)?)(w|x)", descriptor.strip())
        size = float(match[1]) * (600 if match[2] == "x" else 1) if match else 0
        choices.append((url, size))
    # Favor a usable 600–1600px rendition over a tiny placeholder or huge original.
    choices.sort(
        key=lambda choice: (choice[1] > 1600, -choice[1] if choice[1] <= 1600 else choice[1])
    )
    return [url for url, _ in choices]


def is_site_artwork(url):
    """Explicit branding filenames are not article illustrations, even in Open Graph."""
    path = unquote(urlsplit(url).path).casefold()
    return bool(re.search(r"(?:^|[/_.-])(?:logos?|favicons?|avatars?)(?:[/_.-]|$)", path))


def article_image_candidates(document, base_url):
    """Ordered, deduplicated publisher artwork, then substantial body images."""
    try:
        tree = html.fromstring(document) if isinstance(document, (bytes, str)) else document
    except (ValueError, TypeError, ParserError):
        return []

    candidates = []
    seen = set()

    def add(value, alt="", *, publisher_selected=False):
        if not isinstance(value, str) or not value.strip():
            return
        try:
            url = validate_destination(urljoin(base_url, value.strip()))
            if url in seen or is_site_artwork(url):
                return
            if urlsplit(url).path.lower().endswith((".svg", ".ico")):
                return
            seen.add(url)
            candidates.append(
                ImageCandidate(ArticleImage(url=url, alt=str(alt or "")[:500]), publisher_selected)
            )
        except (ValueError, RetrievalError):
            return

    for key in (
        "og:image",
        "og:image:secure_url",
        "og:image:url",
        "twitter:image",
        "twitter:image:src",
    ):
        nodes = tree.xpath("//meta[@property=$key or @name=$key]/@content", key=key)
        alts = tree.xpath(
            "//meta[@property=$key or @name=$key]/@content",
            key="og:image:alt" if key.startswith("og:") else "twitter:image:alt",
        )
        for value in nodes:
            add(value, alts[0] if alts else "", publisher_selected=True)

    for value in tree.xpath('//link[contains(concat(" ", @rel, " "), " image_src ")]/@href'):
        add(value, publisher_selected=True)

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
                add(value, alt, publisher_selected=True)

    containers = (
        "//article//img | //main//img | "
        '//*[contains(concat(" ", normalize-space(@class), " "), " entry-content ")]//img | '
        '//*[contains(concat(" ", normalize-space(@class), " "), " post-content ")]//img | '
        '//*[@itemprop="articleBody"]//img'
    )
    for node in tree.xpath(containers):
        if node.xpath("ancestor::nav | ancestor::aside | ancestor::footer"):
            continue
        ancestors = " ".join(
            f"{parent.get('class', '')} {parent.get('id', '')}" for parent in node.iterancestors()
        )
        if re.search(
            r"(?:^|[\s_-])(related|recommended|advert|ads|promo)(?:$|[\s_-])", ancestors, re.I
        ):
            continue
        if any(
            node.get(key, "").isdigit() and int(node.get(key)) < minimum
            for key, minimum in (("width", 120), ("height", 90))
        ):
            continue
        label = (node.get("alt", "") + " " + node.get("class", "")).casefold()
        if re.search(r"\b(avatar|logo|tracking|icon)\b", label):
            continue
        alt = node.get("alt", "")
        # libxml's HTML parser may nest <img> under the HTML5 void <source> tag.
        sources = node.xpath("ancestor::picture[1]//source") + [node]
        for source in sources:
            for attribute in ("data-srcset", "data-lazy-srcset", "srcset"):
                for value in srcset_urls(source.get(attribute)):
                    add(value, alt)
        for attribute in ("data-src", "data-lazy-src", "data-original", "src"):
            add(node.get(attribute), alt)
    return candidates[:MAX_IMAGE_CANDIDATES]


def article_image(document, base_url):
    """Compatibility entry point for ingestion; serving can try all candidates."""
    candidates = article_image_candidates(document, base_url)
    return candidates[0].image if candidates else None


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
                result = await self._resolve(article)
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

    async def _resolve(self, article):
        media_image = thumbnail(article) or podcast_artwork(article)
        if (
            not media_image
            and self.require_review
            and (
                self.reviewer is None
                or not await asyncio.to_thread(self.store.article_has_cover, article.id)
            )
        ):
            return None

        downloads = {}

        async def attempt(image, *, publisher_selected=False):
            # Reusing bytes also lets a cached uncertain verdict be reconsidered
            # after the article page confirms the publisher selected this image.
            if image.url not in downloads:
                if len(downloads) >= MAX_IMAGE_CANDIDATES:
                    return None
                downloads[image.url] = None
                try:
                    download = await self.fetcher.get(image.url)
                    media_type = raster_type(download.body)
                    if media_type and download.content_type in {
                        media_type,
                        "application/octet-stream",
                    }:
                        downloads[image.url] = (download.body, media_type)
                except (RetrievalError, ValueError):
                    return None
            result = downloads[image.url]
            if result and not media_image and self.reviewer is not None:
                if not await self.reviewer.check(
                    article, result[0], publisher_selected=publisher_selected
                ):
                    return None
            return result

        if media_image:
            return await attempt(media_image)
        if article.format == "podcast":
            return None

        saved = article.image
        if saved and not is_site_artwork(saved.url):
            if result := await attempt(saved):
                return result

        # An old "no image" record must not block better extraction forever.
        # The service and HTTP negative caches limit fresh attempts to every 5 min.
        try:
            page = await self.fetcher.get(article.url)
        except (RetrievalError, ValueError):
            return None
        if page.content_type not in {"text/html", "application/xhtml+xml"}:
            return None
        candidates = await asyncio.to_thread(article_image_candidates, page.body, page.url)
        for candidate in candidates:
            result = await attempt(candidate.image, publisher_selected=candidate.publisher_selected)
            if result:
                await asyncio.to_thread(
                    self.store.set_article_image, article.id, candidate.image, utcnow()
                )
                return result
        # Keep a real saved URL on transient/review failures; remove obsolete logos.
        if not saved or is_site_artwork(saved.url):
            await asyncio.to_thread(
                self.store.set_article_image,
                article.id,
                candidates[0].image if candidates else None,
                utcnow(),
            )
        return None
