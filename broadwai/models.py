import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_language(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip().casefold().replace("_", "-")
    aliases = {
        "français": "fr",
        "francais": "fr",
        "french": "fr",
        "fra": "fr",
        "fre": "fr",
        "anglais": "en",
        "english": "en",
        "eng": "en",
    }
    if re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*", value):
        value = value.split("-", 1)[0]
    return aliases.get(value, value)


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


class ArticleLink(Model):
    label: str = Field(max_length=500)
    url: str = Field(max_length=2000)


class ArticleImage(Model):
    url: str = Field(max_length=2000)
    alt: str = Field("", max_length=500)

    @field_validator("url")
    @classmethod
    def absolute_url(cls, value):
        return canonical_url(value)


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
    content_links: list[ArticleLink] = Field(default_factory=list, max_length=40)
    image: ArticleImage | None = None
    image_checked_at: datetime | None = None
    # Persisted catalog entries may already include multimedia metadata. Keep it
    # on reads and subsequent writes, including the empty fields on text articles.
    format: Literal["article", "video", "podcast", "animation"] = "article"
    media: dict | None = None
    transcript: list[dict] = Field(default_factory=list)

    @field_validator("language")
    @classmethod
    def normalized_language(cls, value):
        return normalize_language(value)

    @field_validator("published_at", "collected_at", "image_checked_at")
    @classmethod
    def aware_date(cls, value: datetime | None) -> datetime | None:
        if value and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    @property
    def content_hash(self) -> str:
        value = f"{self.title}\n{self.extraction_status}\n{self.text or self.excerpt}"
        if self.content_links:
            value += "\n" + json.dumps(
                [link.model_dump() for link in self.content_links], sort_keys=True
            )
        return hashlib.sha256(value.encode()).hexdigest()

    @property
    def reading_time_minutes(self) -> int | None:
        """Estimate from the extracted article at 200 words/minute, never from a brief."""
        if (
            self.format != "article"
            or self.extraction_status != "extracted"
            or not self.text.strip()
        ):
            return None
        return max(1, (len(self.text.split()) + 199) // 200)

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
    reading_memory: dict = Field(default_factory=dict)
    user_id: str = Field(min_length=1, max_length=100)
    interests: list[Interest] = Field(min_length=1, max_length=20)
    excluded_topics: list[str] = Field(default_factory=list, max_length=30)
    excluded_sources: list[str] = Field(default_factory=list, max_length=30)
    languages: list[str] = Field(default_factory=list, max_length=10)
    level: Literal["beginner", "intermediate", "expert"] = "intermediate"
    notes: str = Field("", max_length=3000)
    seen_article_ids: list[str] = Field(default_factory=list, max_length=2000)

    @field_validator("languages")
    @classmethod
    def normalized_languages(cls, values):
        return list(dict.fromkeys(normalize_language(value) for value in values))


class ReadingValidity(Model):
    kind: Literal["news", "research", "evergreen", "event"]
    status: Literal["durable", "time_sensitive", "outdated", "uncertain"]
    reason: str = Field(min_length=1, max_length=350)
    evidence: str = Field(
        min_length=8,
        max_length=180,
        description="Un passage contigu du texte original, sans traduction ni commentaire",
    )


class ReaderNeed(Model):
    topic: str = Field(min_length=1, max_length=150)
    query: str = Field(min_length=1, max_length=200)
    priority: Literal["primary", "secondary"]
    level: Literal["beginner", "intermediate", "expert"]
    evidence: str = Field(
        min_length=1,
        max_length=150,
        description="Un seul passage contigu copié du profil, sans reformulation ni concaténation",
    )


class ReaderConstraint(Model):
    requirement: str = Field(min_length=1, max_length=250)
    evidence: str = Field(
        min_length=1,
        max_length=150,
        description="Un seul passage contigu copié du profil, sans reformulation ni concaténation",
    )


class EditorialIntent(Model):
    needs: list[ReaderNeed] = Field(min_length=1, max_length=8)
    constraints: list[ReaderConstraint] = Field(default_factory=list, max_length=8)


class CitedSource(Model):
    name: str = Field(min_length=1, max_length=200)
    url: str | None = Field(None, max_length=2000)
    relevance: str = Field(
        min_length=1,
        max_length=300,
        description="Apport concret au sujet et intérêt de cette source pour de futures lectures",
    )
    evidence: str = Field(
        min_length=8,
        max_length=300,
        description="Passage contigu du texte fourni qui attribue une information à cette source",
    )


class Brief(Model):
    summary: str = Field(min_length=1, max_length=1800)
    key_points: list[str] = Field(min_length=1, max_length=5)
    topics: list[str] = Field(max_length=8)
    content_type: Literal["news", "analysis", "tutorial", "opinion", "research", "other"]
    level: Literal["beginner", "intermediate", "expert", "unknown"]
    language: str
    caveats: list[str] = Field(max_length=5)
    validity: ReadingValidity | None = None
    headline: str | None = Field(None, max_length=180)
    cited_sources: list[CitedSource] = Field(default_factory=list, max_length=8)

    @field_validator("language")
    @classmethod
    def normalized_language(cls, value):
        return normalize_language(value)


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
    role: Literal["lead", "secondary", "brief", "reading"] | None = None
    matched_need: str | None = None
    evidence: str | None = Field(None, max_length=350)
    story_key: str | None = Field(None, max_length=120)
    distinct_angle: str | None = Field(None, max_length=200)


class EditorialPick(Model):
    article_id: str
    interest_id: str | None = Field(
        None,
        description="Rubrique générale du profil : identifiant interest-N fourni par le serveur",
    )
    section: str = Field(min_length=1, max_length=100)
    score: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1, max_length=180)
    matches_profile: bool = Field(
        description="Lien direct ou connexe avec les intérêts ET respect du contexte des notes",
    )
    evergreen: bool = Field(
        description="Lecture de fond durable, pas une actualité ancienne ou non datée"
    )
    matched_need: str | None = Field(
        None, description="Identifiant du besoin fourni par le serveur"
    )
    evidence: str | None = Field(
        None, max_length=350, description="Citation exacte du titre/extrait"
    )
    temporal_kind: Literal["news", "research", "evergreen", "event"] | None = None
    exploration: bool = Field(
        False, description="Thème connexe mais différent, proposé uniquement pour compléter la une"
    )
    exploration_reason: str | None = Field(
        None,
        max_length=250,
        description="Lien concret avec un intérêt du lecteur et nouvel angle apporté",
    )


class EditorialPlan(Model):
    contract_version: int = 1
    sections: list[str] = Field(min_length=1, max_length=5)
    # A large edition needs replacement candidates because extraction and factual
    # checks intentionally reject weak articles after this first editorial pass.
    picks: list[EditorialPick] = Field(max_length=40)
    gaps: list[str] = Field(max_length=5)
    queries: list[str] = Field(max_length=2)


class SearchScreen(Model):
    picks: list[EditorialPick] = Field(max_length=28)


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
    reading_kind: Literal["current", "evergreen", "research"] = "current"
    role: Literal["lead", "secondary", "brief", "reading"] | None = None
    reading_time_minutes: int | None = Field(None, ge=1)
    selection_kind: Literal["focused", "exploration"] = "focused"
    exploration_reason: str | None = None
    image: ArticleImage | None = None
    image_checked: bool = False


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
    reason: Literal["too_basic", "too_technical", "topic", "source", "style", "other"] | None = None
    comment: str = Field("", max_length=1000)
    preference: "PreferenceCreate | None" = None


class PreferenceInput(Model):
    action: Literal["diversify", "more", "less", "exclude"]
    target_kind: Literal["topic", "source", "content_type", "level", "treatment"]
    target: str = Field(min_length=2, max_length=150)
    explanation: str = Field("", max_length=1000)
    scope: Literal["persistent", "next"] = "persistent"

    @field_validator("target")
    @classmethod
    def meaningful_target(cls, value):
        if not any(c.isalnum() for c in value):
            raise ValueError("Précisez le sujet ou la caractéristique visée")
        return value


class PreferenceCreate(PreferenceInput):
    id: str = Field(default_factory=lambda: uuid4().hex, pattern=r"^[a-zA-Z0-9-]{16,64}$")


class PreferenceUpdate(PreferenceInput):
    revision: int = Field(ge=1)


class ReaderPreference(PreferenceCreate):
    user_id: str
    revision: int = 1
    status: Literal["active", "deleted", "applied", "replaced"] = "active"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    origin_article_id: str | None = None
    origin_cover_id: str | None = None
    applied_cover_id: str | None = None


class PreferenceAssessment(Model):
    article_id: str
    preference_id: str
    match: Literal["yes", "no", "uncertain"]
    evidence: str = Field(max_length=250)


class PreferenceAssessments(Model):
    assessments: list[PreferenceAssessment] = Field(max_length=480)


Feedback.model_rebuild()
