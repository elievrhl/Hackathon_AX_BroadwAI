"use strict";

// Read the saved audit only: absent evidence remains unknown.
const CoverAudit = (() => {
  const statuses = {
    selected: "Dans la couverture", ready: "Fiche disponible, non retenu",
    rejected: "Écarté", failed: "Préparation en échec", waiting: "Préparation non confirmée",
    reserve: "Réserve Exploration", proposed: "Proposé au plan", examined: "Titre / extrait examiné",
    unknown: "Parcours non enregistré",
  };
  function build(cover) {
    const audit = cover.diagnostics || {}, events = audit.events || [], articles = new Map();
    const ensure = id => {
      if (!id) return null;
      if (!articles.has(id)) articles.set(id, {article_id: id, events: [], origins: new Set()});
      return articles.get(id);
    };
    function merge(item, origin) {
      const row = ensure(item.article_id);
      if (!row) return;
      for (const key of ["title", "url", "source", "published_at", "excerpt", "brief", "extraction_status"])
        if (item[key] != null) row[key] = item[key];
      if (origin) row.origins.add(origin);
      return row;
    }
    const plans = [audit.editorial_plan, ...events.filter(e => e.kind === "search_screen_completed").map(e => e.plan)].filter(Boolean);
    for (const plan of plans) for (const pick of plan.picks || []) {
      const row = ensure(pick.article_id);
      if (row) row.pick = pick;
    }
    for (const event of events) {
      if (["editorial_preview", "search_screen_requested"].includes(event.kind)) {
        for (const item of event.candidates || []) {
          const row = merge(item, event.kind === "editorial_preview" ? "Catalogue initial" : "Recherche complémentaire");
          if (row) row.examined = true;
        }
      }
      if (event.kind === "shortlist") {
        for (const item of event.ranked || []) merge(item);
        for (const id of event.shortlisted_ids || []) { const row = ensure(id); if (row) row.scheduled = true; }
      }
      if (event.article_id) {
        const row = merge(event);
        row.events.push(event);
        if (event.kind === "candidate_prepare") row.started = true;
        if (event.kind === "summary_completed") row.generated = true;
        if (event.kind === "summary_cache_hit") row.reused = true;
        if (event.kind === "candidate_skipped") row.rejection = event.reason;
        if (event.kind === "summary_failed") row.failure = event.error;
        if (event.kind === "access_checked") row.access = event;
      }
    }
    for (const rejection of audit.rejected || []) {
      const row = merge(rejection);
      if (row) row.rejection = rejection.reason;
    }
    // A removal belongs to one attempt, and may be superseded by a later selection.
    for (const attempt of cover.trace || []) for (const removal of attempt.outcome?.removed_by_constraints || []) {
      const row = ensure(removal.article_id);
      if (row) row.removal = {step: attempt.step, reason: removal.reason};
    }
    for (const candidate of audit.candidates || []) merge(candidate).ready = true;
    for (const item of cover.items || []) { const row = merge(item); row.selected = true; row.selection = item; }
    for (const row of articles.values()) {
      row.status = row.selected ? "selected" : row.ready ? "ready" : row.rejection ? "rejected"
        : row.failure ? "failed" : row.started || row.scheduled ? "waiting"
        : row.pick?.exploration ? "reserve" : row.pick ? "proposed" : row.examined ? "examined" : "unknown";
      row.reason = row.selected ? row.selection.reason : row.rejection && !row.ready ? row.rejection
        : row.failure && !row.ready ? row.failure
        : row.removal ? `Retrait à l’étape ${row.removal.step} : ${row.removal.reason}. Motif final individuel non enregistré.`
        : row.ready ? "Fiche disponible pour la sélection finale ; motif individuel de non-sélection non enregistré."
        : row.status === "reserve" ? row.pick.exploration_reason || "Piste connexe proposée pour compléter les places libres."
        : row.status === "waiting" ? "Le journal ne confirme pas de fiche disponible ni de décision finale pour cet article."
        : row.pick?.reason || "Aucune préparation enregistrée pour cet article.";
    }
    const rows = [...articles.values()];
    const countEvents = kind => new Set(events.filter(e => e.kind === kind && e.article_id).map(e => e.article_id)).size;
    return {
      audit, events, articles, rows, plans,
      catalog: events.find(e => e.kind === "catalog_ranked"),
      preview: events.find(e => e.kind === "editorial_preview"),
      counts: {
        examined: events.some(e => ["editorial_preview", "search_screen_requested"].includes(e.kind)) ? rows.filter(r => r.examined).length : null,
        scheduled: events.some(e => e.kind === "shortlist") ? rows.filter(r => r.scheduled).length : null,
        started: events.length ? countEvents("candidate_prepare") : null,
        generated: events.length ? countEvents("summary_completed") : null,
        reused: events.length ? countEvents("summary_cache_hit") : null,
        ready: Array.isArray(audit.candidates) ? audit.candidates.length : null,
        selected: (cover.items || []).length,
      },
    };
  }
  return {build, statuses};
})();
if (typeof module !== "undefined" && module.exports) module.exports = CoverAudit;
