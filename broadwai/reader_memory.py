"""Reading preferences inferred from explicit likes, with article evidence."""

from collections import Counter

from pydantic import Field

from broadwai.models import Model


class ArticleLike(Model):
    user_id: str = Field(min_length=1, max_length=100)
    cover_id: str = Field(min_length=1, max_length=100)
    article_id: str = Field(min_length=1, max_length=100)
    liked: bool


def reading_memory(items: list[dict]) -> dict:
    topics = Counter()
    formats = Counter()
    levels = Counter()
    examples = []
    for item in items[:100]:
        brief = item.get("brief") or {}
        labels = {str(topic).strip().casefold()[:100] for topic in brief.get("topics", [])}
        topics.update(sorted(label for label in labels if label))
        if brief.get("content_type"):
            formats[brief["content_type"]] += 1
        if brief.get("level") and brief["level"] != "unknown":
            levels[brief["level"]] += 1
        if len(examples) < 8:
            examples.append(
                {
                    "article_id": item["article_id"],
                    "title": (item.get("headline") or item.get("title", ""))[:180],
                    "summary": brief.get("summary", "")[:400],
                }
            )
    return {
        "liked_articles_count": len(items[:100]),
        "topics": [{"topic": topic, "likes": count} for topic, count in topics.most_common(20)],
        "formats": dict(formats),
        "reading_levels": dict(levels),
        "examples": examples,
    }
