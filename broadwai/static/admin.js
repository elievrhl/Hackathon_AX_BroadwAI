"use strict";
const $ = (id) => document.getElementById(id);
const sourceKindLabel = (kind) => ({ rss: "RSS / Atom", podcast: "Podcast", website: "Site web", hacker_news: "Hacker News" })[kind] || kind;
const state = { sources: [], offset: 0, total: 0, limit: 25, editing: null, busy: false, sequence: 0 };
const date = (value) => value ? new Date(value).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" }) : "—";
const node = (tag, text, cls) => {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (cls) item.className = cls;
  return item;
};
function link(label, url, cls) {
  const item = node("a", label, cls);
  try {
    const parsed = new URL(url);
    if (["http:", "https:"].includes(parsed.protocol)) item.href = parsed.href;
  } catch { /* malformed external URL remains inert */ }
  item.target = "_blank"; item.rel = "noopener noreferrer";
  return item;
}
function button(label, action, cls) {
  const item = node("button", label, cls);
  item.type = "button"; item.addEventListener("click", action); return item;
}
function notice(message, error = false) {
  $("notice").hidden = !message; $("notice").textContent = message;
  $("notice").className = error ? "error" : "";
}
async function api(url, options = {}) {
  if (options.method && !['GET', 'HEAD'].includes(options.method.toUpperCase())) {
    const session = await fetch('/v1/auth/session', { credentials: 'same-origin' }).then(response => response.json());
    options = { ...options, headers: { ...options.headers, 'X-Kiosque-CSRF': session.csrf_token } };
  }
  const response = await fetch(url, { ...options, headers: { "Content-Type": "application/json", ...options.headers } });
  if (!response.ok) {
    let data; try { data = await response.json(); } catch { data = {}; }
    const detail = Array.isArray(data.detail) ? data.detail.map((d) => `${d.loc?.at(-1) || "Champ"} : ${d.msg}`).join("\n") : data.detail;
    throw new Error(detail || `Erreur serveur (${response.status})`);
  }
  return response.status === 204 ? null : response.json();
}
function setBusy(value) {
  state.busy = value;
  document.querySelectorAll("button").forEach((b) => { if (!b.dataset.close) b.disabled = value; });
  if (!value) {
    $("collect-all").disabled = !state.sources.some((s) => s.enabled);
    $("previous").disabled = state.offset === 0;
    $("next").disabled = state.offset + state.limit >= state.total;
  }
}
async function loadSources() {
  state.sources = await api("/v1/sources");
  const selected = $("source-filter").value;
  $("source-filter").replaceChildren(new Option("Toutes les sources", ""));
  const container = $("source-list"); container.replaceChildren();
  $("stat-sources").textContent = state.sources.filter((s) => s.enabled).length;
  if (!state.sources.length) container.append(node("p", "Aucune source. Ajoutez un site web, un flux RSS ou Hacker News pour commencer.", "empty"));
  for (const source of state.sources) {
    $("source-filter").add(new Option(source.name, source.id));
    const card = node("article", undefined, "source-card");
    const title = node("div", undefined, "source-title");
    title.append(node("h3", source.name), node("span", source.enabled ? "Active" : "En pause", `tag${source.enabled ? "" : " inactive"}`));
    card.append(title, link(source.url, source.url, "source-url"));
    card.append(node("div", `${sourceKindLabel(source.kind)} · ${source.article_count} article(s) · limite ${source.limit_per_source}`, "source-meta"));
    card.append(node("div", source.last_collected_at ? `Dernière collecte : ${date(source.last_collected_at)}` : "Pas encore collectée", "source-meta"));
    if (source.last_report) {
      card.append(node("div", `${source.last_report.collected} article(s) trouvé(s) · ${source.last_report.errors.length} erreur(s)`, "source-meta"));
      if (source.last_report.errors.length) {
        const details = node("details"); details.append(node("summary", "Voir les erreurs"), node("pre", JSON.stringify(source.last_report.errors, null, 2))); card.append(details);
      }
    }
    const actions = node("div", undefined, "source-actions");
    actions.append(button("Collecter", () => collect(source.id)), button("Modifier", () => editSource(source)), button("Supprimer", () => removeSource(source), "danger"));
    card.append(actions); container.append(card);
  }
  $("source-filter").value = state.sources.some((s) => s.id === selected) ? selected : "";
  setBusy(state.busy);
}
async function loadStats() {
  const health = await api("/health");
  $("stat-articles").textContent = health.catalog.articles;
  $("stat-briefs").textContent = health.catalog.briefs;
  const schedule = await api("/v1/sources/collection-schedule");
  $("collection-schedule").textContent = schedule.enabled
    ? "Collecte automatique chaque jour à 3 h, heure de Paris · jusqu’à 50 contenus par source selon les disponibilités. Le serveur doit rester démarré."
    : "Collecte automatique désactivée.";
}
async function loadArticles() {
  const sequence = ++state.sequence;
  const params = new URLSearchParams({ offset: state.offset, limit: state.limit, q: $("search").value.trim() });
  if ($("source-filter").value) params.set("source_id", $("source-filter").value);
  if ($("status-filter").value) params.set("status", $("status-filter").value);
  const data = await api(`/v1/admin/articles?${params}`);
  if (sequence !== state.sequence) return;
  state.total = data.total; $("article-count").textContent = data.total;
  const container = $("article-list"); container.replaceChildren();
  if (!data.items.length) {
    const empty = node("div", undefined, "empty");
    empty.append(node("strong", "Aucun article à afficher"), node("span", "Lancez une collecte ou ajustez les filtres.")); container.append(empty);
  }
  for (const item of data.items) {
    const row = node("article", undefined, "article-row"); const info = node("div", undefined, "article-info");
    info.append(button(item.title, () => showArticle(item.id), "article-title"));
    const meta = node("div", undefined, "article-meta");
    meta.append(node("span", item.source, "article-domain"), node("span", `Collecté le ${date(item.collected_at)}`), node("span", item.extraction_status === "extracted" ? "Texte extrait" : "Extrait", `tag ${item.extraction_status}`));
    if (item.brief_count) meta.append(node("span", `${item.brief_count} fiche(s)`, "tag"));
    info.append(meta); row.append(info, button("Consulter →", () => showArticle(item.id))); container.append(row);
  }
  $("page-info").textContent = data.total ? `${state.offset + 1}–${Math.min(state.offset + state.limit, data.total)} sur ${data.total} articles` : "0 article";
  setBusy(state.busy);
}
async function refresh() {
  await Promise.all([loadSources(), loadStats(), loadProposals()]);
  await loadArticles();
}
async function loadProposals() {
  const proposals = await api("/v1/source-proposals");
  const container = $("proposal-list"); container.replaceChildren();
  if (!proposals.length) container.append(node("p", "Aucune source proposée pour le moment.", "empty"));
  for (const p of proposals) {
    const card = node("article", undefined, "source-card");
    card.append(node("h3", p.name), node("span", sourceKindLabel(p.kind || "rss"), "tag"), link(p.url, p.url), node("p", p.justification),
      node("p", `${date(p.created_at)} · ${p.status === "proposed" ? "À examiner" : p.status === "approved" ? "Approuvée" : "Refusée"}`, "muted"),
      link("Page à l’origine de la proposition ↗", p.discovered_from));
    if (p.status === "proposed") {
      const actions = node("div", undefined, "source-actions");
      actions.append(button("Approuver", () => reviewProposal(p.id, true)), button("Refuser", () => reviewProposal(p.id, false)));
      card.append(actions);
    }
    container.append(card);
  }
  setBusy(state.busy);
}
async function reviewProposal(id, approve) {
  setBusy(true);
  try {
    await api(`/v1/source-proposals/${id}/review`, {method: "POST", body: JSON.stringify({approve})});
    await refresh(); notice(approve ? "Source approuvée. Vous pouvez lancer sa collecte." : "Proposition refusée.");
  } catch (error) { notice(error.message, true); } finally { setBusy(false); }
}
function editSource(source = null) {
  state.editing = source?.id || null;
  const form = $("source-form"); form.reset();
  $("source-dialog-title").textContent = source ? "Modifier la source" : "Ajouter une source";
  form.elements.name.value = source?.name || "";
  form.elements.kind.value = source?.kind || "website";
  form.elements.url.value = source?.url || "";
  form.elements.limit_per_source.value = source?.limit_per_source || 50;
  form.elements.enabled.checked = source?.enabled ?? true;
  sourceKind(); $("form-error").textContent = ""; $("source-dialog").showModal();
}
function sourceKind() {
  const form = $("source-form"); const kind = form.elements.kind.value;
  const needsUrl = kind !== "hacker_news";
  form.elements.url.disabled = !needsUrl; form.elements.url.required = needsUrl; $("url-label").hidden = !needsUrl;
  $("url-caption").textContent = kind === "website" ? "URL du site ou de la rubrique" : "URL du flux";
  form.elements.url.placeholder = kind === "website" ? "https://exemple.com/blog" : "https://exemple.com/feed.xml";
  $("website-hint").hidden = kind !== "website";
}
async function saveSource(event) {
  event.preventDefault(); setBusy(true); $("form-error").textContent = "";
  const form = $("source-form");
  const body = { name: form.elements.name.value, kind: form.elements.kind.value, url: form.elements.url.value, enabled: form.elements.enabled.checked, limit_per_source: Number(form.elements.limit_per_source.value) };
  try {
    await api(state.editing ? `/v1/sources/${state.editing}` : "/v1/sources", { method: state.editing ? "PUT" : "POST", body: JSON.stringify(body) });
    $("source-dialog").close(); await loadSources(); notice("Source enregistrée.");
  } catch (error) { $("form-error").textContent = error.message; notice(error.message, true); }
  finally { setBusy(false); }
}
async function removeSource(source) {
  if (!confirm(`Supprimer « ${source.name} » de la liste ? Les articles déjà collectés seront conservés.`)) return;
  setBusy(true);
  try { await api(`/v1/sources/${source.id}`, { method: "DELETE" }); state.offset = 0; await refresh(); notice("Source supprimée. Les articles sont conservés."); }
  catch (error) { notice(error.message, true); } finally { setBusy(false); }
}
async function collect(id = null) {
  setBusy(true); notice("Collecte en cours… Les articles seront affichés à la fin de l’opération.");
  try {
    const report = await api(id ? `/v1/sources/${id}/collect` : "/v1/sources/collect", { method: "POST" });
    state.offset = 0; await refresh();
    const count = report.results.reduce((n, r) => n + r.collected, 0);
    const errors = report.results.reduce((n, r) => n + r.errors.length, 0);
    notice(`Collecte terminée : ${report.results.length} source(s), ${count} article(s) trouvé(s), déjà connus compris.${errors ? ` ${errors} erreur(s) : consultez les sources concernées.` : ""}`, errors > 0);
  } catch (error) { notice(error.message, true); } finally { setBusy(false); }
}
async function showArticle(id) {
  const container = $("article-detail"); container.replaceChildren(node("h2", "Chargement…"));
  $("article-dialog").showModal();
  try {
    const data = await api(`/v1/admin/articles/${id}`); const a = data.article;
    container.replaceChildren(); const title = node("h2", a.title); title.id = "detail-title";
    container.append(title, link("Ouvrir l’article original ↗", a.url, "detail-link"));
    const metadata = node("dl");
    for (const [label, value] of [["URL", a.url], ["Domaine", a.source], ["Source(s) de collecte", data.sources.map((s) => s.name).join(", ") || "Collecte directe / source supprimée"], ["Publication", date(a.published_at)], ["Collecte", date(a.collected_at)], ["Langue", a.language || "Non renseignée"], ["Contenu", a.extraction_status === "extracted" ? "Texte extrait" : "Extrait uniquement"], ["Identifiant", a.id]]) metadata.append(node("dt", label), node("dd", value));
    container.append(metadata);
    for (const [label, text] of [["Extrait", a.excerpt], ["Texte extrait", a.text]]) {
      const section = node("section", undefined, "detail-section"); section.append(node("h3", label));
      if (label === "Texte extrait" && text) {
        const expandable = node("details");
        expandable.append(node("summary", `Afficher le texte (${text.length.toLocaleString("fr-FR")} caractères)`), node("p", text, "prose"));
        section.append(expandable);
      } else {
        section.append(node("p", text || "Non disponible. Le texte est extrait à la demande lors de la préparation d’une couverture.", "prose"));
      }
      container.append(section);
    }
    const section = node("section", undefined, "detail-section"); section.append(node("h3", `Fiches synthétiques (${data.briefs.length})`));
    if (!data.briefs.length) section.append(node("p", "Aucune fiche générée pour cet article. La collecte seule ne lance pas de résumé.", "muted"));
    for (const brief of data.briefs) {
      const b = brief.payload; const card = node("div", undefined, "brief-card");
      card.append(node("span", brief.current_content ? "Contenu actuel" : "Ancienne version du contenu", "tag"), node("p", brief.version, "muted"), node("p", b.summary, "prose"));
      const points = node("ul"); for (const point of b.key_points) points.append(node("li", point)); card.append(points);
      card.append(node("p", `${b.topics.join(" · ")} · ${b.content_type} · ${b.level} · ${b.language}`, "muted"));
      for (const caveat of b.caveats) card.append(node("p", caveat, "error"));
      appendCitedSources(card, b.cited_sources);
      section.append(card);
    }
    container.append(section); const raw = node("details"); raw.append(node("summary", "Voir toutes les données JSON"), node("pre", JSON.stringify(data, null, 2))); container.append(raw);
  } catch (error) { container.replaceChildren(node("h2", "Chargement impossible"), node("p", error.message, "error")); }
}
$("add-source").addEventListener("click", () => editSource());
$("source-form").addEventListener("submit", saveSource);
$("source-form").elements.kind.addEventListener("change", sourceKind);
$("collect-all").addEventListener("click", () => collect());
$("refresh").addEventListener("click", () => refresh().catch((error) => notice(error.message, true)));
$("filters").addEventListener("submit", (event) => { event.preventDefault(); state.offset = 0; loadArticles().catch((error) => notice(error.message, true)); });
for (const id of ["source-filter", "status-filter"]) $(id).addEventListener("change", () => { state.offset = 0; loadArticles().catch((error) => notice(error.message, true)); });
$("previous").addEventListener("click", () => { state.offset = Math.max(0, state.offset - state.limit); loadArticles().catch((error) => notice(error.message, true)); });
$("next").addEventListener("click", () => { state.offset += state.limit; loadArticles().catch((error) => notice(error.message, true)); });
document.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => $(b.dataset.close).close()));
refresh().catch((error) => notice(`Impossible de charger les données : ${error.message}`, true));
