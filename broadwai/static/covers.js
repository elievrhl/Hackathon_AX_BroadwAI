"use strict";
const $ = id => document.getElementById(id);
const state = {rows: [], selected: new URLSearchParams(location.search).get("id"), sequence: 0};
const n = (tag, text, cls) => { const e = document.createElement(tag); if(text !== undefined) e.textContent = text; if(cls) e.className=cls; return e; };
const fmt = value => value === null || value === undefined ? "Non enregistré" : Number(value).toLocaleString("fr-FR", {maximumFractionDigits: 3});
const date = value => value ? new Date(value).toLocaleString("fr-FR") : "Date inconnue";
function link(label, url) { const a=n("a",label); try {const u=new URL(url,location.origin); if(["https:","http:"].includes(u.protocol)) a.href=u.href;} catch {} a.target="_blank"; a.rel="noopener noreferrer"; return a; }
async function api(url) { const r=await fetch(url); if(!r.ok) throw new Error(`Chargement impossible (${r.status})`); return r.json(); }
function error(e) {$("error").hidden=false; $("error").textContent=e.message;}
function jsonDetails(label, data) {const d=n("details"); d.append(n("summary",label),n("pre",JSON.stringify(data,null,2))); return d;}
function section(parent, label, opened=false) { const d=n("details",undefined,"section-details"); d.open=opened; d.append(n("summary",label)); parent.append(d); return d; }
function table(parent, columns, rows) { const wrap=n("div",undefined,"table-scroll"), t=n("table"), head=n("tr"); for(const c of columns) head.append(n("th",c)); const thead=n("thead"); thead.append(head); t.append(thead); const body=n("tbody"); for(const cells of rows){const r=n("tr"); for(const cell of cells){const td=n("td"); td.append(cell instanceof Node ? cell : document.createTextNode(String(cell))); r.append(td);} body.append(r);} t.append(body); wrap.append(t); parent.append(wrap); }
const judgment = value => value === undefined ? "Non enregistré" : value ? "Oui" : "Non";
function picksTable(parent, picks, lookup) {
  table(parent, ["Article", "Rubrique", "Score / 100", "Contexte respecté", "Lecture de fond", "Exploration", "Intérêt"],
    picks.map(p => [lookup.get(p.article_id)?.title || p.article_id, p.section, p.score,
      judgment(p.matches_profile), judgment(p.evergreen), p.exploration ? p.exploration_reason : "—", p.reason]));
}
const labels = {catalog_ranked:"Classement du catalogue",shortlist:"Présélection diversifiée",candidate_prepare:"Préparation d’un article",candidate_skipped:"Article écarté",extract_requested:"Extraction demandée",extract_completed:"Texte extrait",extract_failed:"Échec d’extraction",summary_requested:"Résumé demandé",summary_completed:"Résumé reçu",summary_failed:"Échec du résumé",summary_cache_hit:"Fiche réutilisée",candidate_ready:"Article prêt pour le rédacteur",editor_requested:"Appel du rédacteur",editor_decision:"Décision du rédacteur",editor_failed:"Échec du rédacteur",validation:"Validation de la sélection",tool_requested:"Outil demandé",tool_result:"Résultat d’outil",cover_completed:"Couverture enregistrée"};
function candidate(parent, c, selected, summaryState) {const card=n("details",undefined,"candidate-card"); card.append(n("summary",`${selected ? "✓ Retenu · " : ""}${c.title}`)); card.append(link("Article original ↗",c.url),n("p",`${c.source} · ${date(c.published_at)} · ${c.extraction_status}`,"small")); if(c.score !== undefined) card.append(n("p",`Score BM25 + fraîcheur : ${fmt(c.score)} · Intérêts : ${c.matched_interests?.join(", ") || "—"}`,"small")); if(summaryState)card.append(n("p",summaryState,"small")); if(c.reason) card.append(n("p",`Pourquoi : ${c.reason}`)); card.append(n("p",c.brief.summary,"prose")); const points=n("ul"); for(const p of c.brief.key_points) points.append(n("li",p)); card.append(points); for(const caveat of c.brief.caveats) card.append(n("p",caveat,"small")); parent.append(card);}
async function showCover(id) {
  const seq=++state.sequence; state.selected=id; history.replaceState(null,"",`?id=${encodeURIComponent(id)}`); renderHistory(); $("cover-detail").replaceChildren(n("p","Chargement…","empty"));
  const c=await api(`/v1/covers/${encodeURIComponent(id)}`); if(seq!==state.sequence)return;
  const parent=$("cover-detail"), audit=c.diagnostics || {}, events=audit.events || [], calls=c.usage.model_calls || [], selected=new Set(c.items.map(i=>i.article_id)); parent.replaceChildren(n("h2",c.title),n("p",`${date(c.created_at)} · ${c.status} · ${c.items.length} articles`,"muted"));
  const stats=n("div",undefined,"inspection-stats"); for(const s of [`${fmt(c.usage.input_tokens)} tokens entrants`,`${fmt(c.usage.output_tokens)} sortants`,`${c.usage.calls?.summary || 0} appels résumé`,`${c.usage.summary_cache_hits || 0} fiches réutilisées`,`${c.usage.calls?.editor || 0} appels rédacteur`,`${c.usage.calls?.hosted_web_calls || 0} outils web hébergés`]) stats.append(n("span",s)); parent.append(stats);
  parent.append(n("p","Les tokens ne sont pas une facture. Les tokens d’entrée mis en cache restent inclus dans le total entrant.","small"));
  parent.append(link("Ouvrir dans Kiosque ↗",`/reader/?cover=${encodeURIComponent(c.id)}`));
  if(c.usage.cost?.estimated_usd !== null && c.usage.cost?.estimated_usd !== undefined) parent.append(n("p",`Coût estimé : ${fmt(c.usage.cost.estimated_usd*100)} centimes de dollar US · ${c.usage.cost.basis}`,"small"));
  if(!audit.version) parent.append(n("p","Trace ancienne et partielle : les outils, erreurs, articles finaux et totaux sont disponibles. Les scores, la shortlist exacte, les fiches écartées et le détail des appels n’ont pas été enregistrés à l’époque. Ils ne sont pas recalculés a posteriori.","legacy-note"));
  if(audit.request) {const config=section(parent,"Profil et paramètres utilisés"); config.append(jsonDetails("Requête",audit.request),jsonDetails("Limites",audit.settings));}
  if(audit.editorial_intent) {const intent=section(parent,"Besoins du lecteur et couverture"); intent.append(jsonDetails("Besoins et contraintes",audit.editorial_intent),jsonDetails("Besoins non couverts",audit.uncovered_needs || []));}
  if(audit.search_history) {const memory=section(parent,"Recherches et articles écartés"); memory.append(jsonDetails("Recherches",audit.search_history),jsonDetails("Rejets",audit.rejected || []));}
  if(c.usage.remaining_tokens !== undefined) parent.append(n("p",`Budget disponible : ${fmt(c.usage.remaining_tokens)} tokens · réserve finale : ${fmt(c.usage.final_token_reserve)} · réservations non réconciliées : ${fmt(c.usage.unsettled_token_reservations)}`,"small"));
  if(audit.editorial_plan){
    const plan=section(parent,"Choix éditorial avant les résumés",true), previews=events.find(e=>e.kind==="editorial_preview")?.candidates || [], lookup=new Map(previews.map(a=>[a.article_id,a]));
    plan.append(n("p",`Rubriques : ${audit.editorial_plan.sections.join(" · ")}`),n("p","Le score éditorial est une appréciation du modèle sur titres et extraits, pas une mesure objective de qualité.","small"));
    picksTable(plan, audit.editorial_plan.picks, lookup);
    for(const gap of audit.editorial_plan.gaps)plan.append(n("p",`Manque détecté : ${gap}`));
    plan.append(jsonDetails(`Titres et extraits examinés · ${previews.length}`,previews));
  }
  const screens = events.filter(e => e.kind === "search_screen_completed");
  if (screens.length) {
    const checks = section(parent, "Pertinence des résultats de recherche");
    screens.forEach((event, index) => {
      const request = events.filter(e => e.kind === "search_screen_requested" && e.sequence < event.sequence).at(-1);
      const step = section(checks, `Filtre ${index + 1} · ${request?.query || "Recherche"}`);
      picksTable(step, event.plan.picks, new Map((request?.candidates || []).map(a => [a.article_id, a])));
    });
  }
  const final=section(parent,`Couverture finale · ${c.items.length} articles`,true); for(const i of c.items)candidate(final,i,true);
  const ranking=section(parent,"Articles présélectionnés et scores",Boolean(audit.version)); const stages=events.filter(e=>e.kind==="shortlist");
  if(!stages.length) ranking.append(n("p","Présélection et scores non enregistrés pour cette couverture.","muted"));
  stages.forEach((stage,index)=>{const d=section(ranking,`Passage ${index+1} · ${stage.shortlisted_ids.length} présélectionnés / ${stage.ranked_count} classés`,index===0); d.append(n("p","Score lexical relatif à ce corpus, pas une probabilité. La diversification peut retenir un article moins bien classé. Détail : intérêts pondérés + bonus de requête + fraîcheur.","small")); const ids=new Set(stage.shortlisted_ids); table(d,["Article","Score","Présélection","Détail"],stage.ranked.map(r=>[link(r.title,r.url),fmt(r.score),ids.has(r.article_id)?"Oui":"Non",jsonDetails("Composantes",r.score_details)])); if(stage.ranked_count>stage.ranked.length)d.append(n("p",`Affichage limité à ${stage.ranked.length} lignes enregistrées sur ${stage.ranked_count}.`,"small"));});
  const briefs=section(parent,`Fiches présentées au rédacteur · ${audit.candidates?.length ?? "inconnu"}`);
  if(audit.candidates) for(const item of audit.candidates){const match=events.filter(e=>e.article_id===item.article_id && ["summary_cache_hit","summary_completed"].includes(e.kind)).at(-1); candidate(briefs,item,selected.has(item.article_id),match?.kind==="summary_cache_hit"?"Réutilisée depuis le cache":"Générée pendant cet essai");} else briefs.append(n("p","Seules les fiches des articles finaux sont conservées pour cet ancien essai.","muted"));
  const timeline=section(parent,"Outils, décisions et validations",true);
  for(const event of c.trace){const d=n("details",undefined,`event${event.outcome.error || event.outcome.errors ? " error-event":""}`); d.append(n("summary",`Étape ${event.step} · ${event.action}`),n("p",event.justification)); for(const u of event.outcome.discovered_links || []){const row=n("p");row.append(link(u.title,u.url));d.append(row);} d.append(n("pre",JSON.stringify(event.outcome,null,2))); timeline.append(d);}
  const billing=section(parent,`Appels aux modèles · ${calls.length || "détail indisponible"}`); if(calls.length)table(billing,["Rôle / modèle","État / durée","Entrée / cache / sortie","Détail"],calls.map(call=>[`${call.kind} · ${call.model}`,`${call.status} · ${fmt(call.duration_ms)} ms`,`${fmt(call.usage?.input_tokens)} / ${fmt(call.usage?.cached_input_tokens)} / ${fmt(call.usage?.output_tokens)}`,jsonDetails(call.title || call.query || "Voir l’appel",call)])); else billing.append(n("p","Les anciens essais n’enregistrent que les totaux ; aucune ventilation de coût par modèle ne peut être garantie.","muted"));
  const journal=section(parent,`Journal complet · ${events.length} événements`); for(const e of events){const d=n("details",undefined,`event${e.error ? " error-event":""}`); d.append(n("summary",`${e.sequence} · ${fmt(e.elapsed_ms/1000)} s · ${labels[e.kind] || e.kind}${e.title?" · "+e.title:""}`),n("pre",JSON.stringify(e,null,2))); journal.append(d);}
  if(c.warnings.length){parent.append(n("h3","Avertissements")); for(const w of c.warnings)parent.append(n("p",w,"error"));} parent.append(jsonDetails("Toutes les données enregistrées",c),link("Ouvrir le JSON de la couverture",`/v1/covers/${c.id}`));
}
function renderHistory(){const list=$("covers-list");list.replaceChildren(); if(!state.rows.length)list.append(n("p","Aucune couverture enregistrée.","empty")); for(const c of state.rows){const b=n("button",c.title,`history-item${state.selected===c.id?" active":""}`);b.append(n("small",`${date(c.created_at)} · ${c.status} · ${c.item_count} articles`),n("small",Number(c.audit_version)?"Journal détaillé":"Trace ancienne, partielle"));b.addEventListener("click",()=>showCover(c.id).catch(error));list.append(b);}}
async function load(more=false){$("error").hidden=true; const rows=await api(`/v1/covers?limit=30&offset=${more?state.rows.length:0}`); state.rows=more?[...state.rows,...rows]:rows;$("more").hidden=rows.length<30;renderHistory();if(!more && (state.selected || rows[0]))await showCover(state.selected || rows[0].id);}
$("reload").addEventListener("click",()=>load().catch(error));$("more").addEventListener("click",()=>load(true).catch(error));load().catch(error);
