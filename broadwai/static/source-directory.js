"use strict";

function fold(value) {
  return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}
function selectSources(sources, filters) {
  const query = fold(filters.query).trim();
  return sources.filter(source => {
    if (filters.format !== "all" && source.format !== filters.format) return false;
    if (filters.topic && !source.topics.includes(filters.topic)) return false;
    if (filters.language && !source.languages.includes(filters.language)) return false;
    if (filters.publisher && source.publisher !== filters.publisher) return false;
    if (filters.status === "imported" && !source.imported) return false;
    if (filters.status === "selected" && !source.selected) return false;
    if (filters.status === "excluded" && (source.selected || source.imported)) return false;
    return !query || fold([source.name, source.publisher, source.description, ...source.topicLabels].join(" ")).includes(query);
  }).sort((a, b) => a.name.localeCompare(b.name, "fr"));
}
function csvCell(value) {
  let text = String(value ?? "");
  if (/^[\s]*[=+@-]/.test(text)) text = "'" + text;
  return '"' + text.replaceAll('"', '""') + '"';
}
function sourceCSV(sources) {
  const rows = [["Source", "Éditeur", "Sujets", "Langues", "Format", "Importée", "Contenus", "Pourquoi cette source", "Page officielle", "Provenance", "Vérification", "URL de collecte"]];
  for (const source of sources) rows.push([source.name, source.publisher, source.topicLabels.join(", "), source.languages.join(", "), source.format, source.imported ? "Oui" : "Non", source.articleCount ?? "", source.description, source.homepage, source.provenance, source.status, source.url]);
  return "\uFEFF" + rows.map(row => row.map(csvCell).join(";")).join("\r\n");
}
function safeURL(value) {
  try { const url = new URL(value); return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? url.href : null; } catch { return null; }
}
if (typeof module !== "undefined" && module.exports) module.exports = { selectSources, sourceCSV, safeURL };

