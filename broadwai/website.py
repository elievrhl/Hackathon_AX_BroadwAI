"""Discover article links in public HTML without running scripts or following pagination."""

import json
import re
from datetime import datetime
from urllib.parse import urljoin, urlsplit

import trafilatura

from broadwai.models import Article, utcnow
from broadwai.network import Download, RetrievalError, validate_destination

HTML_TYPES = {"text/html", "application/xhtml+xml"}
ARTICLE_TYPES = {
    "Article",
    "NewsArticle",
    "BlogPosting",
    "ReportageNewsArticle",
    "AnalysisNewsArticle",
}
NON_ARTICLE_PATHS = {
    "about",
    "about-us",
    "contact",
    "privacy",
    "privacy-policy",
    "terms",
    "login",
    "signin",
    "subscribe",
    "subscription",
    "newsletter",
    "search",
    "tag",
    "tags",
    "category",
    "categories",
    "author",
    "authors",
    "page",
    "feed",
    "rss",
    "mentions-legales",
    "abonnement",
    "connexion",
}
ASSET_SUFFIXES = (
    ".xml",
    ".json",
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".zip",
    ".mp3",
    ".mp4",
    ".css",
    ".js",
    ".ico",
)
BLOCKED_MESSAGES = (
    "javascript is disabled in your browser",
    "please enable javascript to proceed",
    "verify you are human",
    "checking your browser before accessing",
)
NAVIGATION = re.compile(r"(?:^|[\s_-])(nav|navigation|menu|sidebar|footer)(?:$|[\s_-])", re.I)


def readable_text(text: str | None) -> bool:
    return bool(
        text
        and len(text.strip()) >= 100
        and not (len(text) < 1500 and any(message in text.lower() for message in BLOCKED_MESSAGES))
    )


def same_site(first: str, second: str) -> bool:
    # Accept the common www redirect, but not arbitrary subdomains or third-party links.
    return urlsplit(first).hostname.removeprefix("www.") == urlsplit(second).hostname.removeprefix(
        "www."
    )


def html_tree(download: Download):
    if download.content_type not in HTML_TYPES:
        raise RetrievalError("Une page HTML de blog ou de journal est requise")
    tree = trafilatura.load_html(download.body)
    if tree is None:
        raise RetrievalError("Page HTML illisible")
    return tree


def structured_items(tree):
    """Bound traversal and ignore broken JSON-LD, which is common on publisher pages."""
    for script in tree.xpath('//script[@type="application/ld+json"]')[:50]:
        try:
            pending = [json.loads(script.text or "")]
        except (ValueError, RecursionError):
            continue
        for _ in range(5000):
            if not pending:
                break
            item = pending.pop()
            if isinstance(item, list):
                pending.extend(reversed(item))
            elif isinstance(item, dict):
                yield item
                pending.extend(reversed(list(item.values())))


def schema_types(item):
    types = item.get("@type", [])
    return {
        t.rsplit("/", 1)[-1]
        for t in (types if isinstance(types, list) else [types])
        if isinstance(t, str)
    }


