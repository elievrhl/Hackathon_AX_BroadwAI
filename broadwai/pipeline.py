import asyncio
import json
from collections import Counter
from copy import deepcopy
from time import perf_counter
from urllib.parse import urlsplit

from broadwai.balance import interest_balance, interleave
from broadwai.config import Settings
from broadwai.discovery import is_feed_directory, validate_source
from broadwai.editorial import (
    compact_candidate,
    coverage,
    grounded,
    preview,
    preview_pool,
    reading_kind,
)
from broadwai.llm import BudgetExceeded, LanguageModel, ModelError, RunBudget
from broadwai.models import (
    Article,
    Candidate,
    Cover,
    CoverItem,
    CoverRequest,
    Decision,
    Selection,
    TraceEvent,
    utcnow,
)
from broadwai.network import RetrievalError, validate_destination
from broadwai.preferences import PreferencePolicy, direct_match, semantic
from broadwai.ranking import Ranked, diversify, eligible, rank, similarity, tokens
from broadwai.web_search import open_web_query


class CoverPipeline:
    """One instance per request: bounded observe / decide / act loop."""

    def __init__(self, store, collector, search, model: LanguageModel, settings: Settings):
        self.store = store
        self.collector = collector
        self.search = search
        self.model = model
        self.settings = settings
        self.budget = RunBudget(
            limits={
                "summary": settings.max_summary_calls,
                "plan": 1,
                "intent": 1,
                "preferences": 10,
                "screen": 4,
                "editor": settings.max_agent_steps,
                "search_catalog": 2,
                "search_web": settings.max_web_searches,
                "fetch": settings.max_fetches,
                "web_model": settings.max_web_searches,
                "discovered_article": settings.max_discovered_articles,
                "source_proposal": settings.max_source_proposals,
                "discovery_fetch": settings.max_discovered_articles,
                "source_fetch": settings.max_source_proposals * 5,
            },
            max_tokens=settings.max_token_budget,
            final_reserve=min(settings.final_token_reserve, settings.max_token_budget // 3),
        )
        self.candidates: dict[str, Candidate] = {}
        self.articles: dict[str, Article] = {}
        self.trace: list[TraceEvent] = []
        self.warnings: list[str] = []
        self.discovered: dict[str, Article] = {}
        self.plan = None
        self.picks = {}
        self.exploration_pool: dict[str, Ranked] = {}
        self.exploration_active = False
        self.failed_domains: Counter = Counter()
        self.prepared_ids: set[str] = set()
        self.rejected: dict[str, dict] = {}
        self.catalog_index: dict[str, Article] = {}
        self.intent = {"needs": [], "constraints": []}
        self.balance = None
        self.search_history: list[dict] = []
        self.force_finalize = False
        self.started = perf_counter()
        self.audit: dict = {"version": 1, "events": []}
        self.preference_policy = PreferencePolicy()

    def log(self, kind, **data):
        if kind == "candidate_skipped" and data.get("article_id"):
            id_ = data["article_id"]
            article = self.catalog_index.get(id_)
            self.rejected[id_] = {
                "article_id": id_,
                "reason": data.get("reason"),
                "title": article.title if article else None,
                "url": article.url if article else None,
            }
        self.audit["events"].append(
            {
                "sequence": len(self.audit["events"]) + 1,
                "kind": kind,
                "at": utcnow().isoformat(),
                "elapsed_ms": round((perf_counter() - self.started) * 1000),
                **deepcopy(data),
            }
        )

    async def _interpret(self, request):
        profile = request.profile
        self.balance = interest_balance(profile, request.size)
        needs = [
            {
                "topic": i.topic,
                "query": i.topic,
                "priority": "primary" if n == 0 else "secondary",
                "level": profile.level,
                "evidence": i.topic,
            }
            for n, i in enumerate(profile.interests[:8])
        ]
        constraints = []
        if profile.notes or profile.reading_memory.get("liked_articles_count"):
            try:
                provided_profile = profile.model_dump(exclude={"user_id", "seen_article_ids"})
                explicit_profile = profile.model_dump(
                    exclude={"user_id", "seen_article_ids", "reading_memory"}
                )
                interpreted = await self.model.interpret(
                    {"profile": provided_profile},
                    self.budget,
                )
                evidence_source = (
                    profile.notes
                    + "\n"
                    + "\n".join(i.topic for i in profile.interests)
                    + "\n"
                    + json.dumps(provided_profile, ensure_ascii=False)
                )
                valid_needs = [
                    n for n in interpreted.needs if grounded(n.evidence, evidence_source, minimum=2)
                ]
                valid_constraints = [
                    c
                    for c in interpreted.constraints
                    if grounded(
                        c.evidence, json.dumps(explicit_profile, ensure_ascii=False), minimum=2
                    )
                ]
                rejected_intent = [
                    n.model_dump()
                    for n in [*interpreted.needs, *interpreted.constraints]
                    if not grounded(n.evidence, evidence_source, minimum=2)
                ]
                if rejected_intent:
                    self.log("intent_items_rejected", items=rejected_intent)
                if not valid_needs:
                    raise ModelError("Aucun besoin avec citation du profil")
                if rejected_intent:
                    self.warnings.append(
                        "Interprétation partielle : éléments sans citation du profil écartés"
                    )
                needs = [n.model_dump() for n in valid_needs]
                for need in needs:
                    if not grounded(
                        need["evidence"],
                        json.dumps(explicit_profile, ensure_ascii=False),
                        minimum=2,
                    ):
                        need["priority"] = "secondary"
                constraints = [c.model_dump() for c in valid_constraints]
                # Explicit notes take precedence over broad UI categories, regardless
                # of a model accidentally copying their numeric interest weights.
                note_needs = {
                    n["topic"] for n in needs if grounded(n["evidence"], profile.notes, minimum=2)
                }
                if note_needs:
                    for need in needs:
                        need["priority"] = "primary" if need["topic"] in note_needs else "secondary"
            except (ModelError, BudgetExceeded) as exc:
                self.warnings.append(f"Interprétation du profil indisponible : {exc}")
                if profile.notes:
                    needs.insert(
                        0,
                        {
                            "topic": profile.notes[:150],
                            "query": profile.notes[:200],
                            "priority": "primary",
                            "level": profile.level,
                            "evidence": profile.notes[:300],
                        },
                    )
        # Interpreting notes or likes must never erase another explicit rubric.
        for interest in profile.interests:
            if not any(n["topic"].casefold() == interest.topic.casefold() for n in needs):
                needs.append(
                    {
                        "topic": interest.topic,
                        "query": interest.topic,
                        "priority": "secondary",
                        "level": profile.level,
                        "evidence": interest.topic,
                    }
                )
        self.intent = {
            "needs": [{"id": f"need-{n + 1}", **need} for n, need in enumerate(needs)],
            "constraints": constraints,
            "interest_balance": self.balance,
        }
        if self.preference_policy.rules:
            self.intent["reader_preferences"] = self.preference_policy.context()
            for rule in self.preference_policy.rules:
                if rule.action in {"diversify", "more"} and rule.target_kind in {
                    "topic",
                    "treatment",
                }:
                    self.intent["needs"].append(
                        {
                            "id": "preference-" + rule.id,
                            "topic": rule.target,
                            "query": rule.target,
                            "priority": "secondary",
                            "level": profile.level,
                            "evidence": rule.target,
                        }
                    )
        self.audit["editorial_intent"] = self.intent

    async def _assess_preferences(self):
        policy = self.preference_policy
        if not policy.rules:
            return
        pending = [c for c in self.candidates.values() if c.article_id not in policy.matches]
        rules = [r for r in policy.rules if semantic(r)]
        batch_size = min(8, max(1, 24 // max(1, len(rules))))
        for start in range(0, len(pending), batch_size):
            batch = pending[start : start + batch_size]
            for c in batch:
                policy.matches[c.article_id] = {}
            if rules:
                try:
                    result = await self.model.assess_preferences(
                        {
                            "preferences": [r.model_dump(mode="json") for r in rules],
                            "candidates": [
                                {
                                    "article_id": c.article_id,
                                    "title": c.title,
                                    "summary": c.brief.summary,
                                    "key_points": c.brief.key_points,
                                    "topics": c.brief.topics,
                                    "level": c.brief.level,
                                    "content_type": c.brief.content_type,
                                    "source": c.source,
                                }
                                for c in batch
                            ],
                        },
                        self.budget,
                    )
                    by_id = {c.article_id: c for c in batch}
                    allowed = {r.id for r in rules}
                    pairs = Counter((a.article_id, a.preference_id) for a in result.assessments)
                    for assessment in result.assessments:
                        c = by_id.get(assessment.article_id)
                        if not c or assessment.preference_id not in allowed:
                            continue
                        text = "\n".join(
                            [c.title, c.brief.summary, *c.brief.key_points, *c.brief.topics]
                        )
                        if pairs[c.article_id, assessment.preference_id] != 1:
                            continue
                        if assessment.match != "uncertain" and not grounded(
                            assessment.evidence, text
                        ):
                            continue
                        policy.matches[c.article_id][assessment.preference_id] = assessment.match
                    self.log(
                        "reader_preferences_assessed",
                        assessments=result.model_dump()["assessments"],
                    )
                except (ModelError, BudgetExceeded) as exc:
                    self.log("reader_preferences_failed", error=str(exc))
                    self.warnings.append(
                        "Certaines préférences n'ont pas pu être évaluées ; "
                        "les exclusions non vérifiables restent bloquantes."
                    )
            for c in batch:
                blocked = policy.blocked(self.articles[c.article_id], c.brief)
                if blocked:
                    self.log(
                        "candidate_skipped",
                        article_id=c.article_id,
                        reason="Exclusion explicite ou compatibilité incertaine",
                        preferences=blocked,
                    )
                    self.candidates.pop(c.article_id, None)
                    self.articles.pop(c.article_id, None)

    def _pick_error(self, pick, row, sections, strict=False):
        if pick.score < self.settings.min_editorial_score:
            return "Score éditorial insuffisant"
        if not pick.matches_profile:
            return "Sujet central hors profil"
        if sections and pick.section not in sections and not pick.exploration:
            return "Rubrique inconnue"
        if pick.exploration and not (pick.exploration_reason or "").strip():
            return "Lien d'exploration absent"
        if strict:
            if (
                self.balance
                and len(self.balance["interests"]) > 1
                and pick.interest_id
                not in {interest["id"] for interest in self.balance["interests"]}
            ):
                return "Rubrique générale du profil non identifiée (interest_id)"
            if pick.matched_need not in {n["id"] for n in self.intent["needs"]}:
                return "Besoin éditorial non identifié"
            a = row.article
            if not grounded(pick.evidence, a.title + "\n" + (a.excerpt or a.text)[:320]):
                return "Lien au besoin sans preuve dans le titre ou l'extrait"
            if not pick.temporal_kind:
                return "Temporalité non évaluée"
        return None

    async def _prepare(self, ranked: Ranked, request: CoverRequest, seen: set[str]) -> bool:
        article = ranked.article
        self.catalog_index[article.id] = article
        pick = self.picks.get(article.id)
        self.prepared_ids.add(article.id)
        if self._dated_out(
            article,
            allow_evergreen=bool(pick and pick.evergreen),
            kind=pick.temporal_kind if pick else None,
        ):
            # A title/excerpt classification is provisional. When full text is already
            # available, let the grounded brief settle the temporal kind. Final date
            # and validity checks below still reject stale news and uncertain content.
            if article.extraction_status == "extracted" and article.text.strip():
                self.log("temporal_review_requested", article_id=article.id)
            else:
                self.log(
                    "candidate_skipped",
                    article_id=article.id,
                    reason="Date incompatible avec une actualité ou une lecture de fond validée",
                )
                return False
        self.log(
            "candidate_prepare",
            article_id=article.id,
            title=article.title,
            url=article.url,
            score=ranked.score,
            score_details=ranked.score_details,
        )
        if article.id in self.candidates or len(self.candidates) >= 40:
            self.log("candidate_skipped", article_id=article.id, reason="Déjà présent ou limite 40")
            return False
        brief = self.store.get_brief(article, self.model.summary_version)
        if brief:
            self.budget.cache_hits += 1
            self.log(
                "summary_cache_hit",
                article_id=article.id,
                version=self.model.summary_version,
                content_hash=article.content_hash,
                brief=brief.model_dump(),
            )
        else:
            if article.extraction_status != "extracted":
                try:
                    if self.failed_domains[article.source] >= 2:
                        raise RetrievalError("Domaine déjà inaccessible pendant cette génération")
                    self.budget.take("fetch")
                    self.log("extract_requested", article_id=article.id, url=article.url)
                    article = await self.collector.extract(article)
                    self.log(
                        "extract_completed", article_id=article.id, characters=len(article.text)
                    )
                except (RetrievalError, BudgetExceeded) as exc:
                    if isinstance(exc, RetrievalError):
                        self.failed_domains[article.source] += 1
                    self.log("extract_failed", article_id=article.id, error=str(exc))
                    self.warnings.append(f"{article.id}: {exc}")
            if len(article.text or article.excerpt) < 80:
                self.log("candidate_skipped", article_id=article.id, reason="Contenu insuffisant")
                self.warnings.append(f"{article.id}: contenu insuffisant pour une fiche fiable")
                return False
            brief = self.store.get_brief(article, self.model.summary_version)
            if brief:
                self.budget.cache_hits += 1
                self.log(
                    "summary_cache_hit",
                    article_id=article.id,
                    version=self.model.summary_version,
                    content_hash=article.content_hash,
                    brief=brief.model_dump(),
                )
            else:
                try:
                    self.log(
                        "summary_requested",
                        article_id=article.id,
                        title=article.title,
                        version=self.model.summary_version,
                        content_hash=article.content_hash,
                        extraction_status=article.extraction_status,
                        input_chars=min(
                            len(article.text or article.excerpt), self.settings.max_article_chars
                        ),
                        truncated=len(article.text or article.excerpt)
                        > self.settings.max_article_chars,
                    )
                    brief = await self.model.summarize(article, self.budget)
                except (ModelError, BudgetExceeded) as exc:
                    self.log("summary_failed", article_id=article.id, error=str(exc))
                    self.warnings.append(f"{article.id}: {exc}")
                    return False
                caveats = []
                if article.extraction_status == "excerpt":
                    caveats.append("Fiche fondée uniquement sur un extrait, pas le texte intégral.")
                if len(article.text or article.excerpt) > self.settings.max_article_chars:
                    caveats.append("Texte tronqué avant résumé.")
                caveats.extend(brief.caveats)
                brief = brief.model_copy(update={"caveats": list(dict.fromkeys(caveats))[:5]})
                self.store.put_brief(article, self.model.summary_version, brief)
                self.log("summary_completed", article_id=article.id, brief=brief.model_dump())
        self.log(
            "cited_sources",
            article_id=article.id,
            title=article.title,
            url=article.url,
            sources=[source.model_dump() for source in brief.cited_sources],
        )
        checked_article = article.model_copy(
            update={"language": article.language or brief.language}
        )
        if any(
            r.action == "exclude" and direct_match(r, article, brief) is True
            for r in self.preference_policy.rules
        ):
            self.log(
                "candidate_skipped", article_id=article.id, reason="Exclusion explicite du lecteur"
            )
            return False
        if not eligible(checked_article, request.profile, seen):
            self.log(
                "candidate_skipped", article_id=article.id, reason="Exclu après lecture/langue"
            )
            return False
        validity = brief.validity
        if validity and (
            validity.status in {"outdated", "uncertain"}
            or (validity.kind == "evergreen" and validity.status != "durable")
            or not grounded(
                validity.evidence,
                (article.text or article.excerpt)[: self.settings.max_article_chars],
            )
        ):
            self.log(
                "candidate_skipped",
                article_id=article.id,
                reason="Validité du contenu insuffisante : " + validity.reason,
            )
            return False
        if self._dated_out(
            article,
            allow_evergreen=bool(pick and pick.evergreen and brief.content_type != "news"),
            kind=validity.kind if validity else None,
        ):
            self.log(
                "candidate_skipped",
                article_id=article.id,
                reason="Actualité périmée ou non datée"
                if brief.content_type == "news"
                else "Date incompatible avec la lecture de fond",
            )
            return False
        self.articles[article.id] = article
        self.candidates[article.id] = Candidate(
            article_id=article.id,
            title=article.title,
            url=article.url,
            source=article.source,
            published_at=article.published_at,
            extraction_status=article.extraction_status,
            score=round(ranked.score, 5),
            matched_interests=ranked.matched_interests,
            brief=brief,
        )
        self.log("candidate_ready", article_id=article.id)
        return True

    def _dated_out(self, article, *, allow_evergreen=False, kind=None):
        durable = kind == "evergreen" if kind else allow_evergreen
        if article.published_at:
            age = (utcnow() - article.published_at).total_seconds() / 86400
            limit = (
                self.settings.max_research_age_days
                if kind == "research"
                else self.settings.max_article_age_days
            )
            return age < -1 or (not durable and age > limit)
        return not durable

    def _is_exploration(self, article_id):
        pick = self.picks.get(article_id)
        return bool(pick and pick.exploration)

    def _available_selections(self, *, focused_only=False):
        return [
            Selection(
                article_id=id_,
                section=self.picks[id_].section if id_ in self.picks else "À découvrir",
                reason=self.picks[id_].reason if id_ in self.picks else "Selon vos intérêts",
            )
            for id_ in self.candidates
            if not focused_only or not self._is_exploration(id_)
        ]

    def _focused_capacity(self, request):
        selected, _ = self._allocate(self._available_selections(focused_only=True), request)
        return len(selected)

    async def _complete_with_exploration(self, request, seen):
        if self.force_finalize or not self.budget.can_explore:
            return
        missing = request.size - self._focused_capacity(request)
        if missing <= 0:
            self.exploration_active = False
            return
        # Give direct discovery its first pass before opening adjacent themes.
        if (
            request.discover_web
            and self.search.enabled
            and self.settings.max_web_searches
            and not self.budget.counts["search_web"]
        ):
            return
        if not self.exploration_active:
            self.log("exploration_opened", missing=missing)
        self.exploration_active = True
        # Fill only usable slots, accounting for shared sources and near duplicates.
        for id_, row in self.exploration_pool.items():
            selected, _ = self._allocate(self._available_selections(), request)
            if len(selected) >= request.size:
                break
            if id_ not in self.prepared_ids:
                await self._prepare(row, request, seen)
                await self._assess_preferences()

    async def _add_candidates(
        self,
        ranked: list[Ranked],
        request: CoverRequest,
        seen: set[str],
        limit: int,
        editorial_order: bool = False,
    ) -> list[str]:
        added = []
        # Diversify before spending summary tokens; permit alternatives from a given source.
        shortlist = (
            ranked if editorial_order else diversify(ranked, limit, max(3, request.max_per_source))
        )
        if self.balance and len(self.balance["interests"]) > 1:
            shortlist = interleave(shortlist, lambda row: self._interest(row.article.id))
        self.log(
            "shortlist",
            ranked_count=len(ranked),
            limit=limit,
            source_cap=max(3, request.max_per_source),
            shortlisted_ids=[r.article.id for r in shortlist],
            ranked=[
                {
                    "article_id": r.article.id,
                    "title": r.article.title,
                    "url": r.article.url,
                    "source": r.article.source,
                    "score": r.score,
                    "score_details": r.score_details,
                    "matched_interests": r.matched_interests,
                }
                for r in ranked[:100]
            ],
            ranked_display_limit=100,
        )
        cursor = 0
        while cursor < len(shortlist) and len(added) < limit:
            if not self.budget.can_explore:
                self.force_finalize = True
                break
            batch = shortlist[cursor : cursor + min(3, limit - len(added))]
            cursor += len(batch)
            results = await asyncio.gather(*(self._prepare(r, request, seen) for r in batch))
            added.extend(
                r.article.id for r, accepted in zip(batch, results, strict=True) if accepted
            )
        await self._assess_preferences()
        return [id_ for id_ in added if id_ in self.candidates]

    def _validate(self, selections: list[Selection], request: CoverRequest) -> list[str]:
        errors = []
        if (
            request.discover_web
            and self.search.enabled
            and not self.budget.counts["search_web"]
            and not self.force_finalize
        ):
            errors.append("Effectue search_web : une découverte web a été demandée")
        if not selections:
            return ["La sélection ne doit pas être vide"]
        if len(selections) > request.size:
            errors.append("Trop d'articles")
        can_research = (
            not self.force_finalize
            and self.budget.can_explore
            and self.budget.counts["editor"] < self.settings.max_agent_steps
            and self.budget.counts["summary"] < self.settings.max_summary_calls
            and (
                (
                    self.search.enabled
                    and self.budget.counts["search_web"] < self.settings.max_web_searches
                )
                or self.budget.counts["search_catalog"] < 1
            )
        )
        if len(selections) < request.size and can_research:
            errors.append(
                f"Seulement {len(selections)}/{request.size} articles : "
                "cherche des remplacements pertinents ou des thèmes connexes en Exploration "
                "avant de finaliser"
            )
        if self.balance and len(self.balance["interests"]) > 1:
            counts = Counter(self._interest(s.article_id) for s in selections)
            available = Counter(self._interest(id_) for id_ in self.candidates)
            for interest in self.balance["interests"]:
                target = self.balance["minimum_per_interest"]
                if counts[interest["id"]] < target and (
                    can_research or available[interest["id"]] > counts[interest["id"]]
                ):
                    errors.append(
                        f"Diversité : réserver {target} articles à {interest['topic']}. "
                        "Cherche cette rubrique manquante avant de renforcer les sujets couverts."
                    )
        sections = Counter(s.section for s in selections if not self._is_exploration(s.article_id))
        focused_count = sum(sections.values())
        if self.plan and set(sections) - set(self.plan.sections):
            errors.append("Utilise les rubriques prévues dans editorial_plan")
        if request.size >= 15 and len(selections) == request.size:
            if focused_count >= 15 and (
                not 3 <= len(sections) <= 5 or min(sections.values(), default=0) < 2
            ):
                errors.append(
                    "Une une complète exige 3 à 5 rubriques avec au moins 2 articles chacune"
                )
        if self.plan and self.plan.contract_version >= 2:
            needs = {n["id"] for n in self.intent["needs"]}
            roles = Counter(s.role for s in selections if not self._is_exploration(s.article_id))
            if focused_count and (
                roles["lead"] != 1 or roles["secondary"] > 2 or roles["brief"] > 3
            ):
                errors.append(
                    "Choisir un sujet principal, au plus deux secondaires et trois brèves"
                )
            stories = {}
            for s in selections:
                c = self.candidates.get(s.article_id)
                if not c:
                    continue
                if s.matched_need not in needs:
                    errors.append(f"{s.article_id}: besoin non justifié après lecture")
                if not grounded(
                    s.evidence,
                    c.title
                    + "\n"
                    + c.brief.summary
                    + "\n"
                    + "\n".join(c.brief.key_points)
                    + "\n"
                    + (c.brief.validity.evidence if c.brief.validity else ""),
                ):
                    errors.append(f"{s.article_id}: preuve absente de la fiche")
                if not s.headline or not s.role or not s.story_key:
                    errors.append(f"{s.article_id}: titre français, rôle et sujet requis")
                if s.story_key:
                    key = " ".join(tokens(s.story_key))
                    if key in stories and (
                        not s.distinct_angle or s.distinct_angle == stories[key]
                    ):
                        errors.append(f"{s.article_id}: reprise du même sujet sans apport distinct")
                    stories[key] = s.distinct_angle
        ids = [s.article_id for s in selections]
        if len(ids) != len(set(ids)):
            errors.append("Identifiants dupliqués")
        unknown = set(ids) - self.candidates.keys()
        if unknown:
            errors.append("Identifiants non disponibles : " + ", ".join(sorted(unknown)))
        articles = [self.articles[id_] for id_ in ids if id_ in self.articles]
        counts = Counter(a.source for a in articles)
        if any(count > request.max_per_source for count in counts.values()):
            errors.append(
                f"Quota par source dépassé : maximum {request.max_per_source}. "
                + ", ".join(f"{domain}: {count}" for domain, count in counts.items())
            )
        if any(similarity(a, b) >= 0.8 for i, a in enumerate(articles) for b in articles[i + 1 :]):
            errors.append("Articles quasi identiques dans la sélection")
        if can_research:
            covered_requests = {
                rule.id
                for rule in self.preference_policy.rules
                if rule.action == "diversify"
                and any(
                    self.preference_policy.match(
                        rule, self.articles[s.article_id], self.candidates[s.article_id].brief
                    )
                    == "yes"
                    for s in selections
                    if s.article_id in self.candidates
                )
            }
            for rule in self.preference_policy.rules:
                if len(covered_requests) >= self.preference_policy.discovery_limit:
                    break
                if rule.action != "diversify":
                    continue
                matching = {
                    id_
                    for id_, c in self.candidates.items()
                    if self.preference_policy.match(rule, self.articles[id_], c.brief) == "yes"
                }
                if not (matching & set(ids)):
                    errors.append(
                        f"Demande de diversification à couvrir si possible : {rule.target}"
                    )
        return errors

    def _interest(self, article_id):
        pick = self.picks.get(article_id)
        return pick.interest_id if pick else None

    def _allocate(self, selections: list[Selection], request: CoverRequest):
        """Apply mechanical quotas once; the model supplies editorial order and judgments."""
        has_exploration = any(self._is_exploration(s.article_id) for s in selections)
        exploration_limit = (
            max(0, request.size - self._focused_capacity(request)) if has_exploration else 0
        )
        kept, removed = [], []
        counts = Counter()
        ids = set()
        exploration_count = 0
        discovery_count = 0
        reduced_counts = Counter()
        interest_counts = Counter()
        balanced = self.balance and len(self.balance["interests"]) > 1
        ordered = self.preference_policy.order(selections, self.articles, self.candidates)
        ordered = sorted(ordered, key=lambda s: self._is_exploration(s.article_id))
        if balanced:
            ordered = interleave(
                [s for s in ordered if not self._is_exploration(s.article_id)],
                lambda s: self._interest(s.article_id),
            ) + [s for s in ordered if self._is_exploration(s.article_id)]
        for s in ordered:
            article = self.articles.get(s.article_id)
            candidate = self.candidates.get(s.article_id)
            discoveries = (
                self.preference_policy.discoveries(article, candidate.brief)
                if article and candidate
                else []
            )
            # Even an unavailable semantic check cannot let a whole edition pivot to
            # a newly requested need: also count the editor's attributed need.
            pick = self.picks.get(s.article_id)
            if pick:
                discoveries.extend(
                    r.id
                    for r in self.preference_policy.rules
                    if r.action == "diversify" and pick.matched_need == "preference-" + r.id
                )
            reduced = (
                self.preference_policy.reduced(article, candidate.brief)
                if article and candidate
                else []
            )
            exploration = self._is_exploration(s.article_id)
            reason = None
            if article is None:
                reason = "Identifiant inconnu"
            elif s.article_id in ids:
                reason = "Doublon"
            elif candidate and self.preference_policy.blocked(article, candidate.brief):
                reason = "Exclusion explicite du lecteur"
            elif discoveries and discovery_count >= self.preference_policy.discovery_limit:
                reason = "Quota de diversification demandé par le lecteur"
            elif any(reduced_counts[id_] >= self.preference_policy.less_limit for id_ in reduced):
                reason = "Présence réduite à la demande du lecteur"
            elif exploration and exploration_count >= exploration_limit:
                reason = "Exploration réservée aux places manquantes"
            elif counts[article.source] >= request.max_per_source:
                reason = "Quota de source"
            elif (
                balanced
                and self._interest(s.article_id)
                and (
                    interest_counts[self._interest(s.article_id)]
                    >= self.balance["max_per_interest"]
                )
            ):
                reason = "Quota de rubrique générale : préserver les autres intérêts"
            elif len(kept) >= request.size:
                reason = "Taille demandée atteinte"
            elif any(similarity(article, self.articles[k.article_id]) >= 0.8 for k in kept):
                reason = "Article quasi identique"
            if reason:
                removed.append({"article_id": s.article_id, "reason": reason})
                continue
            ids.add(s.article_id)
            discovery_count += bool(discoveries)
            reduced_counts.update(reduced)
            counts[article.source] += 1
            interest_counts[self._interest(s.article_id)] += 1
            if exploration:
                exploration_count += 1
                s = s.model_copy(update={"section": "Exploration"})
            kept.append(s)
        # Layout overflow must not discard an otherwise valid editorial selection.
        focused = [s for s in kept if not self._is_exploration(s.article_id)]
        if focused and all(s.role for s in focused):
            lead_id = next(
                (s.article_id for s in focused if s.role == "lead"), focused[0].article_id
            )
            role_counts = Counter()
            adjusted = []
            for index, selection in enumerate(kept):
                role = selection.role
                if selection.article_id == lead_id:
                    role = "lead"
                elif self._is_exploration(selection.article_id) or role == "lead":
                    role = "reading"
                elif (
                    role in {"secondary", "brief"}
                    and role_counts[role] >= {"secondary": 2, "brief": 3}[role]
                ):
                    role = "reading"
                role_counts[role] += 1
                if role != selection.role:
                    kept[index] = selection.model_copy(update={"role": role})
                    adjusted.append(
                        {"article_id": selection.article_id, "from": selection.role, "to": role}
                    )
            if adjusted:
                self.log("layout_roles_adjusted", changes=adjusted)
        return kept, removed

    def _finish(
        self, selections: list[Selection], request: CoverRequest, title: str, fallback: bool = False
    ) -> Cover:
        if self.preference_policy.rules:
            self.audit["reader_preferences"] = self.preference_policy.context()
            self.audit["preference_matches"] = self.preference_policy.matches
            impact = []
            for rule in self.preference_policy.rules:
                matching = [
                    s.article_id
                    for s in selections
                    if self.preference_policy.match(
                        rule, self.articles[s.article_id], self.candidates[s.article_id].brief
                    )
                    == "yes"
                ]
                impact.append(
                    {
                        "id": rule.id,
                        "target": rule.target,
                        "target_kind": rule.target_kind,
                        "explanation": rule.explanation,
                        "action": rule.action,
                        "selected_count": len(matching),
                        "article_ids": matching,
                    }
                )
                if rule.action in {"diversify", "more"} and not matching:
                    self.warnings.append(f"Demande non couverte dans cette édition : {rule.target}")
            self.audit["preference_impact"] = impact
        items = []
        for selection in selections:
            candidate = self.candidates[selection.article_id]
            items.append(
                CoverItem(
                    **candidate.model_dump(exclude={"score", "matched_interests"}),
                    section=selection.section,
                    reason=selection.reason,
                    headline=selection.headline,
                    role=selection.role,
                    reading_time_minutes=self.articles[selection.article_id].reading_time_minutes,
                    image=self.articles[selection.article_id].image,
                    image_checked=self.articles[selection.article_id].image_checked_at is not None,
                    selection_kind=(
                        "exploration" if self._is_exploration(selection.article_id) else "focused"
                    ),
                    exploration_reason=(
                        self.picks[selection.article_id].exploration_reason
                        if self._is_exploration(selection.article_id)
                        else None
                    ),
                    reading_kind=reading_kind(candidate, self.picks.get(selection.article_id)),
                )
            )
        status = "fallback" if fallback else "complete" if len(items) == request.size else "partial"
        if self.balance and len(self.balance["interests"]) > 1:
            counts = Counter(self._interest(s.article_id) for s in selections)
            missing = [
                i["topic"]
                for i in self.balance["interests"]
                if counts[i["id"]] < self.balance["minimum_per_interest"]
            ]
            self.audit["interest_balance"] = {
                **self.balance,
                "selected": dict(counts),
                "underrepresented": missing,
            }
            if missing:
                self.warnings.append("Rubriques insuffisamment couvertes : " + "; ".join(missing))
                if status == "complete":
                    status = "partial"
        self.log("cover_completed", status=status, selected_ids=[s.article_id for s in selections])
        self.audit["candidates"] = [c.model_dump(mode="json") for c in self.candidates.values()]
        self.audit["duration_ms"] = round((perf_counter() - self.started) * 1000)
        self.audit["search_history"] = self.search_history
        self.audit["rejected"] = list(self.rejected.values())
        self.audit["uncovered_needs"] = [
            n
            for n in self.intent["needs"]
            if n["id"]
            not in {
                s.matched_need or self.picks[s.article_id].matched_need
                for s in selections
                if s.article_id in self.picks
            }
        ]
        if request.discover_sources and not self.budget.counts["source_proposal"]:
            self.warnings.append("Proposition de source différée : priorité à la couverture")
        if len(items) < request.size:
            self.warnings.append(
                f"Seulement {len(items)} articles retenus sur {request.size} demandés"
            )
        cover = Cover(
            user_id=request.profile.user_id,
            title=title,
            status=status,
            items=items,
            trace=self.trace,
            warnings=list(dict.fromkeys(self.warnings)),
            usage=self.budget.report(),
            diagnostics=self.audit,
        )
        self.store.put_cover(cover, preferences=self.preference_policy.rules)
        return cover

    async def run(self, request: CoverRequest) -> Cover:
        rules = self.store.list_preferences(request.profile.user_id, active_only=True)
        self.preference_policy = PreferencePolicy(rules, request.size)
        # Load a snapshot once. A change made while generating applies to the next run.
        source_exclusions = [
            r.target
            for r in rules
            if r.action == "exclude" and r.target_kind == "source" and not r.explanation
        ]
        if source_exclusions:
            request = request.model_copy(
                update={
                    "profile": request.profile.model_copy(
                        update={
                            "excluded_sources": list(
                                dict.fromkeys(
                                    [*request.profile.excluded_sources, *source_exclusions]
                                )
                            ),
                        }
                    )
                }
            )
        self.audit["request"] = request.model_dump(mode="json")
        self.audit["settings"] = {
            key: getattr(self.settings, key)
            for key in (
                "shortlist_size",
                "max_agent_steps",
                "max_summary_calls",
                "max_fetches",
                "max_web_searches",
                "max_discovered_articles",
                "max_source_proposals",
                "max_article_chars",
                "max_catalog_articles",
                "max_token_budget",
                "editorial_pool_size",
                "min_editorial_score",
                "max_article_age_days",
                "max_research_age_days",
                "final_token_reserve",
            )
        }
        await self._interpret(request)
        seen = self.store.consumed_ids(request.profile.user_id)
        catalog = self.store.articles(self.settings.max_catalog_articles)
        self.catalog_index.update({a.id: a for a in catalog})
        ranked = rank(
            [a for a in catalog if not self._dated_out(a, allow_evergreen=True)],
            request.profile,
            seen,
            needs=self.intent["needs"],
        )
        self.log(
            "catalog_ranked",
            catalog_count=len(catalog),
            eligible_count=len(ranked),
            consumed_count=len(seen),
            algorithm="BM25 + fraîcheur, puis diversification",
        )
        pool = preview_pool(
            ranked, self.settings.editorial_pool_size, [i.topic for i in request.profile.interests]
        )
        # Keep enough vetted alternatives to replace articles rejected after full-text
        # extraction.  A target-sized shortlist made the 18-item reader routinely
        # exhaust its preparation budget after normal quality rejections.
        selection_limit = min(40, max(request.size * 2, self.settings.shortlist_size))
        previews = [preview(r) for r in pool]
        self.log("editorial_preview", candidates=previews, selection_limit=selection_limit)
        try:
            self.plan = await self.model.plan(
                {
                    "profile": request.profile.model_dump(exclude={"seen_article_ids"}),
                    "size": request.size,
                    "max_per_source": request.max_per_source,
                    "selection_limit": selection_limit,
                    "candidates": previews,
                    "today": utcnow().date().isoformat(),
                    "max_article_age_days": self.settings.max_article_age_days,
                    "max_research_age_days": self.settings.max_research_age_days,
                    "editorial_intent": self.intent,
                    "min_editorial_score": self.settings.min_editorial_score,
                    "exploration_allowed": True,
                },
                self.budget,
            )
            self.audit["editorial_plan"] = self.plan.model_dump()
            self.log("editorial_plan", plan=self.plan.model_dump())
            by_id = {r.article.id: r for r in pool}
            selected = []
            for pick in self.plan.picks:
                if pick.article_id in by_id and pick.article_id not in self.picks:
                    error = self._pick_error(
                        pick,
                        by_id[pick.article_id],
                        self.plan.sections,
                        self.plan.contract_version >= 2,
                    )
                    if error:
                        self.log("candidate_skipped", article_id=pick.article_id, reason=error)
                        continue
                    self.picks[pick.article_id] = pick
                    if pick.exploration:
                        self.exploration_pool[pick.article_id] = by_id[pick.article_id]
                    else:
                        selected.append(by_id[pick.article_id])
            await self._add_candidates(
                selected, request, seen, selection_limit, editorial_order=True
            )
        except (ModelError, BudgetExceeded) as exc:
            self.log("editorial_plan_failed", error=str(exc))
            self.warnings.append(f"Présélection éditoriale indisponible : {exc}")
        observations: list[dict] = []
        attempted: set[tuple] = set()
        for step in range(1, self.settings.max_agent_steps + 1):
            self.force_finalize = (
                self.force_finalize
                or not self.budget.can_explore
                or step == self.settings.max_agent_steps
            )
            await self._complete_with_exploration(request, seen)
            state = {
                "profile": request.profile.model_dump(exclude={"seen_article_ids"}),
                "size": request.size,
                "discover_web": request.discover_web,
                "discover_sources": request.discover_sources,
                "max_per_source": request.max_per_source,
                "exploration_allowed": self.exploration_active,
                "focused_capacity": self._focused_capacity(request),
                "max_article_age_days": self.settings.max_article_age_days,
                "max_research_age_days": self.settings.max_research_age_days,
                "editorial_intent": self.intent,
                "min_editorial_score": self.settings.min_editorial_score,
                "force_finalize": self.force_finalize,
                "budget_remaining_tokens": self.budget.remaining_tokens,
                "search_history": self.search_history,
                "rejected": list(self.rejected.values())[-30:],
                "preference_matches": self.preference_policy.matches,
                "candidates": [
                    compact_candidate(c, self.picks.get(c.article_id))
                    for c in self.candidates.values()
                ],
                "observations": observations[-2:],
                "editorial_plan": self.plan.model_dump(exclude={"picks"}) if self.plan else None,
                "coverage": coverage(
                    self.candidates,
                    self.picks,
                    self.plan.sections if self.plan else [],
                    request.size,
                    request.max_per_source,
                ),
                "failed_domains": [s for s, n in self.failed_domains.items() if n >= 2],
                "remaining_summaries": self.settings.max_summary_calls
                - self.budget.counts["summary"],
                "remaining_catalog_searches": 2 - self.budget.counts["search_catalog"],
                "remaining_steps": self.settings.max_agent_steps - step + 1,
                "web_search_enabled": self.search.enabled,
                "remaining_web_searches": self.settings.max_web_searches
                - self.budget.counts["search_web"],
                "discovered_links": [
                    {"url": a.url, "title": a.title} for a in self.discovered.values()
                ],
                "remaining_source_proposals": self.settings.max_source_proposals
                - self.budget.counts["source_proposal"],
                "remaining_article_imports": self.settings.max_discovered_articles
                - self.budget.counts["discovered_article"],
            }
            try:
                self.log(
                    "editor_requested",
                    step=step,
                    candidate_ids=list(self.candidates),
                    observations=observations[-2:],
                    coverage=state["coverage"],
                )
                try:
                    decision = await self.model.decide(state, self.budget)
                except BudgetExceeded:
                    if self.force_finalize or not self.candidates:
                        raise
                    self.force_finalize = True
                    state["force_finalize"] = True
                    self.log("final_reserve_used", step=step)
                    decision = await self.model.decide(state, self.budget)
                self.log("editor_decision", step=step, decision=decision.model_dump(mode="json"))
            except (ModelError, BudgetExceeded) as exc:
                self.log("editor_failed", step=step, error=str(exc))
                self.warnings.append(str(exc))
                self.trace.append(
                    TraceEvent(
                        step=step,
                        action="model_error",
                        justification="Impossible de poursuivre",
                        outcome={"error": str(exc)},
                    )
                )
                break
            if decision.action == "finalize":
                decision.selections, removed = self._allocate(decision.selections, request)
                if removed:
                    self.log(
                        "selection_allocated",
                        step=step,
                        removed=removed,
                        kept_ids=[s.article_id for s in decision.selections],
                    )
                errors = self._validate(decision.selections, request)
                if not decision.title or len(decision.title) > 200:
                    errors.append("Titre requis, 200 caractères maximum")
                outcome = {"errors": errors} if errors else {"selected": len(decision.selections)}
                if removed:
                    outcome["removed_by_constraints"] = removed
                self.log("validation", step=step, **outcome)
                self.trace.append(
                    TraceEvent(
                        step=step,
                        action=decision.action,
                        justification=decision.justification,
                        outcome=outcome,
                    )
                )
                if not errors:
                    return self._finish(decision.selections, request, decision.title)
            else:
                key = (
                    decision.action,
                    tuple(sorted(set(tokens(decision.query or "")))),
                    decision.article_id,
                    decision.source_url,
                )
                if key in attempted:
                    outcome = {"error": "Action déjà tentée : choisis une autre action"}
                else:
                    attempted.add(key)
                    try:
                        self.log(
                            "tool_requested",
                            step=step,
                            action=decision.action,
                            query=decision.query,
                            article_id=decision.article_id,
                            source_url=decision.source_url,
                        )
                        outcome = await self._act(decision, request, seen)
                    except (RetrievalError, BudgetExceeded, ValueError) as exc:
                        outcome = {"error": str(exc)}
                # Keep audit useful without storing full article text in the trace.
                audit = {k: v for k, v in outcome.items() if k != "text"}
                self.log("tool_result", step=step, action=decision.action, outcome=audit)
                self.trace.append(
                    TraceEvent(
                        step=step,
                        action=decision.action,
                        justification=decision.justification,
                        outcome=audit,
                    )
                )
                if decision.action in {"search_web", "search_catalog"}:
                    self.search_history.append(
                        {
                            "action": decision.action,
                            "query": decision.query,
                            "added": len(outcome.get("added_ids", [])),
                            "rejections": outcome.get("rejections", []),
                            "error": outcome.get("error"),
                        }
                    )
            observations.append({"action": decision.action, **outcome})

        self.warnings.append(
            "Sélection de secours déterministe : l'agent n'a pas validé de couverture"
        )
        await self._complete_with_exploration(request, seen)
        primary_needs = {n["id"] for n in self.intent["needs"] if n["priority"] == "primary"}
        fallback = sorted(
            self.candidates.values(),
            key=lambda c: (
                self._is_exploration(c.article_id),
                not (
                    c.article_id in self.picks
                    and self.picks[c.article_id].matched_need in primary_needs
                ),
                -self.picks[c.article_id].score if c.article_id in self.picks else -c.score,
            ),
        )
        selections = [
            Selection(
                article_id=r.article_id,
                section="À découvrir",
                reason="Sélection de secours selon vos intérêts et la diversité.",
                headline=r.brief.headline,
                role="reading",
            )
            for r in fallback
        ]
        for s in selections:
            if s.article_id in self.picks:
                s.section = self.picks[s.article_id].section
                s.reason = self.picks[s.article_id].reason
        selections, _ = self._allocate(selections, request)
        if (
            not selections
            and self.budget.model_calls
            and all(call["status"] == "error" for call in self.budget.model_calls)
        ):
            raise ModelError("Aucun appel modèle n'a abouti ; aucune couverture enregistrée")
        for index, selection in enumerate(selections):
            if not self._is_exploration(selection.article_id):
                selection.role = "lead" if index == 0 else "secondary" if index < 3 else "reading"
        return self._finish(selections, request, "Votre sélection", fallback=True)

    async def _act(self, decision: Decision, request: CoverRequest, seen: set[str]) -> dict:
        if self.force_finalize:
            raise ValueError("Budget réservé à la composition : finalise maintenant")
        if decision.action == "propose_source":
            available, _ = self._allocate(self._available_selections(), request)
            if self.plan and len(available) < request.size:
                raise ValueError("Proposition de source différée : couverture encore incomplète")
            self.budget.take("source_proposal")
            url = validate_destination(decision.source_url or "")
            known = [a.url for a in self.discovered.values()] + [
                a.url for a in self.articles.values()
            ]
            origins = {f"{urlsplit(u).scheme}://{urlsplit(u).netloc}/" for u in known}
            if url not in known and url not in origins:
                raise ValueError("La source doit provenir d'un lien découvert ou d'un candidat")
            kind, source_url = await validate_source(self.collector.fetcher, url, self.budget)
            proposal = self.store.propose_source(
                source_url,
                (decision.title or urlsplit(source_url).hostname)[:150],
                decision.justification,
                url,
                kind=kind,
            )
            return {
                k: proposal[k]
                for k in ("id", "url", "kind", "status", "source_id")
                if k in proposal
            }

        if decision.action in {"search_catalog", "search_web"}:
            if not decision.query or not 2 <= len(decision.query) <= 300:
                raise ValueError("La requête doit contenir entre 2 et 300 caractères")
            words = set(tokens(decision.query))
            for previous in self.search_history:
                prior = set(tokens(previous.get("query") or ""))
                if (
                    previous["action"] == decision.action
                    and not previous["added"]
                    and len(words & prior) / max(1, len(words | prior)) >= 0.8
                ):
                    raise ValueError("Recherche déjà infructueuse : cible un autre besoin ou angle")
            rejected_before = set(self.rejected)
            if decision.action == "search_web":
                if not self.search.enabled:
                    raise RetrievalError("Recherche web non configurée")
                self.budget.take("search_web")
                avoid = [s for s, n in self.failed_domains.items() if n >= 2]
                requested_query = decision.query
                query = open_web_query(requested_query) + (
                    " ; éviter les sites " + ", ".join(avoid) if avoid else ""
                )
                strategy = "independent" if self.budget.counts["search_web"] > 1 else "open_web"
                result_limit = min(12, max(5, (request.size - len(self.candidates)) * 2 + 2))
                search_context = {
                    "profile": request.profile.model_dump(exclude={"user_id", "seen_article_ids"}),
                    "strategy": strategy,
                    "avoid_domains": avoid,
                    "max_article_age_days": self.settings.max_article_age_days,
                    "max_research_age_days": self.settings.max_research_age_days,
                    "editorial_intent": self.intent,
                    "search_history": self.search_history,
                    "rejected": list(self.rejected.values())[-30:],
                    "exploration_allowed": self.exploration_active,
                }
                found = await self.search.search(
                    query,
                    self.budget,
                    limit=result_limit,
                    context=search_context,
                )
                self.log(
                    "web_discovery",
                    requested_query=requested_query,
                    query=query,
                    strategy=strategy,
                    returned_count=len(found),
                )
                self.discovered.update({a.id: a for a in found})
                self.catalog_index.update({a.id: a for a in found})
                articles = []
                import_errors = []
                for candidate in found:
                    if candidate.id in self.rejected or candidate.id in self.prepared_ids:
                        continue
                    if is_feed_directory(candidate):
                        self.log(
                            "candidate_skipped",
                            article_id=candidate.id,
                            reason="Annuaire ou répertoire de sources",
                        )
                        continue
                    if not eligible(candidate, request.profile, seen):
                        self.log(
                            "candidate_skipped",
                            article_id=candidate.id,
                            reason="Langue, exclusion ou article déjà lu",
                        )
                        continue
                    if self.failed_domains[candidate.source] >= 2:
                        import_errors.append(
                            {"url": candidate.url, "error": "Domaine déjà inaccessible"}
                        )
                        continue
                    existing = self.store.get_article(candidate.id)
                    if existing:
                        articles.append(existing)
                        continue
                    try:
                        self.budget.take("discovered_article")
                        self.budget.take("discovery_fetch")
                        candidate = candidate.model_copy(
                            update={
                                "discovery": {
                                    **candidate.discovery,
                                    "provider": "openai_web_search",
                                    "query": query,
                                    "requested_query": requested_query,
                                    "strategy": strategy,
                                    "justification": decision.justification,
                                    "discovered_at": utcnow().isoformat(),
                                }
                            }
                        )
                        articles.append(await self.collector.extract(candidate))
                    except (RetrievalError, BudgetExceeded) as exc:
                        if isinstance(exc, RetrievalError):
                            self.failed_domains[candidate.source] += 1
                        import_errors.append({"url": candidate.url, "error": str(exc)})
                        self.log("candidate_skipped", article_id=candidate.id, reason=str(exc))
            else:
                self.budget.take("search_catalog")
                articles = self.store.articles(self.settings.max_catalog_articles)
            articles = [
                a
                for a in articles
                if a.id not in self.prepared_ids
                and a.id not in self.rejected
                and not self._dated_out(a, allow_evergreen=True)
            ]
            ranked = rank(
                articles,
                request.profile,
                seen,
                query=decision.query if decision.action == "search_catalog" else None,
                needs=self.intent["needs"],
            )
            pool = diversify(ranked, 20, 4)
            if pool:
                self.log(
                    "search_screen_requested",
                    query=decision.query,
                    candidates=[preview(r) for r in pool],
                )
                try:
                    screened = await self.model.screen(
                        {
                            "profile": request.profile.model_dump(exclude={"seen_article_ids"}),
                            "size": request.size,
                            "max_per_source": request.max_per_source,
                            "selection_limit": 12,
                            "candidates": [preview(r) for r in pool],
                            "sections": self.plan.sections if self.plan else [],
                            "today": utcnow().date().isoformat(),
                            "max_article_age_days": self.settings.max_article_age_days,
                            "max_research_age_days": self.settings.max_research_age_days,
                            "editorial_intent": self.intent,
                            "min_editorial_score": self.settings.min_editorial_score,
                            "exploration_allowed": self.exploration_active,
                        },
                        self.budget,
                    )
                except (ModelError, BudgetExceeded) as exc:
                    return {"error": f"Filtre éditorial indisponible : {exc}", "added_ids": []}
                self.log("search_screen_completed", plan=screened.model_dump())
                by_id = {r.article.id: r for r in pool}
                ranked = []
                for pick in screened.picks:
                    if pick.article_id in by_id:
                        row = by_id.pop(pick.article_id)
                        error = self._pick_error(
                            pick,
                            row,
                            self.plan.sections if self.plan else [],
                            screened.contract_version >= 2,
                        )
                        if error:
                            self.log("candidate_skipped", article_id=pick.article_id, reason=error)
                            continue
                        if pick.exploration:
                            self.exploration_pool[pick.article_id] = row
                        else:
                            ranked.append(row)
                        self.picks[pick.article_id] = pick
                for id_ in by_id:
                    self.log(
                        "candidate_skipped",
                        article_id=id_,
                        reason="Non retenu par le filtre éditorial",
                    )
            ids = await self._add_candidates(
                ranked,
                request,
                seen,
                min(12, max(5, request.size - len(self.candidates))),
                editorial_order=True,
            )
            return {
                "query": query if decision.action == "search_web" else decision.query,
                "added_ids": ids,
                "rejections": [r for id_, r in self.rejected.items() if id_ not in rejected_before],
                **(
                    {
                        "import_errors": import_errors,
                        "requested_query": requested_query,
                        "strategy": strategy,
                        "returned_count": len(found),
                        "discovered_links": [{"url": a.url, "title": a.title} for a in found],
                    }
                    if decision.action == "search_web"
                    else {}
                ),
            }

        if decision.action == "read_article":
            if decision.article_id not in self.candidates:
                raise ValueError("Article inconnu : consulter d'abord le catalogue")
            article = self.articles[decision.article_id]
            if article.extraction_status != "extracted":
                self.budget.take("fetch")
                article = await self.collector.extract(article)
                old_candidate = self.candidates.pop(article.id)
                self.articles.pop(article.id)
                self.preference_policy.matches.pop(article.id, None)
                accepted = await self._prepare(
                    Ranked(article, old_candidate.score, old_candidate.matched_interests),
                    request,
                    seen,
                )
                await self._assess_preferences()
                accepted = accepted and article.id in self.candidates
                if not accepted:
                    return {"article_id": article.id, "error": "Article retiré après extraction"}
            return {
                "article_id": article.id,
                "text": article.text[:12000],
                "truncated": len(article.text) > 12000,
                "extraction_status": article.extraction_status,
            }
        raise ValueError("Action inconnue")
