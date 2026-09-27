"use strict";
const $ = id => document.getElementById(id);
const state = {rows: [], selected: new URLSearchParams(location.search).get("id"), sequence: 0, listSequence: 0, operations: null, generating: false};
const n = (tag, text, cls) => {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (cls) element.className = cls;
  return element;
};
const fmt = value => value == null ? "Non enregistré" : Number(value).toLocaleString("fr-FR", {maximumFractionDigits: 3});
const date = value => value ? new Date(value).toLocaleString("fr-FR") : "Date inconnue";
const duration = value => value == null ? "Non enregistrée" : value < 60000 ? `${fmt(value / 1000)} s` : `${Math.floor(value / 60000)} min ${Math.round(value % 60000 / 1000)} s`;
const statusNames = {complete: "Objectif atteint", partial: "Édition partielle", fallback: "Sélection de secours"};
const actionNames = {search_catalog: "Chercher dans le catalogue", search_web: "Chercher sur le web", read_article: "Approfondir un article", propose_source: "Proposer une source", finalize: "Composer et valider la une", model_error: "Interruption du rédacteur"};
actionNames.search_sources = "Découvrir des blogs et sources spécialisées";
const roleNames = {lead: "Sujet principal", secondary: "Sujet secondaire", brief: "Brève", reading: "Lecture"};
const callNames = {intent: "Compréhension du profil", plan: "Plan éditorial", summary: "Fiche d’article", screen: "Filtre de recherche", editor: "Décision du rédacteur", web_model: "Recherche web", preferences: "Préférences du lecteur"};
const labels = {
  access_checked: "Disponibilité du texte avant le choix éditorial",
  prefetch_completed: "Vérification préalable des textes terminée",
  source_discovery: "Recherche de nouvelles sources",
  source_validated: "Source vérifiée et articles repérés",
  source_proposed: "Source proposée pour les collectes futures",
  catalog_ranked: "Classement du catalogue", editorial_preview: "Titres et extraits envoyés au rédacteur",
  editorial_plan: "Plan éditorial reçu", editorial_plan_failed: "Plan éditorial indisponible",
  shortlist: "File d’articles à préparer", candidate_prepare: "Préparation commencée",
  candidate_skipped: "Article écarté", extract_requested: "Texte intégral demandé",
  extract_completed: "Texte extrait", extract_failed: "Extraction en échec",
  summary_requested: "Création d’une fiche demandée", summary_completed: "Fiche créée",
  summary_failed: "Création de fiche en échec", summary_cache_hit: "Fiche existante réutilisée",
  candidate_ready: "Candidat disponible après contrôles", editor_requested: "Consultation du rédacteur",
  editor_decision: "Décision du rédacteur", editor_failed: "Rédacteur indisponible",
  validation: "Contrôle de la sélection", tool_requested: "Action demandée", tool_result: "Résultat de l’action",
  cover_completed: "Couverture enregistrée", cited_sources: "Pistes citées dans une fiche",
  web_discovery: "Liens trouvés sur le web", search_screen_requested: "Examen des résultats de recherche",
  search_screen_completed: "Résultats de recherche évalués", exploration_opened: "Ouverture aux thèmes connexes",
  selection_allocated: "Application des quotas", layout_roles_adjusted: "Ajustement des rôles dans la une",
  temporal_review_requested: "Vérification de la validité temporelle", final_reserve_used: "Budget réservé à la finalisation",
  controller_decision: "Recherche ciblée décidée par le serveur",
  research_completed: "Recherches terminées : passage à la composition",
  reserve_opened: "Préparation d’alternatives déjà présélectionnées",
  reader_preferences_assessed: "Préférences évaluées", reader_preferences_failed: "Évaluation des préférences en échec",
  intent_items_rejected: "Interprétation du profil corrigée", intent_failed: "Interprétation du profil indisponible",
};
function link(label, url) {
  const a = n("a", label);
  try {
    const u = new URL(url, location.origin);
    if (["https:", "http:"].includes(u.protocol) && !u.username && !u.password) a.href = u.href;
  } catch { /* Keep the text when no link is usable. */ }
  a.target = "_blank"; a.rel = "noopener noreferrer";
  return a;
}
async function api(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof data?.detail === "string" ? data.detail : `Requête impossible (${response.status})`);
  if (data === null) throw new Error("Réponse du serveur illisible.");
  return data;
}
function error(e) { $("error").hidden = false; $("error").textContent = e.message; }
function jsonDetails(label, data) {
  const d = n("details", undefined, "raw-details");
  d.append(n("summary", label), n("pre", JSON.stringify(data, null, 2)));
  return d;
}
function section(parent, title, description, {open = false, id} = {}) {
  const d = n("details", undefined, "section-details");
  d.open = open;
  if (id) d.id = id;
  const heading = n("summary"), text = n("span", title, "section-title");
  if (description) text.append(n("span", description, "section-description"));
  heading.append(text); d.append(heading); parent.append(d);
  return d;
}
function table(parent, columns, rows) {
  const wrap = n("div", undefined, "table-scroll"), t = n("table"), head = n("tr");
  wrap.tabIndex = 0; wrap.setAttribute("role", "region"); wrap.setAttribute("aria-label", columns.join(" · "));
  for (const column of columns) { const th = n("th", column); th.scope = "col"; head.append(th); }
  const thead = n("thead"); thead.append(head); t.append(thead);
  const body = n("tbody");
  for (const cells of rows) {
    const row = n("tr");
    for (const cell of cells) { const td = n("td"); td.append(cell instanceof Node ? cell : document.createTextNode(String(cell ?? "—"))); row.append(td); }
    body.append(row);
  }
  t.append(body); wrap.append(t); parent.append(wrap);
}
function paragraphs(parent, values, cls = "") { for (const value of values || []) parent.append(n("p", value, cls)); }
function badge(text, kind = "") { return n("span", text, `audit-badge ${kind}`); }
function articleName(data, id) { return data.articles.get(id)?.title || id; }
function humanMessage(message, data) { return String(message).replace(/\b[a-f0-9]{22,32}\b/g, id => articleName(data, id)); }
function renderBrief(parent, item) {
  const brief = item.brief;
  if (!brief) { parent.append(n("p", "Fiche non enregistrée dans cette trace.", "muted")); return; }
  parent.append(n("p", brief.summary, "prose"));
  const points = n("ul");
  for (const point of brief.key_points || []) points.append(n("li", point));
  parent.append(points); paragraphs(parent, brief.caveats, "notice");
  if (brief.validity) parent.append(n("p", `Validité du contenu : ${brief.validity.reason}`, "small"));
  if (brief.dossier) {
    const d = brief.dossier;
    const integrity = {clear: "Propos isolable", fragmentary: "Contenu partiel", unusable: "Inexploitable"};
    const support = {reported: "Reportage", argument: "Argument / opinion", method: "Méthode", research: "Résultat de recherche", announcement: "Sujet annoncé", unclear: "Base indéterminée"};
    table(parent, ["Dossier réutilisable", "Observation"], [
      ["Apport concret", d.contribution], ["Angle", d.angle], ["Prérequis", d.prerequisites],
      ["État du texte", integrity[d.integrity] || d.integrity],
      ["Nature du propos", support[d.support] || d.support],
      ["Temporalité", {evergreen: "Fond durable", research: "Recherche datée", news: "Actualité", event: "Événement"}[d.temporal_kind]],
      ["Dépendance temporelle", d.temporal_dependency || "Aucune identifiée"],
      ["Risque sur le propos central", d.central_risk ? "Signalé" : "Non signalé"],
    ]);
    parent.append(n("p", "Ces observations décrivent le document, pas une certification. L’adéquation au lecteur est jugée à la composition ; l’âge est vérifié par le serveur.", "small"));
  }
  appendCitedSources(parent, brief.cited_sources);
}
function articleDetails(row) {
  const d = n("details", undefined, "article-journey");
  d.append(n("summary", row.selection?.headline || row.title || row.article_id));
  if (row.url) d.append(link("Lire chez l’éditeur ↗", row.url));
  if (row.access) d.append(n("p", `Avant le choix éditorial : ${{full_text: "texte intégral disponible", excerpt_only: "extrait seulement", unavailable: "contenu inexploitable"}[row.access.status] || row.access.status}${row.access.checked ? "" : " · téléchargement non effectué"}${row.access.error ? ` · ${row.access.error}` : ""}`, "small"));
  if (row.pick) {
    d.append(n("p", `Avis éditorial : ${fmt(row.pick.score)}/100 · ${row.pick.section || "Rubrique inconnue"}`, "small"), n("p", row.pick.reason));
  }
  if (row.events.length) {
    const list = n("ol", undefined, "article-events");
    for (const event of row.events.filter(e => e.kind !== "cited_sources")) list.append(n("li", `${duration(event.elapsed_ms)} · ${labels[event.kind] || event.kind}${event.reason || event.error ? ` — ${event.reason || event.error}` : ""}`));
    d.append(list);
  }
  if (row.removal) d.append(n("p", `Lors de la tentative ${row.removal.step} : ${row.removal.reason}. Cette observation ne remplace pas le résultat final.`, "small"));
  if (row.brief) renderBrief(d, row);
  d.append(n("p", `Identifiant : ${row.article_id}`, "small"));
  return d;
}
function renderArticleExplorer(parent, data) {
  const panel = section(parent, "Que sont devenus les articles ?", "Recherchez un titre, filtrez son résultat, puis ouvrez-le pour suivre son parcours.", {open: true});
  const filters = n("div", undefined, "audit-filters"), searchLabel = n("label", "Titre, source ou motif"), search = n("input");
  search.type = "search"; search.placeholder = "Rechercher un article…";
  search.id = "article-search"; searchLabel.htmlFor = search.id; searchLabel.append(search);
  const selectLabel = n("label", "Résultat"), select = n("select");
  select.id = "article-result"; selectLabel.htmlFor = select.id; select.setAttribute("aria-label", "Résultat");
  for (const [value, label] of [["all", "Tous les articles identifiés"], ...Object.entries(CoverAudit.statuses)]) { const option = n("option", label); option.value = value; select.append(option); }
  selectLabel.append(select); filters.append(searchLabel, selectLabel); panel.append(filters);
  const count = n("p", undefined, "small"), content = n("div"), controls = n("div", undefined, "audit-pagination");
  count.setAttribute("role", "status");
  const previous = n("button", "← Précédents"), next = n("button", "Suivants →"), position = n("span");
  controls.append(previous, position, next); panel.append(count, content, controls);
  const order = Object.keys(CoverAudit.statuses), rows = [...data.rows].sort((a, b) => order.indexOf(a.status) - order.indexOf(b.status));
  let page = 0;
  const normalize = text => text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("fr");
  function draw() {
    const query = normalize(search.value.trim());
    const filtered = rows.filter(r => (select.value === "all" || r.status === select.value) && normalize([r.title, r.selection?.headline, r.source, r.reason, r.article_id].join(" ")).includes(query));
    const start = page * 12, end = Math.min(start + 12, filtered.length);
    count.textContent = `${filtered.length} article${filtered.length > 1 ? "s" : ""} · un article n’est compté qu’une fois, même s’il apparaît dans plusieurs recherches.`;
    content.replaceChildren();
    if (!filtered.length) content.append(n("p", "Aucun article ne correspond à ce filtre.", "empty"));
    else table(content, ["Article et parcours", "Résultat", "Explication enregistrée"], filtered.slice(start, end).map(row => {
      const name = n("div"); name.append(articleDetails(row), n("p", row.source || [...row.origins].join(" · ") || "Source non enregistrée", "small"));
      return [name, badge(CoverAudit.statuses[row.status], row.status), row.reason];
    }));
    previous.disabled = page === 0; next.disabled = end >= filtered.length;
    position.textContent = filtered.length ? `${start + 1}–${end} sur ${filtered.length}` : "0 résultat"; controls.hidden = filtered.length <= 12;
  }
  for (const control of [search, select]) control.addEventListener(control === search ? "input" : "change", () => { page = 0; draw(); });
  previous.addEventListener("click", () => { page--; draw(); }); next.addEventListener("click", () => { page++; draw(); }); draw();
}
function renderOverview(parent, cover, data) {
  const {audit, counts} = data, target = audit.request?.size, usage = cover.usage || {};
  const header = n("div", undefined, "edition-heading"), title = n("div");
  title.append(n("p", date(cover.created_at), "eyebrow"), n("h2", cover.title));
  header.append(title, badge(statusNames[cover.status] || cover.status, cover.status)); parent.append(header);
  const result = cover.status === "fallback" ? "Le rédacteur n’a pas validé de sélection. Une sélection de secours a été enregistrée à partir des candidats disponibles."
    : cover.status === "partial" ? "La sélection validée comporte moins d’articles que demandé. Les recherches, contrôles et avertissements ci-dessous expliquent les limites rencontrées."
    : "Le rédacteur a validé une sélection qui atteint le nombre d’articles demandé.";
  parent.append(n("p", result, "edition-result"));
  const metrics = n("div", undefined, "inspection-stats"), cost = usage.cost?.estimated_usd;
  for (const [value, label] of [
    [target == null ? fmt(counts.selected) : `${counts.selected} / ${target}`, "articles dans la une"],
    [new Set((cover.items || []).map(i => i.source).filter(Boolean)).size, "sources dans la une"],
    [duration(audit.duration_ms), "durée de génération"],
    [cost == null ? "Non disponible" : `${fmt(cost)} $ US`, "coût estimé de génération"],
  ]) { const box = n("div"); box.append(n("strong", value), n("span", label)); metrics.append(box); }
  parent.append(metrics, link("Ouvrir cette édition dans Kiosque ↗", `/reader/?cover=${encodeURIComponent(cover.id)}`));
  if (!audit.version) parent.append(n("p", "Trace ancienne : certaines étapes et leurs compteurs n’ont pas été enregistrés. Les données manquantes restent indiquées comme telles.", "notice"));
  if (cover.warnings?.length) {
    const warnings = section(parent, `${cover.warnings.length} avertissement${cover.warnings.length > 1 ? "s" : ""} enregistré${cover.warnings.length > 1 ? "s" : ""}`, "Difficultés rencontrées pendant cette génération.");
    paragraphs(warnings, cover.warnings.map(w => humanMessage(w, data)), "notice");
  }
  const flow = n("nav", undefined, "pipeline-flow"); flow.setAttribute("aria-label", "Étapes de création de la couverture");
  const steps = [
    ["profile", "Profil et catalogue", data.catalog?.eligible_count, "articles après filtrage"],
    ["plan", data.events.some(e => e.kind === "prefetch_completed") ? "Disponibilité et présélection" : "Titres et extraits", counts.examined, "articles examinés"],
    ["preparation", "Préparer les fiches", counts.started, "préparations commencées"],
    ["decisions", "Chercher et arbitrer", counts.ready, "candidats disponibles à la fin"],
    ["edition", "Enregistrer la une", counts.selected, "articles retenus"],
  ];
  steps.forEach(([id, label, count, suffix], index) => {
    const a = n("a", undefined, "pipeline-step"); a.href = `#stage-${id}`;
    a.append(n("span", `${index + 1}. ${label}`, "step-label"), n("strong", count == null ? "—" : fmt(count)), n("span", count == null ? "Donnée non enregistrée" : suffix, "small"));
    a.addEventListener("click", () => { $(`stage-${id}`).open = true; }); flow.append(a);
  });
  parent.append(flow, n("p", "Les recherches peuvent ajouter des articles et relancer leur préparation. Ces compteurs décrivent des étapes différentes : ils ne s’additionnent pas.", "small"));
}
function renderProfile(parent, data) {
  const {audit, catalog} = data, request = audit.request || {}, profile = request.profile;
  const panel = section(parent, "1. Comprendre la demande et filtrer le catalogue", "Le profil, les préférences et les articles déjà lus orientent le point de départ.", {id: "stage-profile"});
  if (profile) {
    panel.append(n("p", `Intérêts : ${(profile.interests || []).map(i => `${i.topic} (poids ${i.weight})`).join(" · ")}`));
    panel.append(n("p", `Langues : ${(profile.languages || []).join(", ")} · Niveau : ${{beginner: "débutant", intermediate: "intermédiaire", expert: "expert"}[profile.level] || profile.level} · Maximum par source : ${fmt(request.max_per_source)}`, "small"));
    if (profile.notes) panel.append(n("blockquote", profile.notes));
  } else panel.append(n("p", "Profil utilisé non enregistré.", "muted"));
  if (catalog) panel.append(n("p", `${fmt(catalog.catalog_count)} articles chargés du catalogue ; ${fmt(catalog.eligible_count)} restent après les filtres initiaux. L’historique contient ${fmt(catalog.consumed_count)} articles consommés par ce lecteur.`));
  const needs = audit.editorial_intent?.needs || [], uncovered = new Set((audit.uncovered_needs || []).map(i => i.id));
  if (needs.length) table(panel, ["Besoin interprété", "Priorité", "Couverture du besoin"], needs.map(need => [need.topic, need.priority === "primary" ? "Principale" : "Secondaire", audit.uncovered_needs == null ? "Non enregistrée" : uncovered.has(need.id) ? "Non couvert" : "Couvert selon la trace"]));
  paragraphs(panel, (audit.editorial_intent?.constraints || []).map(c => `Consigne : ${c.requirement}`));
  const rules = audit.reader_preferences?.rules || [];
  if (rules.length) table(panel, ["Préférence", "Effet demandé", "Application"], rules.map(rule => [rule.target, {more: "Favoriser", less: "Réduire", exclude: "Exclure", diversify: "Découvrir"}[rule.action] || rule.action, rule.explanation || "Sans précision supplémentaire"]));
  if (audit.preference_impact?.length) table(panel, ["Demande du lecteur", "Articles correspondants dans la une"], audit.preference_impact.map(p => [p.target, p.selected_count]));
}
function picksTable(parent, picks, data) {
  table(parent, ["Article proposé", "Rubrique", "Avis / 100", "Justification"], (picks || []).map(p => {
    const info = n("div", p.reason);
    if (p.exploration) info.append(n("p", `Réserve Exploration : ${p.exploration_reason || "raison non enregistrée"}`, "small"));
    info.append(n("p", `Contexte du profil respecté : ${p.matches_profile == null ? "inconnu" : p.matches_profile ? "oui" : "non"} · Lecture de fond : ${p.evergreen == null ? "inconnue" : p.evergreen ? "oui" : "non"}`, "small"));
    return [articleName(data, p.article_id), p.section, fmt(p.score), info];
  }));
}
function renderPlan(parent, data) {
  const {audit, preview} = data, plan = audit.editorial_plan;
  const preflight = data.events.find(e => e.kind === "prefetch_completed");
  const panel = section(parent, preflight ? "2. Vérifier la disponibilité, puis présélectionner" : "2. Choisir les articles prometteurs sur titre et extrait", "Le rédacteur propose des pistes à partir des titres et extraits. Elles ne sont pas encore retenues dans la une.", {id: "stage-plan"});
  if (preflight) {
    const checks = data.events.filter(e => e.kind === "access_checked" && e.sequence < preflight.sequence);
    panel.append(n("p", "Avant cet examen, le serveur récupère les textes manquants sur un lot limité. Le rédacteur sait s’il dispose du texte intégral ou d’un extrait ; les contenus inexploitables sont retirés. Le texte récupéré est réutilisé lors de la préparation des fiches."));
    table(panel, ["Contrôle préalable", "Articles"], [
      ["Texte intégral disponible", checks.filter(e => e.status === "full_text").length],
      ["Extrait seulement", checks.filter(e => e.status === "excerpt_only").length],
      ["Contenu inexploitable", checks.filter(e => e.status === "unavailable").length],
      ["Dont téléchargement non effectué (temps ou quota épuisé)", checks.filter(e => !e.checked).length],
      ["Admis après contrôle de disponibilité et exclusions", preflight.available_count],
    ]);
  }
  panel.append(n("p", `Le premier examen porte sur ${preview ? preview.candidates.length : "un nombre non enregistré de"} titres et extraits. Le classement lexical rapproche les mots du profil et des articles ; la diversification élargit les sources.`));
  if (!plan) { panel.append(n("p", "Plan éditorial non enregistré ou indisponible.", "muted")); return; }
  panel.append(n("p", `Rubriques envisagées : ${(plan.sections || []).join(" · ")}`));
  panel.append(n("p", plan.contract_version >= 3 ? "Le score sur 100 sert à ordonner les pistes plausibles, sans seuil éliminatoire. La pertinence, les prérequis et l’apport sont réévalués à la composition. Les rubriques ci-dessus sont provisoires." : `Le score éditorial est un avis du modèle sur 100. ${audit.settings?.min_editorial_score == null ? "Seuil de passage non enregistré." : `Seuil utilisé : ${audit.settings.min_editorial_score}/100.`} Un score suffisant ne garantit pas la sélection : le contexte et les contrôles suivants comptent aussi.`, "small"));
  const picks = section(panel, `${(plan.picks || []).length} propositions dans le plan initial`, "Inclut les propositions ensuite rejetées et les réserves d’Exploration.");
  picksTable(picks, plan.picks, data);
  paragraphs(panel, (plan.gaps || []).map(g => `Manque repéré : ${g}`), "notice");
  paragraphs(panel, (plan.queries || []).map(q => `Recherche suggérée, pas nécessairement exécutée : ${q}`), "small");
  if (preview) panel.append(jsonDetails("Titres et extraits du premier examen", preview.candidates));
}
function renderPreparation(parent, data) {
  const {counts, audit, events} = data;
  const panel = section(parent, "3. Préparer la fiche et vérifier le contenu", "Une fiche peut être créée puis rejetée après vérification de sa validité, de sa langue ou des préférences du lecteur.", {id: "stage-preparation"});
  panel.append(n("p", "Les « articles présélectionnés » de l’ancienne interface correspondent aux files d’articles à préparer. Entrer dans une file ne prouve ni que la préparation a commencé, ni qu’une fiche a été validée."));
  table(panel, ["Mesure", "Articles distincts", "Ce que cela signifie"], [
    ["Dans les files de préparation", fmt(counts.scheduled), "Candidats envoyés à la préparation, tous passages confondus. Les réserves Exploration peuvent être préparées séparément."],
    ["Préparation commencée", fmt(counts.started), data.events.some(e => e.kind === "prefetch_completed") ? "Réutilisation du texte contrôlé en amont et recherche d’une fiche en cache." : "Extraction éventuelle du texte et recherche d’une fiche réutilisable."],
    ["Nouvelle fiche reçue", fmt(counts.generated), "Résumé structuré généré. Les contrôles de fond viennent ensuite."],
    ["Fiche existante réutilisée", fmt(counts.reused), "Fiche retrouvée en cache, sans nouveau résumé pour cet événement."],
    ["Candidats disponibles à la fin", fmt(counts.ready), "Fiches restées disponibles pour la composition finale ; certaines ne seront pas retenues."],
  ]);
  panel.append(n("p", "Les catégories peuvent se recouper si un article a été préparé plusieurs fois. Un échec d’extraction peut laisser un extrait exploitable ; il ne signifie pas à lui seul que l’article est écarté.", "small"));
  const candidates = section(panel, "Consulter les fiches disponibles à la fin", `${fmt(counts.ready)} candidat(s) enregistré(s).`);
  if (audit.candidates) for (const c of audit.candidates) candidates.append(articleDetails(data.articles.get(c.article_id)));
  else candidates.append(n("p", "Seules les fiches de la couverture finale sont connues.", "muted"));
  const queues = section(panel, "Files de préparation et scores de classement", "Détail technique des passages. Le score lexical est relatif au corpus ; il ne se compare pas au score éditorial sur 100.");
  const stages = events.filter(e => e.kind === "shortlist");
  if (!stages.length) queues.append(n("p", "Files non enregistrées.", "muted"));
  stages.forEach((stage, index) => {
    const d = section(queues, `Passage ${index + 1} · ${(stage.shortlisted_ids || []).length} articles dans la file`, `${fmt(stage.ranked_count)} candidats à ce passage.`);
    const ids = new Set(stage.shortlisted_ids || []);
    table(d, ["Article", "Score lexical", "Dans la file", "Composantes"], (stage.ranked || []).map(r => [r.url ? link(r.title, r.url) : r.title, fmt(r.score), ids.has(r.article_id) ? "Oui" : "Non", jsonDetails("Détail du score", r.score_details)]));
    if (stage.ranked_count > (stage.ranked || []).length) d.append(n("p", `Le journal ne conserve que ${(stage.ranked || []).length} lignes sur ${stage.ranked_count}.`, "small"));
  });
}
function renderDecisions(parent, cover, data) {
  const controlled = data.events.some(e => e.kind === "research_completed");
  const panel = section(parent, "4. Compléter, arbitrer et contrôler la sélection", controlled ? "Le serveur cherche seulement si des besoins manquent ou si moins de 80 % de la cible est disponible. Il réutilise les réserves, puis limite les recherches. Le rédacteur compare les apports et compose : 18 est une cible, pas un minimum obligatoire." : "Le rédacteur alterne recherches, lectures et tentatives de finalisation. Chaque résultat peut modifier l’étape suivante.", {id: "stage-decisions"});
  const trace = cover.trace || [];
  if (!trace.length) panel.append(n("p", "Aucune décision enregistrée.", "muted"));
  for (const event of trace) {
    const out = event.outcome || {}, issues = [...(out.errors || []), ...(out.error ? [out.error] : [])];
    const result = issues.length ? `${issues.length} difficulté(s) signalée(s)` : event.action === "finalize" ? `${fmt(out.selected)} articles validés` : Array.isArray(out.added_ids) ? `${out.added_ids.length} candidats ajoutés` : "Résultat disponible";
    const actor = out.actor === "controller" ? `Serveur · recherche ${Math.abs(event.step)}` : `Rédacteur · étape ${event.step}`;
    const d = section(panel, `${actor} · ${actionNames[event.action] || event.action}`, result);
    if (issues.length) d.classList.add("has-issues");
    d.append(n("p", event.justification));
    const request = data.events.find(e => e.kind === "tool_requested" && e.step === event.step), query = out.query || request?.query;
    if (query) d.append(n("blockquote", query));
    if (out.returned_count != null) d.append(n("p", `${out.returned_count} liens trouvés ; ${(out.added_ids || []).length} candidats ajoutés après import et préparation.`));
    if (out.sources?.length) {
      table(d, ["Source vérifiée", "Type", "Articles repérés"], out.sources.map(s => [link(s.name, s.url), s.kind === "rss" ? "Flux RSS/Atom" : "Site web", s.article_ids?.length ?? "Non enregistré"]));
      d.append(n("p", "Quelques articles de ces sites ont été examinés pour cette édition. Leur ajout aux collectes futures reste soumis à validation dans l’admin.", "small"));
    }
    if (out.source_proposals?.length) for (const proposal of out.source_proposals) {
      const p = n("p"); p.append(link("Voir les propositions de sources dans l’admin ↗", "/admin"), n("span", ` · ${proposal.url} · ${proposal.status}`)); d.append(p);
    }
    paragraphs(d, issues.map(issue => humanMessage(issue, data)), "notice");
    if (out.added_ids?.length) paragraphs(d, out.added_ids.map(id => `Candidat ajouté : ${articleName(data, id)}`));
    if (out.removed_by_constraints?.length) table(d, ["Article retiré de cette tentative", "Contrainte appliquée"], out.removed_by_constraints.map(r => [articleName(data, r.article_id), r.reason]));
    if (out.import_errors?.length) table(d, ["Page inaccessible", "Motif"], out.import_errors.map(r => [link(r.url, r.url), r.error]));
    if (out.discovered_links?.length) {
      const links = section(d, `${out.discovered_links.length} liens découverts`, "Un lien trouvé n’est pas encore un article importé ni sélectionné.");
      for (const item of out.discovered_links) { const p = n("p"); p.append(link(item.title, item.url)); links.append(p); }
    }
    d.append(jsonDetails("Données de cette action", out));
  }
  const screens = data.events.filter(e => e.kind === "search_screen_completed");
  if (screens.length) {
    const checks = section(panel, "Évaluation des articles trouvés pendant les recherches", "Ces propositions suivent les mêmes contrôles que le plan initial.");
    for (const [index, event] of screens.entries()) {
      const request = data.events.filter(e => e.kind === "search_screen_requested" && e.sequence < event.sequence).at(-1);
      const step = section(checks, `Filtre ${index + 1}`, request?.query || "Requête non enregistrée");
      picksTable(step, event.plan?.picks, data);
    }
  }
  if (data.events.some(e => e.kind === "exploration_opened")) panel.append(n("p", "Exploration a été activée : des thèmes connexes ont été envisagés pour compléter les places libres, avec les mêmes exigences de qualité.", "notice"));
}
function renderEdition(parent, cover, data) {
  const panel = section(parent, `5. Couverture enregistrée · ${data.counts.selected} articles`, "La liste ci-dessous est le résultat publié, dans l’ordre éditorial.", {id: "stage-edition"});
  for (const item of cover.items || []) {
    const d = section(panel, item.headline || item.title, [item.section, roleNames[item.role], item.source].filter(Boolean).join(" · "));
    if (item.reason) d.append(n("p", `Pourquoi cet article : ${item.reason}`));
    if (item.exploration_reason) d.append(n("p", `Exploration : ${item.exploration_reason}`, "notice"));
    d.append(link("Lire l’article original ↗", item.url)); renderBrief(d, item);
  }
  if (!cover.items?.length) panel.append(n("p", "Aucun article enregistré dans cette couverture.", "muted"));
  panel.append(n("p", "Les visuels sont récupérés et vérifiés lors de l’affichage dans Kiosque. Leur contrôle et son coût ne figurent pas dans cette trace de génération.", "small"));
  const sources = data.events.filter(e => e.kind === "cited_sources"), sourceCount = sources.reduce((total, e) => total + (e.sources || []).length, 0);
  const sourcePanel = section(panel, `Pistes citées dans les fiches · ${sources.length ? sourceCount : "non enregistrées"}`, "Inclut les fiches d’articles ensuite écartés. Une piste n’est pas automatiquement une source ajoutée au catalogue.");
  for (const event of sources.filter(e => e.sources?.length)) {
    const origin = section(sourcePanel, event.title || articleName(data, event.article_id));
    if (event.url) origin.append(link("Article à l’origine de ces pistes ↗", event.url));
    appendCitedSources(origin, event.sources);
  }
  if (!sourceCount) sourcePanel.append(n("p", sources.length ? "Aucune piste citée retenue." : "Pistes non enregistrées pour cette édition.", "muted"));
}
function renderTechnical(parent, cover, data) {
  const usage = cover.usage || {}, calls = usage.model_calls || [];
  const panel = section(parent, "Coûts, limites et journal technique", "Usage des modèles, paramètres exacts et données brutes pour approfondir le diagnostic.");
  panel.append(n("p", `${fmt(usage.input_tokens)} tokens entrants · ${fmt(usage.output_tokens)} sortants · ${fmt(usage.calls?.summary)} appels de résumé · ${fmt(usage.summary_cache_hits)} réutilisations de fiches.`, "small"));
  panel.append(n("p", "Le coût affiché est une estimation, pas une facture. Les tokens d’entrée mis en cache sont déjà inclus dans le total entrant.", "small"));
  if (usage.cost?.basis) panel.append(n("p", usage.cost.basis, "small"));
  if (usage.cost?.unpriced_calls) panel.append(n("p", `${usage.cost.unpriced_calls} appel(s) sans estimation tarifaire.`, "notice"));
  panel.append(n("p", `Budget restant : ${fmt(usage.remaining_tokens)} tokens · réserve de finalisation : ${fmt(usage.final_token_reserve)} · réservations non réconciliées : ${fmt(usage.unsettled_token_reservations)}.`, "small"));
  if (calls.length) table(panel, ["Rôle / modèle", "État / durée", "Tokens entrée / cache / sortie", "Détail"], calls.map(call => [
    `${callNames[call.kind] || call.kind} · ${call.model}`, `${{completed: "Terminé", error: "Erreur", pending: "En attente"}[call.status] || call.status} · ${duration(call.duration_ms)}`,
    `${fmt(call.usage?.input_tokens)} / ${fmt(call.usage?.cached_input_tokens)} / ${fmt(call.usage?.output_tokens)}`, jsonDetails(call.title || call.query || "Voir l’appel", call),
  ]));
  else panel.append(n("p", "Détail des appels non enregistré.", "muted"));
  if (data.audit.request) panel.append(jsonDetails("Profil et requête exacts", data.audit.request));
  if (data.audit.settings) panel.append(jsonDetails("Limites utilisées pour cette édition", data.audit.settings));
  const journal = section(panel, `Journal chronologique · ${data.events.length} événements`);
  for (const event of data.events) journal.append(jsonDetails(`${event.sequence} · ${duration(event.elapsed_ms)} · ${labels[event.kind] || event.kind}${event.article_id ? ` · ${articleName(data, event.article_id)}` : ""}`, event));
  panel.append(jsonDetails("Toutes les données enregistrées", cover), link("Ouvrir le JSON de la couverture", `/v1/covers/${encodeURIComponent(cover.id)}`));
}
function renderCover(cover) {
  const data = CoverAudit.build(cover), parent = $("cover-detail"); parent.replaceChildren();
  renderOverview(parent, cover, data);
  renderProfile(parent, data); renderPlan(parent, data); renderPreparation(parent, data);
  renderDecisions(parent, cover, data); renderEdition(parent, cover, data);
  renderArticleExplorer(parent, data); renderTechnical(parent, cover, data);
}
async function showCover(id) {
  const seq = ++state.sequence;
  state.selected = id; history.replaceState(null, "", `?id=${encodeURIComponent(id)}`); renderHistory();
  $("cover-detail").setAttribute("aria-busy", "true"); $("cover-detail").replaceChildren(n("p", "Chargement de la trace…", "empty"));
  try { const cover = await api(`/v1/covers/${encodeURIComponent(id)}`); if (seq === state.sequence) renderCover(cover); }
  catch (e) { if (seq === state.sequence) { error(e); $("cover-detail").replaceChildren(n("p", "Cette couverture n’a pas pu être chargée. Réessayez avec Actualiser.", "empty")); } }
  finally { if (seq === state.sequence) $("cover-detail").removeAttribute("aria-busy"); }
}
function renderHistory() {
  const list = $("covers-list"); list.replaceChildren();
  if (!state.rows.length) list.append(n("p", "Aucune couverture enregistrée.", "empty"));
  for (const cover of state.rows) {
    const b = n("button", cover.title, `history-item${state.selected === cover.id ? " active" : ""}`);
    if (state.selected === cover.id) b.setAttribute("aria-current", "true");
    b.append(n("small", date(cover.created_at)), n("small", `${statusNames[cover.status] || cover.status} · ${cover.item_count} articles`), n("small", Number(cover.audit_version) ? "Trace détaillée" : "Trace ancienne, partielle"));
    b.addEventListener("click", () => showCover(cover.id)); list.append(b);
  }
}
const scheduleNames = { scheduled: "Programmée", running: "En préparation", ready: "Terminée", failed: "Échec · prochaine tentative automatique à 4 h", disabled: "Désactivée", unregistered: "Non inscrite" };
const parisDate = value => value ? new Date(value).toLocaleString("fr-FR", { timeZone: "Europe/Paris", dateStyle: "short", timeStyle: "short" }) : "—";
function selectedProfile() { return state.operations?.profiles.find(row => row.user_id === $("reader-profile").value); }
function operationControls() {
  const profile = selectedProfile();
  $("generate-cover").disabled = !profile || !state.operations?.llm_configured || state.operations?.preparing || state.generating;
  $("generate-cover").textContent = state.generating ? "Préparation en cours…" : "Générer une une maintenant";
  $("reader-profile").disabled = state.generating;
}
function renderSchedule() {
  const profile = selectedProfile(), parent = $("profile-schedule");
  parent.replaceChildren();
  if (!profile) parent.append(n("p", state.operations?.profiles.length ? "Choisissez un profil pour consulter sa planification ou préparer une édition." : "Aucun profil inscrit. Les lecteurs sont ajoutés lorsqu’ils choisissent leurs sujets dans Kiosque.", "muted"));
  else {
    const {request, schedule} = profile;
    parent.append(n("p", `Compte : ${profile.user_id}`, "small"));
    parent.append(n("p", request.profile.interests.map(interest => interest.topic).join(" · ")));
    parent.append(n("p", `${request.size} contenus · langues : ${request.profile.languages.join(", ") || "toutes"} · profil mis à jour le ${parisDate(profile.updated_at)}`, "small"));
    parent.append(n("p", `Préparation quotidienne : ${scheduleNames[schedule.status] || schedule.status} · prochaine échéance : ${parisDate(schedule.next_run_at)} (Paris)`));
    if (schedule.cover_id) parent.append(link("Ouvrir la trace de la dernière préparation quotidienne", `/admin/covers?id=${encodeURIComponent(schedule.cover_id)}`));
  }
  operationControls();
}
async function loadOperations() {
  try {
    // Profiles are paginated by the API. Keep every registered reader selectable.
    let data, profiles = [], offset = 0;
    do {
      data = await api(`/v1/admin/editions?limit=100&offset=${offset}`);
      profiles.push(...data.profiles); offset += data.profiles.length;
    } while (data.profiles.length === 100);
    state.operations = {...data, profiles};
    const selected = $("reader-profile").value;
    $("reader-profile").replaceChildren(new Option("Tous les lecteurs · historique", ""));
    for (const profile of profiles) {
      const topics = profile.request.profile.interests.map(interest => interest.topic.split(",")[0]).join(" / ");
      $("reader-profile").add(new Option(`${profile.user_id} · ${topics}`, profile.user_id));
    }
    $("reader-profile").value = selected;
    $("scheduler-health").textContent = data.daily_editions_enabled ? "Automatique · 4 h Paris" : "Automatique désactivée";
    $("model-health").textContent = !data.llm_configured ? "Modèles indisponibles : configurer OPENAI_API_KEY, SUMMARY_MODEL et EDITOR_MODEL sur le serveur." : data.preparing ? "Une couverture est actuellement en préparation." : "Modèles configurés · aucune préparation en cours sur ce serveur.";
    renderSchedule();
  } catch (e) {
    state.operations = null;
    $("scheduler-health").textContent = "État indisponible";
    operationControls();
    throw e;
  }
}
async function load(more = false, refreshDetail = true) {
  const seq = ++state.listSequence;
  $("error").hidden = true; $("reload").disabled = true; $("more").disabled = true;
  const params = new URLSearchParams({limit: 30, offset: more ? state.rows.length : 0});
  if ($("reader-profile").value) params.set("user_id", $("reader-profile").value);
  try {
    const rows = await api(`/v1/covers?${params}`);
    if (seq !== state.listSequence) return;
    state.rows = more ? [...state.rows, ...rows] : rows; $("more").hidden = rows.length < 30; renderHistory();
    if (!more && refreshDetail) {
      if (state.selected || rows[0]) await showCover(state.selected || rows[0].id);
      else $("cover-detail").replaceChildren(n("p", "Aucune édition pour ce profil.", "empty"));
    }
  } finally { if (seq === state.listSequence) { $("reload").disabled = false; $("more").disabled = false; } }
}
async function generate(event) {
  event.preventDefault();
  if ($("generate-cover").disabled || state.generating) return;
  const profile = selectedProfile();
  if (!profile) return;
  state.generating = true; operationControls();
  $("generation-notice").hidden = false;
  $("generation-notice").textContent = "Préparation en cours. Cela peut prendre jusqu’à cinq minutes. Gardez cette page ouverte ; aucune relance automatique ne sera effectuée.";
  $("error").hidden = true;
  let cover;
  try {
    cover = await api(`/v1/admin/readers/${encodeURIComponent(profile.user_id)}/covers`, {method: "POST"});
  } catch (e) {
    error(e);
    $("generation-notice").textContent = "La préparation n’a pas été confirmée. Actualisez l’historique avant de lancer une nouvelle tentative.";
  } finally { state.generating = false; operationControls(); }
  if (cover) {
    state.selected = cover.id;
    state.rows = [{...cover, item_count: cover.items.length, audit_version: cover.diagnostics?.version || 0}, ...state.rows.filter(row => row.id !== cover.id)];
    history.replaceState(null, "", `?id=${encodeURIComponent(cover.id)}`);
    renderHistory(); renderCover(cover);
    $("generation-notice").textContent = `Édition enregistrée : ${cover.title}. ${cover.items.length} contenus · ${statusNames[cover.status] || cover.status}.`;
    try { await Promise.all([load(false, false), loadOperations()]); }
    catch (e) { error(new Error(`L’édition est enregistrée. Actualisation incomplète : ${e.message}`)); }
  }
}
$("generation-form").addEventListener("submit", generate);
$("reader-profile").addEventListener("change", () => {
  state.selected = null; state.sequence++;
  history.replaceState(null, "", location.pathname);
  renderSchedule(); load().catch(error);
});
$("reload").addEventListener("click", () => Promise.all([load(), loadOperations()]).catch(error));
$("more").addEventListener("click", () => load(true).catch(error));
Promise.all([load(), loadOperations()]).catch(error);
setInterval(() => { if (!document.hidden && !state.generating) loadOperations().catch(error); }, 30_000);
