import hashlib
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utcnow() -> datetime:
    return datetime.now(UTC)


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("Une URL HTTP(S) absolue est requise")
    if parts.username or parts.password or parts.port not in {None, 80, 443}:
        raise ValueError("Identifiants et ports non standard interdits")
    host = parts.hostname.lower().rstrip(".").encode("idna").decode()
    if ":" in host:
        host = f"[{host}]"
    if parts.port and (parts.scheme, parts.port) not in {("http", 80), ("https", 443)}:
        host += f":{parts.port}"
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}
    ]
    return urlunsplit((parts.scheme, host, parts.path or "/", urlencode(query), ""))


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Article(Model):
    id: str
    url: str
    title: str = Field(min_length=1, max_length=1000)
    source: str
    text: str = ""
    excerpt: str = ""
    published_at: datetime | None = None
    collected_at: datetime = Field(default_factory=utcnow)
    language: str | None = None
    extraction_status: Literal["excerpt", "extracted"] = "excerpt"
    discovery: dict = Field(default_factory=dict)

    @field_validator("published_at", "collected_at")
    @classmethod
    def aware_date(cls, value: datetime | None) -> datetime | None:
        if value and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    @property
    def content_hash(self) -> str:
        value = f"{self.title}\n{self.extraction_status}\n{self.text or self.excerpt}"
        return hashlib.sha256(value.encode()).hexdigest()

    @classmethod
    def create(cls, url: str, title: str, **kwargs) -> "Article":
        url = canonical_url(url)
        return cls(
            id=hashlib.sha256(url.encode()).hexdigest()[:24],
            url=url,
            title=title,
            source=urlsplit(url).hostname or "",
            **kwargs,
        )


class Interest(Model):
    topic: str = Field(min_length=1, max_length=200)
    weight: float = Field(1.0, gt=0, le=5)


class Profile(Model):
    user_id: str = Field(min_length=1, max_length=100)
    interests: list[Interest] = Field(min_length=1, max_length=20)
    excluded_topics: list[str] = Field(default_factory=list, max_length=30)
    excluded_sources: list[str] = Field(default_factory=list, max_length=30)
    languages: list[str] = Field(default_factory=list, max_length=10)
    level: Literal["beginner", "intermediate", "expert"] = "intermediate"
    notes: str = Field("", max_length=3000)
    seen_article_ids: list[str] = Field(default_factory=list, max_length=2000)


class Brief(Model):
    summary: str = Field(min_length=1, max_length=1800)
    key_points: list[str] = Field(min_length=1, max_length=5)
    topics: list[str] = Field(max_length=8)
    content_type: Literal["news", "analysis", "tutorial", "opinion", "research", "other"]
    level: Literal["beginner", "intermediate", "expert", "unknown"]
    language: str
    caveats: list[str] = Field(max_length=5)


class Candidate(Model):
    article_id: str
    title: str
    url: str
    source: str
    published_at: datetime | None
    extraction_status: str
    score: float
    matched_interests: list[str]
    brief: Brief


class Selection(Model):
    article_id: str
    section: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=500)
    headline: str | None = Field(None, max_length=180)


class EditorialPick(Model):
    article_id: str
    section: str = Field(min_length=1, max_length=100)
    score: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1, max_length=180)
    matches_profile: bool = Field(
        True,
        description="Le sujet central respecte les intérêts ET le contexte explicite des notes",
    )
    evergreen: bool = Field(
        False, description="Lecture de fond durable, pas une actualité ancienne ou non datée"
    )


class EditorialPlan(Model):
    sections: list[str] = Field(min_length=1, max_length=5)
    picks: list[EditorialPick] = Field(max_length=28)
    gaps: list[str] = Field(max_length=5)
    queries: list[str] = Field(max_length=2)


class Decision(Model):
    """One observable action, not a request to expose chain-of-thought."""

    action: Literal["search_catalog", "search_web", "read_article", "propose_source", "finalize"]
    justification: str = Field(min_length=1, max_length=500)
    query: str | None
    article_id: str | None
    title: str | None
    selections: list[Selection]
    source_url: str | None = None


class TraceEvent(Model):
    step: int
    action: str
    justification: str
    outcome: dict


class CoverItem(Model):
    article_id: str
    title: str
    url: str
    source: str
    published_at: datetime | None
    section: str
    reason: str
    brief: Brief
    extraction_status: str
    headline: str | None = None
    reading_kind: Literal["current", "evergreen"] = "current"


class Cover(Model):
    id: str = Field(default_factory=lambda: uuid4().hex)
    user_id: str
    title: str
    created_at: datetime = Field(default_factory=utcnow)
    status: Literal["complete", "partial", "fallback"]
    items: list[CoverItem]
    trace: list[TraceEvent]
    warnings: list[str]
    usage: dict
    diagnostics: dict = Field(default_factory=dict)


class CoverRequest(Model):
    profile: Profile
    discover_web: bool = False
    discover_sources: bool = False
    size: int = Field(18, ge=1, le=20)
    max_per_source: int = Field(3, ge=1, le=10)


class IngestRequest(Model):
    feed_urls: list[str] = Field(default_factory=list, max_length=10)
    website_urls: list[str] = Field(default_factory=list, max_length=10)
    hacker_news: bool = False
    limit_per_source: int = Field(15, ge=1, le=50)

    @field_validator("feed_urls", "website_urls")
    @classmethod
    def validate_urls(cls, urls: list[str]) -> list[str]:
        return [canonical_url(url) for url in urls]


class Feedback(Model):
    user_id: str = Field(min_length=1, max_length=100)
    cover_id: str
    article_id: str
    kind: Literal["impression", "open", "useful", "already_known", "not_interested"]
