import asyncio
from collections import Counter
from copy import deepcopy
from time import perf_counter
from urllib.parse import urlsplit

from broadwai.config import Settings
from broadwai.discovery import is_feed_directory, validate_source
from broadwai.editorial import compact_candidate, coverage, preview, preview_pool
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
from broadwai.ranking import Ranked, diversify, eligible, rank, similarity
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
        )
        self.candidates: dict[str, Candidate] = {}
        self.articles: dict[str, Article] = {}
        self.trace: list[TraceEvent] = []
        self.warnings: list[str] = []
        self.discovered: dict[str, Article] = {}
        self.plan = None
        self.picks = {}
        self.failed_domains: Counter = Counter()
        self.prepared_ids: set[str] = set()
        self.started = perf_counter()
        self.audit: dict = {"version": 1, "events": []}

    def log(self, kind, **data):
        self.audit["events"].append(
            {
                "sequence": len(self.audit["events"]) + 1,
                "kind": kind,
                "at": utcnow().isoformat(),
                "elapsed_ms": round((perf_counter() - self.started) * 1000),
                **deepcopy(data),
            }
        )

    async def _prepare(self, ranked: Ranked, request: CoverRequest, seen: set[str]) -> bool:
        article = ranked.article
        pick = self.picks.get(article.id)
        if self._dated_out(article, allow_evergreen=bool(pick and pick.evergreen)):
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
        self.prepared_ids.add(article.id)
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
        checked_article = article.model_copy(
            update={"language": article.language or brief.language}
        )
        if not eligible(checked_article, request.profile, seen):
            self.log(
                "candidate_skipped", article_id=article.id, reason="Exclu après lecture/langue"
            )
            return False
        if self._dated_out(article) and brief.content_type == "news":
            self.log(
                "candidate_skipped", article_id=article.id, reason="Actualité périmée ou non datée"
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

    def _dated_out(self, article, *, allow_evergreen=False):
        if article.published_at:
            age = (utcnow() - article.published_at).total_seconds() / 86400
            limit = (
                self.settings.max_evergreen_age_days
                if allow_evergreen
                else self.settings.max_article_age_days
            )
            return age > limit or age < -1
        return article.discovery.get("provider") == "openai_web_search" and not allow_evergreen

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
            batch = shortlist[cursor : cursor + min(3, limit - len(added))]
            cursor += len(batch)
            results = await asyncio.gather(*(self._prepare(r, request, seen) for r in batch))
            added.extend(
                r.article.id for r, accepted in zip(batch, results, strict=True) if accepted
            )
        return added

    def _validate(self, selections: list[Selection], request: CoverRequest) -> list[str]:
        errors = []
        if request.discover_web and self.search.enabled and not self.budget.counts["search_web"]:
            errors.append("Effectue search_web : une découverte web a été demandée")
        if not selections:
            return ["La sélection ne doit pas être vide"]
        if len(selections) > request.size:
            errors.append("Trop d'articles")
        can_research = (
            self.budget.counts["editor"] < self.settings.max_agent_steps
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
                "cherche des remplacements pertinents avant de finaliser"
            )
        sections = Counter(s.section for s in selections)
        if request.size >= 15 and len(selections) == request.size:
            if not 3 <= len(sections) <= 5 or min(sections.values(), default=0) < 2:
                errors.append(
                    "Une une complète exige 3 à 5 rubriques avec au moins 2 articles chacune"
                )
            if self.plan and set(sections) - set(self.plan.sections):
                errors.append("Utilise les rubriques prévues dans editorial_plan")
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
        return errors

    def _allocate(self, selections: list[Selection], request: CoverRequest):
        """Apply mechanical quotas once; the model supplies editorial order and judgments."""
        kept, removed = [], []
        counts = Counter()
        ids = set()
        for s in selections:
            article = self.articles.get(s.article_id)
            reason = None
            if article is None:
                reason = "Identifiant inconnu"
            elif s.article_id in ids:
                reason = "Doublon"
            elif counts[article.source] >= request.max_per_source:
                reason = "Quota de source"
            elif len(kept) >= request.size:
                reason = "Taille demandée atteinte"
            elif any(similarity(article, self.articles[k.article_id]) >= 0.8 for k in kept):
                reason = "Article quasi identique"
            if reason:
                removed.append({"article_id": s.article_id, "reason": reason})
                continue
            ids.add(s.article_id)
            counts[article.source] += 1
            kept.append(s)
        return kept, removed

    def _finish(
        self, selections: list[Selection], request: CoverRequest, title: str, fallback: bool = False
    ) -> Cover:
        items = []
        for selection in selections:
            candidate = self.candidates[selection.article_id]
            items.append(
                CoverItem(
                    **candidate.model_dump(exclude={"score", "matched_interests"}),
                    section=selection.section,
                    reason=selection.reason,
                    headline=selection.headline,
                    reading_kind=(
                        "evergreen"
                        if self.picks.get(selection.article_id)
                        and self.picks[selection.article_id].evergreen
                        else "current"
                    ),
                )
            )
        status = "fallback" if fallback else "complete" if len(items) == request.size else "partial"
        self.log("cover_completed", status=status, selected_ids=[s.article_id for s in selections])
        self.audit["candidates"] = [c.model_dump(mode="json") for c in self.candidates.values()]
        self.audit["duration_ms"] = round((perf_counter() - self.started) * 1000)
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
        self.store.put_cover(cover)
        return cover

    async def run(self, request: CoverRequest) -> Cover:
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
                "max_evergreen_age_days",
            )
        }
        seen = self.store.consumed_ids(request.profile.user_id)
        catalog = self.store.articles(self.settings.max_catalog_articles)
        ranked = rank(
            [a for a in catalog if not self._dated_out(a, allow_evergreen=True)],
            request.profile,
            seen,
        )
        self.log(
            "catalog_ranked",
            catalog_count=len(catalog),
            eligible_count=len(ranked),
            consumed_count=len(seen),
            algorithm="BM25 + fraîcheur, puis diversification",
        )
        pool = preview_pool(ranked, self.settings.editorial_pool_size)
        selection_limit = min(28, max(request.size + 4, self.settings.shortlist_size))
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
                    "max_evergreen_age_days": self.settings.max_evergreen_age_days,
                },
                self.budget,
            )
            self.audit["editorial_plan"] = self.plan.model_dump()
            self.log("editorial_plan", plan=self.plan.model_dump())
            by_id = {r.article.id: r for r in pool}
            selected = []
            for pick in self.plan.picks:
                if (
                    pick.article_id in by_id
                    and pick.article_id not in self.picks
                    and pick.score >= self.settings.min_editorial_score
                    and pick.matches_profile
                    and pick.section in self.plan.sections
                ):
                    self.picks[pick.article_id] = pick
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
            state = {
                "profile": request.profile.model_dump(exclude={"seen_article_ids"}),
                "size": request.size,
                "discover_web": request.discover_web,
                "discover_sources": request.discover_sources,
                "max_per_source": request.max_per_source,
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
                key = (decision.action, decision.query, decision.article_id, decision.source_url)
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
            observations.append({"action": decision.action, **outcome})

        self.warnings.append(
            "Sélection de secours déterministe : l'agent n'a pas validé de couverture"
        )
        fallback = diversify(
            [
                Ranked(self.articles[c.article_id], c.score, c.matched_interests)
                for c in self.candidates.values()
            ],
            request.size,
            request.max_per_source,
        )
        selections = [
            Selection(
                article_id=r.article.id,
                section="À découvrir",
                reason="Sélection de secours selon vos intérêts et la diversité.",
            )
            for r in fallback
        ]
        for s in selections:
            if s.article_id in self.picks:
                s.section = self.picks[s.article_id].section
                s.reason = self.picks[s.article_id].reason
        return self._finish(selections, request, "Votre sélection", fallback=True)

    async def _act(self, decision: Decision, request: CoverRequest, seen: set[str]) -> dict:
        if decision.action == "propose_source":
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
                result_limit = min(12, max(5, request.size - len(self.candidates) + 2))
                search_context = {
                    "profile": request.profile.model_dump(exclude={"user_id", "seen_article_ids"}),
                    "strategy": strategy,
                    "avoid_domains": avoid,
                    "max_article_age_days": self.settings.max_article_age_days,
                    "max_evergreen_age_days": self.settings.max_evergreen_age_days,
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
                articles = []
                import_errors = []
                for candidate in found:
                    if is_feed_directory(candidate):
                        continue
                    if not eligible(candidate, request.profile, seen):
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
            else:
                self.budget.take("search_catalog")
                articles = self.store.articles(self.settings.max_catalog_articles)
            articles = [
                a
                for a in articles
                if a.id not in self.prepared_ids and not self._dated_out(a, allow_evergreen=True)
            ]
            ranked = rank(
                articles,
                request.profile,
                seen,
                query=decision.query if decision.action == "search_catalog" else None,
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
                            "max_evergreen_age_days": self.settings.max_evergreen_age_days,
                        },
                        self.budget,
                    )
                except (ModelError, BudgetExceeded) as exc:
                    return {"error": f"Filtre éditorial indisponible : {exc}", "added_ids": []}
                self.log("search_screen_completed", plan=screened.model_dump())
                by_id = {r.article.id: r for r in pool}
                ranked = []
                for pick in screened.picks:
                    if (
                        pick.article_id in by_id
                        and pick.score >= self.settings.min_editorial_score
                        and pick.matches_profile
                        and (not self.plan or pick.section in self.plan.sections)
                    ):
                        ranked.append(by_id.pop(pick.article_id))
                        self.picks[pick.article_id] = pick
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
                accepted = await self._prepare(
                    Ranked(article, old_candidate.score, old_candidate.matched_interests),
                    request,
                    seen,
                )
                if not accepted:
                    return {"article_id": article.id, "error": "Article retiré après extraction"}
            return {
                "article_id": article.id,
                "text": article.text[:12000],
                "truncated": len(article.text) > 12000,
                "extraction_status": article.extraction_status,
            }
        raise ValueError("Action inconnue")
