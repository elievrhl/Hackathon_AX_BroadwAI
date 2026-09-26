import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from broadwai.models import Article, Profile, utcnow

STOPWORDS = set(
    "a au aux avec ce ces dans de des du en et est la le les pour par sur un une "
    "the a an and are as at be by for from in is it of on or that this to with".split()
)


def tokens(text: str) -> list[str]:
    text = "".join(
        c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c)
    )
    return [word for word in re.findall(r"\w+", text) if word not in STOPWORDS]


def similarity(a: Article, b: Article) -> float:
    if a.content_hash == b.content_hash:
        return 1.0
    if a.text and b.text and len(a.text) >= 200:
        if " ".join(a.text.split()) == " ".join(b.text.split()):
            return 1.0
    left, right = set(tokens(a.title)), set(tokens(b.title))
    return len(left & right) / max(1, len(left | right))


def eligible(article: Article, profile: Profile, seen: set[str]) -> bool:
    if article.discovery.get("kind") == "source_directory":
        return False
    if article.id in seen or article.id in profile.seen_article_ids:
        return False
    if any(
        article.source == host.lower() or article.source.endswith("." + host.lower())
        for host in profile.excluded_sources
    ):
        return False
    if profile.languages and article.language and article.language not in profile.languages:
        return False
    words = set(tokens(article.title + " " + (article.text or article.excerpt)))
    return not any(
        set(tokens(topic)) and set(tokens(topic)) <= words for topic in profile.excluded_topics
    )


@dataclass
class Ranked:
    article: Article
    score: float
    matched_interests: list[str]
    score_details: dict = field(default_factory=dict)


def rank(
    articles: list[Article],
    profile: Profile,
    seen: set[str] | None = None,
    query: str | None = None,
    now: datetime | None = None,
    needs: list[dict] | None = None,
) -> list[Ranked]:
    """BM25 baseline: no LLM call, training, or embedding download required."""
    articles = [a for a in articles if eligible(a, profile, seen or set())]
    if not articles:
        return []
    # RSS descriptions are less polluted by navigation/footer text than full HTML extracts.
    docs = [Counter(tokens(a.title + " " + (a.excerpt or a.text)[:1800])) for a in articles]
    lengths = [sum(doc.values()) for doc in docs]
    average = max(1, sum(lengths) / len(docs))
    frequencies = Counter(term for doc in docs for term in doc)
    now = now or utcnow()

    def bm25(terms: list[str], index: int) -> float:
        score = 0.0
        for term in set(terms):
            count = docs[index][term]
            if count:
                idf = math.log(
                    1 + (len(docs) - frequencies[term] + 0.5) / (frequencies[term] + 0.5)
                )
                score += (
                    idf * count * 2.2 / (count + 1.2 * (0.25 + 0.75 * lengths[index] / average))
                )
        return score

    ranked = []
    for i, article in enumerate(articles):
        scores = [
            (interest.topic, interest.weight * bm25(tokens(interest.topic), i))
            for interest in profile.interests
        ]
        relevance = sum(value for _, value in scores)
        need_scores = {
            need["id"]: (4 if need["priority"] == "primary" else 1) * bm25(tokens(need["query"]), i)
            for need in (needs or [])
        }
        notes_score = bm25(tokens(profile.notes), i) if profile.notes else 0
        relevance += sum(need_scores.values()) + 2 * notes_score
        query_score = 0
        if query:
            temporal = set(
                "recent recents latest article articles septembre september actualite news".split()
            )
            query_score = bm25(
                [t for t in tokens(query) if not t.isdigit() and t not in temporal], i
            )
            if query_score <= 0:
                continue
            relevance += 2 * query_score
        age = (
            max(0, (now - article.published_at).total_seconds() / 86400)
            if article.published_at
            else 30
        )
        freshness = 0.12 * math.exp(-age / 7)
        ranked.append(
            Ranked(
                article,
                relevance + freshness,
                [topic for topic, value in scores if value > 0],
                {
                    "interests": dict(scores),
                    "query_bonus": 2 * query_score,
                    "freshness": freshness,
                    "age_days": age,
                    "needs": need_scores,
                    "notes": notes_score,
                },
            )
        )
    return sorted(ranked, key=lambda r: (-r.score, r.article.id))


def diversify(ranked: list[Ranked], limit: int, max_per_source: int) -> list[Ranked]:
    pool = list(ranked)
    chosen: list[Ranked] = []
    counts: Counter = Counter()
    covered: set[str] = set()
    scale = max((r.score for r in ranked), default=1) or 1
    # Hashing/tokenizing full texts in every pair/iteration blocked the API for minutes.
    features = {
        r.article.id: (
            r.article.content_hash,
            " ".join(r.article.text.split()),
            len(r.article.text),
            set(tokens(r.article.title)),
        )
        for r in ranked
    }
    max_similarity = {r.article.id: 0.0 for r in ranked}

    def pair_similarity(a, b):
        ah, at, al, aw = features[a.article.id]
        bh, bt, _, bw = features[b.article.id]
        if ah == bh or (at and bt and al >= 200 and at == bt):
            return 1.0
        return len(aw & bw) / max(1, len(aw | bw))

    while pool and len(chosen) < limit:
        pool = [
            r
            for r in pool
            if counts[r.article.source] < max_per_source and max_similarity[r.article.id] < 0.8
        ]
        if not pool:
            break
        best = max(
            pool,
            key=lambda r: (
                r.score / scale
                + 0.2 * len(set(r.matched_interests) - covered)
                - 0.35 * max_similarity[r.article.id]
            ),
        )
        chosen.append(best)
        counts[best.article.source] += 1
        covered.update(best.matched_interests)
        pool.remove(best)
        for r in pool:
            max_similarity[r.article.id] = max(
                max_similarity[r.article.id], pair_similarity(r, best)
            )
    return chosen
