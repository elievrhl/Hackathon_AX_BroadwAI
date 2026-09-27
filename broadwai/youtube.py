"""Public YouTube feed identities; no watch-page scraping or inferred transcripts."""

import re
from urllib.parse import parse_qs, urlsplit

from broadwai.models import ArticleImage

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
CHANNEL_ID = re.compile(r"UC[A-Za-z0-9_-]{22}\Z")


def video_id(url: str) -> str | None:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"https", "http"} or parsed.username or parsed.password:
            return None
        if parsed.port not in {None, 80, 443}:
            return None
        parts = parsed.path.strip("/").split("/")
        if parsed.hostname == "youtu.be" and len(parts) == 1:
            value = parts[0]
        elif parsed.hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            if parsed.path == "/watch":
                value = parse_qs(parsed.query).get("v", [""])[0]
            elif len(parts) == 2 and parts[0] in {"shorts", "embed", "live"}:
                value = parts[1]
            else:
                return None
        else:
            return None
        return value if VIDEO_ID.fullmatch(value) else None
    except ValueError:
        return None


def channel_feed(url: str) -> str | None:
    """Accept a canonical channel URL or a public Atom feed, never arbitrary hosts."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"https", "http"} or parsed.username or parsed.password:
            return None
        if parsed.hostname not in {"youtube.com", "www.youtube.com"}:
            return None
        if parsed.port not in {None, 80, 443}:
            return None
        parts = parsed.path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "channel":
            value = parts[1]
        elif parsed.path == "/feeds/videos.xml":
            value = parse_qs(parsed.query).get("channel_id", [""])[0]
        else:
            return None
        if CHANNEL_ID.fullmatch(value):
            return "https://www.youtube.com/feeds/videos.xml?channel_id=" + value
    except ValueError:
        pass
    return None


def thumbnail(article) -> ArticleImage | None:
    """Derive the thumbnail from the actual watch URL, ignoring untrusted image metadata."""
    id_ = video_id(article.url) if article.format == "video" else None
    if id_:
        return ArticleImage(
            url=f"https://i.ytimg.com/vi/{id_}/hqdefault.jpg", alt=article.title[:500]
        )
    return None


def evidence_kind(article) -> str:
    if article.format in {"video", "podcast"}:
        return "transcript" if article.extraction_status == "extracted" else "description_only"
    return "full_text" if article.extraction_status == "extracted" else "excerpt"
