"""Public YouTube identities and duration metadata; never infer spoken content."""

import json
import re
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

from broadwai.models import ArticleImage

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
CHANNEL_ID = re.compile(r"UC[A-Za-z0-9_-]{22}\Z")


class _DurationMetadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.canonical = None
        self.duration = None
        self.values = {}

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "link" and "canonical" in (values.get("rel") or "").split():
            self.canonical = values.get("href")
        if tag == "meta" and values.get("itemprop") == "duration":
            self.duration = values.get("content")
        if tag == "meta" and values.get("itemprop"):
            self.values.setdefault(values["itemprop"], values.get("content"))


def summary_video_id(url: str) -> str | None:
    """Recognize video-summary permalinks, not articles merely mentioning a video."""
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"https", "http"}
            or parsed.username
            or parsed.password
            or parsed.port not in {None, 80, 443}
            or parsed.hostname not in {"recapcraft.com", "www.recapcraft.com"}
        ):
            return None
        match = re.fullmatch(r"/v/([A-Za-z0-9_-]{11})/?", parsed.path)
        return match[1] if match else None
    except ValueError:
        return None


def video_metadata(body: bytes, expected_id: str) -> dict | None:
    """Read the original video's public metadata, never its recommended videos or recap."""
    text = body.decode("utf-8", errors="replace")
    metadata = _DurationMetadata()
    metadata.feed(text)
    if not metadata.canonical or video_id(metadata.canonical) != expected_id:
        return None
    details = {}
    match = re.search(r"(?:var\s+)?ytInitialPlayerResponse\s*=\s*", text)
    if match:
        try:
            player, _ = json.JSONDecoder().raw_decode(text[match.end() :])
            details = player.get("videoDetails", {})
            if details.get("videoId") != expected_id:
                return None
        except (ValueError, AttributeError, TypeError):
            return None
    title = details.get("title") or metadata.values.get("name")
    description = details.get("shortDescription") or metadata.values.get("description")
    if not isinstance(title, str) or not title.strip() or not isinstance(description, str):
        return None
    published_at = None
    try:
        published_at = datetime.fromisoformat(metadata.values.get("datePublished") or "")
    except ValueError:
        pass
    return {
        "title": title[:1000],
        "excerpt": description[:12000],
        "published_at": published_at,
        "media": {
            "provider": "youtube",
            "video_id": expected_id,
            "channel_id": details.get("channelId"),
            "channel_title": details.get("author"),
            "duration_seconds": metadata_duration(body, expected_id),
            "original_title": title[:1000],
            "original_description": description[:12000],
            "original_published_at": published_at.isoformat() if published_at else None,
        },
    }


def metadata_duration(body: bytes, expected_id: str) -> float | None:
    """Read only the primary video's published duration, never recommendation durations."""
    metadata = _DurationMetadata()
    metadata.feed(body.decode("utf-8", errors="replace"))
    if not metadata.canonical or video_id(metadata.canonical) != expected_id:
        return None
    match = re.fullmatch(
        r"PT(?:(\d{1,6})H)?(?:(\d{1,6})M)?(?:(\d{1,6}(?:\.\d{1,3})?)S)?",
        metadata.duration or "",
    )
    if not match:
        return None
    hours, minutes, seconds = (float(value or 0) for value in match.groups())
    duration = hours * 3600 + minutes * 60 + seconds
    return duration if duration > 0 else None


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
