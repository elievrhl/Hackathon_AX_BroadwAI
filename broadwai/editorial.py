"""Cheap candidate context and deterministic checks around the editor's judgments."""

from collections import Counter

from broadwai.models import utcnow
from broadwai.ranking import diversify
from broadwai.youtube import evidence_kind


def reading_kind(candidate, pick=None):
    if candidate.brief.dossier:
        return {"evergreen": "evergreen", "research": "research"}.get(
            candidate.brief.dossier.temporal_kind, "current"
        )
    validity = candidate.brief.validity
    if validity:
        return {"evergreen": "evergreen", "research": "research"}.get(validity.kind, "current")
    return (
        "evergreen"
        if pick and pick.evergreen and candidate.brief.content_type != "news"
        else "current"
    )


def preview_pool(ranked, limit, interest_topics=()):
    # Leave room for recent, multilingual discoveries missed by lexical retrieval.
    relevant = diversify(ranked, limit * 2 // 3, 5)
    recent = sorted(
        ranked, key=lambda r: r.article.published_at or r.article.collected_at, reverse=True
    )
    selected = {r.article.id: r for r in relevant}
    # Reserve a share of the pool for every explicit interest, regardless of likes.
    if len(interest_topics) > 1:
        per_topic = max(1, limit // (2 * len(interest_topics)))
        reserved = {}
        reserved_sources = Counter()
        for topic in interest_topics:
            matches = sorted(
                (r for r in ranked if r.score_details.get("interests", {}).get(topic, 0) > 0),
                key=lambda r: r.score_details["interests"][topic],
                reverse=True,
            )
            added = 0
            for row in matches:
                if added >= per_topic:
                    break
                if row.article.id not in reserved and reserved_sources[row.article.source] < 5:
                    reserved[row.article.id] = row
                    reserved_sources[row.article.source] += 1
                    added += 1
        combined = {**reserved, **selected}
        selected = {}
        sources = Counter()
        for id_, row in combined.items():
            if len(selected) < limit and sources[row.article.source] < 5:
                selected[id_] = row
                sources[row.article.source] += 1
    counts = Counter(r.article.source for r in selected.values())
    for row in recent:
        if len(selected) >= limit:
            break
        if row.article.id not in selected and counts[row.article.source] < 5:
            selected[row.article.id] = row
            counts[row.article.source] += 1
    # A small, relevant video reserve prevents a large text catalogue hiding the
    # format before the editor gets a chance to judge it. No extra final-edition slots.
    videos = [r for r in ranked if r.article.format == "video" and r.matched_interests][:5]
    podcasts = [r for r in ranked if r.article.format == "podcast" and r.matched_interests][:3]
    return list({r.article.id: r for r in [*videos, *podcasts, *selected.values()]}.values())[
        :limit
    ]


def preview(row, access=None):
    a = row.article
    return {
        "article_id": a.id,
        "title": a.title,
        "source": a.source,
        "format": a.format,
        "media": a.media,
        "evidence_kind": evidence_kind(a),
        "date": a.published_at.isoformat() if a.published_at else None,
        "language": a.language,
        "lexical_score": round(row.score, 3),
        "excerpt": (a.text or a.excerpt)[:1400],
        "extraction_status": a.extraction_status,
        "access": access,
    }


def compact_candidate(c, pick=None):
    # The full, cached brief remains available in diagnostics. Send it only once,
    # without redundant key points, lexical scores or long URL query strings.
    context = {
        "article_id": c.article_id,
        "title": c.title,
        "source": c.source,
        "format": c.format,
        "media": c.media,
        "evidence_kind": evidence_kind(c),
        "date": c.published_at.isoformat() if c.published_at else None,
        "summary": c.brief.summary,
        "caveats": c.brief.caveats[:2],
        "content_type": c.brief.content_type,
        "language": c.brief.language,
        "extraction_status": c.extraction_status,
        "reading_kind": reading_kind(c, pick),
        "validity": c.brief.validity.model_dump() if c.brief.validity else None,
        "headline": c.brief.headline,
        "level": c.brief.level,
        "matched_need": pick.matched_need if pick else None,
        "planned_section": pick.section if pick else None,
        "selection_kind": "exploration" if pick and pick.exploration else "focused",
        "interest_id": pick.interest_id if pick else None,
        "exploration_reason": pick.exploration_reason if pick and pick.exploration else None,
    }
    if c.brief.dossier:
        # Composition needs the contribution, angle and prerequisites, not a second
        # copy of the reader-facing summary or a model-copied original headline.
        for key in ("summary", "validity", "headline"):
            context.pop(key)
        context["dossier"] = c.brief.dossier.model_dump()
        context["caveats"] = c.brief.caveats
    return context


def coverage(candidates, picks, sections, size, source_cap):
    counts = Counter(c.source for c in candidates.values())
    section_counts = Counter(picks[id_].section for id_ in candidates if id_ in picks)
    return {
        "target": size,
        "prepared": len(candidates),
        "source_capacity_upper_bound": sum(min(n, source_cap) for n in counts.values()),
        "by_source": dict(counts),
        "by_planned_section": dict(section_counts),
        "by_interest": dict(
            Counter(
                picks[id_].interest_id
                for id_ in candidates
                if id_ in picks and picks[id_].interest_id
            )
        ),
        "empty_sections": [s for s in sections if not section_counts[s]],
        "by_need": dict(
            Counter(
                picks[id_].matched_need
                for id_ in candidates
                if id_ in picks and picks[id_].matched_need
            )
        ),
        "today": utcnow().date().isoformat(),
    }
