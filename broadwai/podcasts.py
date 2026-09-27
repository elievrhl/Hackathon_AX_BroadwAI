"""Read publisher-supplied podcast metadata without downloading or transcribing audio."""

import re
from urllib.parse import urljoin, urlsplit

from broadwai.models import ArticleImage
from broadwai.network import RetrievalError, validate_destination


def public_url(value, base_url):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return validate_destination(urljoin(base_url, value))
    except (ValueError, RetrievalError):
        return None


def duration_seconds(value):
    """iTunes durations are seconds, MM:SS or HH:MM:SS; never guess missing values."""
    value = str(value or "").strip()
    if not re.fullmatch(r"\d{1,6}(?::\d{2}){0,2}", value):
        return None
    parts = [int(part) for part in value.split(":")]
    if any(part >= 60 for part in parts[1:]):
        return None
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds if 0 < seconds <= 86400 else None


def audio_enclosure(entry, base_url):
    for enclosure in entry.get("enclosures", []):
        kind = str(enclosure.get("type", "")).lower().split(";")[0]
        url = public_url(enclosure.get("href"), base_url)
        if not url:
            continue
        audio_type = kind.startswith("audio/") or kind == "application/ogg"
        audio_extension = (
            urlsplit(url).path.lower().endswith((".mp3", ".m4a", ".ogg", ".opus", ".wav"))
        )
        if audio_type or (not kind or kind == "application/octet-stream") and audio_extension:
            return url
    return None


def episode_metadata(entry, feed, base_url, repeated_links):
    audio_url = audio_enclosure(entry, base_url)
    if not audio_url:
        return None
    link = public_url(entry.get("link"), base_url)
    show_url = public_url(feed.get("link"), base_url)
    # Many feeds reuse the show homepage for every item. It is not an episode
    # permalink: use the unique audio URL so episodes never overwrite each other.
    episode_url = link
    if not link or link == show_url or link in repeated_links or urlsplit(link).path in {"", "/"}:
        episode_url = audio_url
    image_url = None
    for owner in (entry, feed):
        artwork = owner.get("image") or {}
        if isinstance(artwork, dict):
            image_url = public_url(artwork.get("href") or artwork.get("url"), base_url)
            if image_url:
                break
    return {
        "url": episode_url,
        "source": urlsplit(link or show_url or base_url).hostname,
        "media": {
            "provider": "rss_podcast",
            "feed_url": base_url,
            "guid": str(entry.get("id", ""))[:1000],
            "show_title": str(feed.get("title", "Podcast"))[:300],
            "publisher": str(feed.get("author", ""))[:300],
            "audio_url": audio_url,
            "duration_seconds": duration_seconds(entry.get("itunes_duration")),
            "episode_type": entry.get("itunes_episodetype", "full"),
            "artwork_url": image_url,
        },
        "image": ArticleImage(url=image_url, alt=str(feed.get("title", "Podcast"))[:500])
        if image_url
        else None,
    }


def podcast_artwork(article):
    """Feed artwork is a show/episode cover, not an editorial photograph to classify."""
    media = article.media or {}
    if (
        article.format == "podcast"
        and media.get("provider") == "rss_podcast"
        and article.discovery.get("kind") == "podcast_episode"
        and article.image
        and article.image.url == media.get("artwork_url")
        and public_url(media.get("audio_url"), article.url)
    ):
        return article.image
    return None