if (typeof document !== "undefined") {
  const data = window.SOURCE_DIRECTORY;
  const $ = id => document.getElementById(id);
  const state = { format: "all", query: "", topic: "", language: "", status: "imported", publisher: "", page: 0, view: "cards" };
  const requestedFormat = new URLSearchParams(location.search).get("format");
  if (["youtube", "podcast", "article"].includes(requestedFormat)) state.format = requestedFormat;
  const pageSize = 24;
  const formatNames = { article: "Article", youtube: "YouTube", podcast: "Podcast" };
  const statuses = { ok: "Flux vérifié", failed: "Non exploitable", stale: "Flux ancien", duplicate: "Doublon écarté", review_required: "À revoir", pending: "À vérifier", legacy: "Source préexistante" };
  const number = value => value.toLocaleString("fr-FR");
  const date = value => value ? new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium" }).format(new Date(value)) : "—";
  const el = (tag, text, cls) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (cls) node.className = cls; return node; };
  function link(label, url) { const a = el("a", label); const safe = safeURL(url); if (safe) a.href = safe; a.target = "_blank"; a.rel = "noopener noreferrer"; return a; }
  function button(label, action) { const b = el("button", label); b.type = "button"; b.addEventListener("click", action); return b; }
  function sourceState(source) { return source.imported ? `${source.articleCount ?? 0} contenu${source.articleCount === 1 ? "" : "s"} · ${source.enabled ? "Active" : "En pause"}` : source.selected ? "Vérifiée · à importer" : statuses[source.status] || "Non retenue"; }
  function showDetail(source) {
    const target = $("detail-content"); target.replaceChildren();
    target.append(el("p", formatNames[source.format], "eyebrow"), el("h2", source.name), el("p", `${source.publisher} · ${source.languages.map(l => l === "fr" ? "Français" : "Anglais").join(" / ")}`, "publisher"));
    target.querySelector("h2").id = "detail-title";
    const chips = el("div", undefined, "chips"); source.topicLabels.forEach(topic => chips.append(el("span", topic, "chip"))); target.append(chips);
    const links = el("div", undefined, "source-links");
    if (safeURL(source.homepage)) links.append(link(source.format === "youtube" ? "Voir la chaîne ↗" : source.format === "podcast" ? "L’émission officielle ↗" : "Visiter la publication ↗", source.homepage));
    if (source.provenance && safeURL(source.provenance)) links.append(link("Vérifier la provenance ↗", source.provenance));
    target.append(links, el("h3", "Pourquoi cette source ?"), el("p", source.description));
    if (source.qualityNotes?.length) { const list = el("ul"); source.qualityNotes.filter(note => note !== source.description).forEach(note => list.append(el("li", note))); target.append(list); }
    target.append(el("h3", "Provenance & contexte"), el("p", source.provenanceNote || source.editorialNote), el("p", source.accessNote));
    if (source.reviewScope) target.append(el("h3", "Ce qui a été examiné"), el("p", source.reviewScope));
    if (source.format === "youtube") target.append(el("p", "Le catalogue utilise les titres et descriptions publiés par la chaîne. Une description ne constitue pas une transcription de la vidéo."));
    if (source.format === "podcast") target.append(el("p", "Les épisodes proviennent du flux public de l’émission. Les résumés disponibles sont ceux publiés par le producteur ; aucun épisode n’est généré par Kiosque."));
    target.append(el("h3", "Dans Kiosque"), el("p", sourceState(source)), el("p", `${statuses[source.status] || source.status} · contrôle du ${date(source.checkedAt)}${source.latestAt ? ` · dernière publication observée : ${date(source.latestAt)}` : ""}`));
    if (source.error) target.append(el("p", source.error));
    if (source.samples?.length) { target.append(el("h3", "Quelques publications du flux")); const list = el("ul"); source.samples.slice(0,3).forEach((url, index) => { const li = el("li"); li.append(link(source.sampleTitles?.[url] || `Ouvrir la publication ${index + 1} ↗`, url)); list.append(li); }); target.append(list); }
    const tech = el("details"); tech.append(el("summary", "Adresse du flux pour la collecte"), el("p", source.url, "technical")); target.append(tech);
    $("detail").showModal();
  }
  function card(source) {
    const item = el("article", undefined, "source-card"); const top = el("div", undefined, "card-top");
    top.append(el("span", source.publisher.replace(/^(The|Le|La|Les) /i, "").slice(0,2).toUpperCase(), "monogram"), el("span", `${formatNames[source.format]} · ${source.languages.join(" / ").toUpperCase()}`, `format ${source.format}`));
    item.append(top, el("h2", source.name), el("p", source.publisher, "publisher"), el("p", source.description, "description"));
    const chips = el("div", undefined, "chips"); source.topicLabels.slice(0,3).forEach(topic => chips.append(el("span", topic, "chip"))); item.append(chips);
    const bottom = el("div", undefined, "card-bottom"); bottom.append(el("span", sourceState(source), `state${source.selected ? "" : " excluded"}`), button("Voir la fiche ↗", () => showDetail(source))); item.append(bottom); return item;
  }
  function table(sources) {
    const wrap = el("div", undefined, "table-wrap"), table = el("table"), head = el("thead"), row = el("tr");
    ["Source / éditeur", "Sujets", "Langue", "Format", "Dans Kiosque"].forEach(label => row.append(el("th", label))); head.append(row); table.append(head);
    const body = el("tbody"); for (const source of sources) { const row = el("tr"), title = el("td"); title.append(button(source.name, () => showDetail(source)), el("p", source.publisher, "publisher")); row.append(title, el("td", source.topicLabels.join(", ")), el("td", source.languages.join(" / ").toUpperCase()), el("td", formatNames[source.format]), el("td", sourceState(source))); body.append(row); } table.append(body); wrap.append(table); return wrap;
  }
  function render() {
    const sources = selectSources(data.sources, state); const maxPage = Math.max(0, Math.ceil(sources.length / pageSize) - 1); state.page = Math.min(state.page, maxPage);
    const visible = sources.slice(state.page * pageSize, (state.page + 1) * pageSize); const target = $("results"); target.className = state.view; target.replaceChildren();
    if (!sources.length) target.append(el("p", "Aucune source ne correspond à ces filtres. Essayez un autre sujet ou réinitialisez la recherche.", "empty"));
    else if (state.view === "cards") visible.forEach(source => target.append(card(source))); else target.append(table(visible));
    const publisherCount = new Set(sources.map(source => source.publisher)).size;
    $("result-count").textContent = state.format === "youtube" ? `${number(sources.length)} chaîne${sources.length === 1 ? "" : "s"} YouTube` : `${number(sources.length)} source${sources.length === 1 ? "" : "s"} · ${number(publisherCount)} éditeur${publisherCount === 1 ? "" : "s"} identifié${publisherCount === 1 ? "" : "s"}`;
    $("page-info").textContent = `Page ${state.page + 1} / ${maxPage + 1}`; $("previous").disabled = state.page === 0; $("next").disabled = state.page >= maxPage; $("download").disabled = !sources.length;
    document.querySelectorAll("[data-format]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.format === state.format)));
    const note = $("format-note"); note.replaceChildren(); note.hidden = !["youtube", "podcast"].includes(state.format);
    if (state.format === "youtube") note.append(el("strong", "Des chaînes choisies. Des raisons consultables."), el("p", "Cours, recherche, enquêtes, collections et savoir-faire : chaque fiche présente la provenance officielle, les motifs du choix, les exemples examinés et les limites. Plusieurs chaînes peuvent relever du même organisme."));
    if (state.format === "podcast") note.append(el("strong", "Des émissions, avec leur producteur."), el("p", "La première sélection réunit six émissions de Radio France : quatre de France Culture, deux de France Inter. Ouvrez une fiche pour retrouver la page de l’émission, son flux officiel et les raisons du choix."));
  }
  function stats() {
    const imported = data.sources.filter(s => s.imported); $("total").textContent = number(imported.length); $("publishers").textContent = number(new Set(imported.map(s => s.publisherDomain).filter(Boolean)).size); $("videos").textContent = imported.filter(s => s.format === "youtube").length; $("podcasts").textContent = imported.filter(s => s.format === "podcast").length;
  }
  if (!data) { $("results").append(el("p", "L’annuaire n’a pas pu être chargé. Réessayez dans un instant.", "empty")); }
  else {
    data.topics.forEach(topic => $("topic").add(new Option(topic.label, topic.id)));
    [...new Set(data.sources.map(s => s.publisher))].sort((a,b) => a.localeCompare(b,"fr")).forEach(name => $("publisher").add(new Option(name, name)));
    $("updated").textContent = `Sélection du ${date(data.generatedAt)}`;
    $("live-status").textContent = `État enregistré le ${date(data.generatedAt)}. Les compteurs de contenus concernent le catalogue de Kiosque.`;
    for (const id of ["query", "topic", "language", "status", "publisher", "view"]) $(id).addEventListener(id === "query" ? "input" : "change", event => { state[id] = event.target.value; state.page = 0; render(); });
    $("filters").addEventListener("submit", e => e.preventDefault());
    document.querySelectorAll("[data-format]").forEach(b => b.addEventListener("click", () => { state.format = b.dataset.format; state.page = 0; render(); }));
    $("reset").addEventListener("click", () => { Object.assign(state, { format:"all", query:"", topic:"", language:"", publisher:"", status:"imported", page:0 }); ["query","topic","language","publisher","status"].forEach(id => $(id).value = state[id]); render(); });
    $("previous").addEventListener("click", () => { state.page--; render(); $("results").scrollIntoView({block:"start"}); });
    $("next").addEventListener("click", () => { state.page++; render(); $("results").scrollIntoView({block:"start"}); });
    $("download").addEventListener("click", () => { const url = URL.createObjectURL(new Blob([sourceCSV(selectSources(data.sources,state))],{type:"text/csv;charset=utf-8"})); const a = el("a"); a.href = url; a.download = "sources-kiosque.csv"; a.click(); setTimeout(() => URL.revokeObjectURL(url),1000); });
    $("detail").querySelector(".close").addEventListener("click", () => $("detail").close());
    stats(); render();
    if (["http:","https:"].includes(location.protocol)) {
      fetch("/v1/source-directory").then(response => { if (!response.ok) throw new Error("unavailable"); return response.json(); }).then(rows => {
        const current = new Map(rows.map(row => [`${row.kind}|${row.url}`, row]));
        data.sources.forEach(source => { const live = current.get(`${source.kind}|${source.url}`); source.imported = Boolean(live); source.articleCount = live?.article_count ?? 0; source.enabled = live?.enabled ?? false; });
        $("live-status").textContent = "État du site actualisé à l’ouverture · les contenus et activations proviennent du catalogue local."; stats(); render();
      }).catch(() => { $("live-status").textContent = `Serveur indisponible : état enregistré le ${date(data.generatedAt)}. Les liens et filtres restent accessibles.`; });
    }
  }
}
