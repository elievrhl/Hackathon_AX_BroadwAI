"""Bounded widening of retrieval, not relaxation of content/access safeguards."""

from broadwai.ranking import tokens


def exploration_limit(size, focused, allowed=True):
    # At most a quarter of the requested AND actually selected edition.
    return min(size // 4, focused // 3, max(0, size - focused)) if allowed else 0


def research_angles(plan, intent, missing_needs):
    known = {need["id"] for need in intent["needs"]}
    missing = {need["id"] for need in missing_needs}
    angles = [
        a.model_dump()
        for a in plan.search_angles
        if a.need_id in known and (a.scope != "adjacent" or intent.get("allow_adjacent", True))
    ]
    # Exhaust angles within the domain before crossing into adjacent subjects.
    angles.sort(key=lambda a: (a["scope"] == "adjacent", a["need_id"] not in missing))
    fallback = [
        {"need_id": n["id"], "query": n["query"], "scope": "direct", "connection": n["topic"]}
        for n in [*missing_needs, *intent["needs"]]
        if n.get("query")
    ]
    return (
        [a for a in angles if a["scope"] != "adjacent"]
        + fallback
        + [a for a in angles if a["scope"] == "adjacent"]
    )


def next_angle(angles, history, action, *, adjacent_allowed, french_only=False):
    """Rotate angles across tools; same wording with a new word is not a new attempt."""
    for angle in angles:
        if angle["scope"] == "adjacent" and not adjacent_allowed:
            continue
        query = angle["query"]
        if french_only and action != "search_catalog":
            query += " en français"
        words = set(tokens(query)) - {"français", "francais"}
        repeated = False
        for previous in history:
            prior = set(tokens(previous.get("query") or "")) - {"français", "francais"}
            if len(words & prior) / max(1, len(words | prior)) >= 0.8:
                repeated = True
                break
        if not repeated:
            return {**angle, "query": query[:300]}
    # An empty local catalogue does not prove the web has no articles on the subject.
    # Only reuse such a query after the alternative in-domain angles were attempted.
    if action != "search_catalog":
        local_only = [h for h in history if h["action"] == "search_catalog"]
        external = [h for h in history if h["action"] != "search_catalog"]
        if local_only:
            candidates = [a for a in angles if a["scope"] != "adjacent"]
            return next_angle(
                candidates, external, action, adjacent_allowed=False, french_only=french_only
            )
    return None
