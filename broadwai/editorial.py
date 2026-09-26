"""Cheap candidate context and deterministic checks around the editor's judgments."""

from collections import Counter

from broadwai.models import utcnow
from broadwai.ranking import diversify


def preview_pool(ranked, limit):
    # Leave room for recent, multilingual discoveries missed by lexical retrieval.
    relevant = diversify(ranked, limit * 2 // 3, 5)
    recent = sorted(
        ranked, key=lambda r: r.article.published_at or r.article.collected_at, reverse=True
    )
    selected = {r.article.id: r for r in relevant}
    counts = Counter(r.article.source for r in relevant)
    for row in recent:
        if len(selected) >= limit:
            break
        if row.article.id not in selected and counts[row.article.source] < 5:
            selected[row.article.id] = row
            counts[row.article.source] += 1
    return list(selected.values())


def preview(row):
    a = row.article
    return {
        "article_id": a.id,
        "title": a.title,
        "source": a.source,
        "date": a.published_at.isoformat() if a.published_at else None,
        "language": a.language,
        "lexical_score": round(row.score, 3),
        "excerpt": (a.excerpt or a.text)[:320],
    }


def compact_candidate(c, pick=None):
    # The full, cached brief remains available in diagnostics. Send it only once,
    # without redundant key points, lexical scores or long URL query strings.
    return {
        "article_id": c.article_id,
        "title": c.title,
        "source": c.source,
        "date": c.published_at.isoformat() if c.published_at else None,
        "summary": c.brief.summary,
        "caveats": c.brief.caveats,
        "content_type": c.brief.content_type,
        "language": c.brief.language,
        "extraction_status": c.extraction_status,
        "reading_kind": "evergreen" if pick and pick.evergreen else "current",
    }


def coverage(candidates, picks, sections, size, source_cap):
    counts = Counter(c.source for c in candidates.values())
    section_counts = Counter(picks[id_].section for id_ in candidates if id_ in picks)
    return {
        "target": size,
        "prepared": len(candidates),
        "source_capacity_upper_bound": sum(min(n, source_cap) for n in counts.values()),
        "by_source": dict(counts),
        "by_planned_section": dict(section_counts),
        "empty_sections": [s for s in sections if not section_counts[s]],
        "today": utcnow().date().isoformat(),
    }