def article_links(download: Download, limit: int) -> list[str]:
    tree = html_tree(download)
    candidates: dict[str, int] = {}

    def add(href, score):
        if not isinstance(href, str) or not href.strip() or href.startswith("#"):
            return
        try:
            target = validate_destination(urljoin(download.url, href))
            parts = urlsplit(target)
            segments = set(parts.path.lower().strip("/").split("/"))
            if (
                not same_site(target, download.url)
                or target == validate_destination(download.url)
                or parts.path == "/"
                or segments & NON_ARTICLE_PATHS
                or parts.path.lower().endswith(ASSET_SUFFIXES)
            ):
                return
            candidates[target] = max(score, candidates.get(target, 0))
        except (ValueError, RetrievalError):
            return

    for item in structured_items(tree):
        if schema_types(item) & ARTICLE_TYPES:
            add(item.get("url") or item.get("@id"), 4)
        elif "ListItem" in schema_types(item):
            value = item.get("item")
            add(item.get("url") or (value.get("url") if isinstance(value, dict) else value), 3)
    for anchor in tree.xpath("//a[@href]"):
        if anchor.xpath("ancestor::nav | ancestor::footer | ancestor::aside") or any(
            parent.get("role") == "navigation"
            or NAVIGATION.search(parent.get("class", "") + " " + parent.get("id", ""))
            for parent in anchor.iterancestors()
        ):
            continue
        title = " ".join(anchor.text_content().split()) or anchor.get("title", "")
        prominent = bool(
            anchor.xpath(
                "ancestor::article | ancestor::h1 | ancestor::h2 | "
                "ancestor::h3 | .//h1 | .//h2 | .//h3"
            )
        )
        bookmark = "bookmark" in anchor.get("rel", "").split()
        permalink = anchor.get("title", "").lower().startswith("permalink")
        if prominent or bookmark or permalink or len(title) >= 15:
            add(anchor.get("href"), 4 if bookmark or permalink else 2 if prominent else 1)
    return sorted(candidates, key=candidates.get, reverse=True)[:limit]


def website_article(download: Download, source_url: str) -> Article:
    """Require article signals before importing, and never trust HTML canonical URLs."""
    url = validate_destination(download.url)
    if not same_site(url, source_url):
        raise RetrievalError("L'article redirige vers un autre site")
    tree = html_tree(download)
    metadata = trafilatura.extract_metadata(tree, default_url=url, extensive=False)
    structured = list(structured_items(tree))
    # JSON-LD for related stories or a list of stories does not describe this page.
    schemas = [item for item in structured if schema_types(item) & ARTICLE_TYPES]
    marked = bool(tree.xpath('//meta[@property="og:type" or @name="og:type"][@content="article"]'))
    for item in schemas:
        target = item.get("url") or item.get("mainEntityOfPage") or item.get("@id")
        if isinstance(target, dict):
            target = target.get("@id") or target.get("url")
        try:
            if isinstance(target, str) and validate_destination(urljoin(url, target)) == url:
                marked = True
            elif not target and len(schemas) == 1:
                marked = True
        except (ValueError, RetrievalError):
            continue
    article_nodes = tree.xpath("//article")
    if not marked and (
        len(article_nodes) > 1
        or not (
            len(article_nodes) == 1 or (tree.xpath("//h1") and tree.xpath("//p") and metadata.date)
        )
    ):
        raise RetrievalError("La page ne présente pas de contenu d'article identifiable")
    title = (metadata.title or "").strip()
    if not title:
        raise RetrievalError("Titre d'article introuvable")
    if title.casefold() == (metadata.sitename or "").strip().casefold():
        raise RetrievalError("Page d'accueil ou d'archives : le titre est celui du site")
    text = trafilatura.extract(tree, include_comments=False, include_tables=True) or ""
    excerpt = (metadata.description or "").strip()
    # A paywall can leave usable metadata, but an interstitial is never article text.
    extracted = readable_text(text)
    if not extracted and not (marked and readable_text(excerpt)):
        raise RetrievalError("Texte ou extrait d'article insuffisant (accès limité ou JavaScript)")
    published = None
    if metadata.date:
        try:
            published = datetime.fromisoformat(metadata.date.replace("Z", "+00:00"))
        except ValueError:
            pass
    language = tree.get("lang") or metadata.language
    return Article.create(
        url=url,
        title=title[:1000],
        excerpt=excerpt[:12000],
        text=text if extracted else "",
        extraction_status="extracted" if extracted else "excerpt",
        published_at=published,
        language=language.replace("_", "-").split("-")[0].lower() if language else None,
        discovery={
            "kind": "website",
            "source_url": source_url,
            "retrieved_at": utcnow().isoformat(),
        },
    )
