"""Explicit reader rules: limited diversification, soft ranking, hard exclusions.

Raw clicks never create rules. Deleted/replaced rules are not reconstructed from events.
Semantic judgments remain fallible; missing hard-rule checks fail closed.
"""

import math
import re
from urllib.parse import urlsplit

from broadwai.models import PreferenceInput
from broadwai.ranking import tokens

CONTENT_TYPES = {"news", "analysis", "tutorial", "opinion", "research", "other"}
LEVELS = {"beginner", "intermediate", "expert"}


class PreferenceConflict(ValueError):
    pass


def validate_preference(value: PreferenceInput):
    value = value.model_copy()
    if value.target_kind == "source":
        host = urlsplit(value.target if "://" in value.target else "https://" + value.target)
        if not host.hostname or "." not in host.hostname or host.username or host.password:
            raise ValueError("Indiquez le domaine de la source, par exemple example.org")
        value.target = host.hostname.lower().rstrip(".").encode("idna").decode()
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", value.target):
            raise ValueError("Domaine de source invalide")
    allowed = {"content_type": CONTENT_TYPES, "level": LEVELS}.get(value.target_kind)
    if allowed and value.target not in allowed:
        raise ValueError("Type de contenu ou niveau inconnu")
    if not tokens(value.target):
        raise ValueError("Précisez un sujet ou une caractéristique")
    return value


def target_key(value):
    return value.target_kind + ":" + " ".join(tokens(value.target))


def semantic(preference):
    # A qualification can narrow a topic, format, level or source. Never drop it.
    return preference.target_kind in {"topic", "treatment"} or bool(preference.explanation)


def direct_match(preference, article, brief=None):
    if semantic(preference):
        return None
    if preference.target_kind == "source":
        return article.source == preference.target or article.source.endswith(
            "." + preference.target
        )
    if brief is None:
        return None
    if preference.target_kind == "content_type":
        return brief.content_type == preference.target
    if preference.target_kind == "level":
        return None if brief.level == "unknown" else brief.level == preference.target
    return None


class PreferencePolicy:
    def __init__(self, preferences=(), size=18):
        self.rules = list(preferences)
        self.size = size
        self.discovery_limit = max(1, math.ceil(size / 6))
        self.less_limit = max(1, size // 6)
        self.matches = {}

    def context(self):
        return {
            "rules": [r.model_dump(mode="json") for r in self.rules],
            "diversification_total_slots": self.discovery_limit,
            "less_max_per_rule": self.less_limit,
            "instruction": (
                "Les règles sont explicites et déjà corrigées par le lecteur. Respecter la cible "
                "ET son explication, sans élargir une exclusion. Diversifier réserve quelques "
                "places au total et conserve les intérêts habituels. Plus/moins sont des "
                "préférences relatives, exclude est obligatoire, même en Exploration."
            ),
        }

    def match(self, rule, article, brief=None):
        direct = direct_match(rule, article, brief)
        if direct is not None:
            return "yes" if direct else "no"
        return self.matches.get(article.id, {}).get(rule.id, "uncertain")

    def blocked(self, article, brief=None):
        return [
            r.id
            for r in self.rules
            if r.action == "exclude" and self.match(r, article, brief) != "no"
        ]

    def boost(self, article, brief):
        value = sum(
            {"more": 0.25, "less": -0.4}.get(r.action, 0)
            for r in self.rules
            if self.match(r, article, brief) == "yes"
        )
        return max(-0.5, min(0.5, value))

    def discoveries(self, article, brief):
        return [
            r.id
            for r in self.rules
            if r.action == "diversify" and self.match(r, article, brief) == "yes"
        ]

    def reduced(self, article, brief):
        return [
            r.id
            for r in self.rules
            if r.action == "less" and self.match(r, article, brief) == "yes"
        ]

    def order(self, selections, articles, candidates):
        """Keep editorial ordering except for bounded explicit reader adjustments."""
        if not self.rules:
            return selections
        indexed = list(enumerate(selections))

        def priority(row):
            index, selection = row
            a = articles.get(selection.article_id)
            c = candidates.get(selection.article_id)
            if not a or not c:
                return (1, index)
            discovery = bool(self.discoveries(a, c.brief))
            return (0 if discovery else 1, index - self.boost(a, c.brief) * self.size)

        return [s for _, s in sorted(indexed, key=priority)]
