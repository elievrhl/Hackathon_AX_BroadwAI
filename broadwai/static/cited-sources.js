"use strict";

// Shared by article details and the cover audit. Model strings are always text nodes.
function appendCitedSources(parent, sources) {
  const section = document.createElement("section");
  section.className = "cited-sources";
  const heading = document.createElement("h4");
  heading.textContent = "Sources citées pertinentes";
  section.append(heading);
  const note = document.createElement("p");
  note.className = "muted small";
  note.textContent = sources === undefined
    ? "Sources non enregistrées pour cette ancienne fiche."
    : sources.length
      ? "Pistes retenues par le modèle pour approfondir le sujet."
      : "Aucune source citée jugée pertinente dans le contenu fourni.";
  section.append(note);
  if (sources?.length) {
    const list = document.createElement("ul");
    for (const source of sources) {
      const item = document.createElement("li");
      const name = document.createElement("strong");
      name.textContent = source.name;
      item.append(name);
      let url;
      try {
        const parsed = new URL(source.url);
        if (["http:", "https:"].includes(parsed.protocol) && !parsed.username && !parsed.password) url = parsed;
      } catch { /* A source can be named without a URL. */ }
      if (url) {
        const link = document.createElement("a");
        link.href = url.href;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = url.href;
        item.append(document.createTextNode(" · "), link);
      } else {
        item.append(document.createTextNode(" · URL non disponible"));
      }
      const relevance = document.createElement("p");
      relevance.textContent = source.relevance;
      const evidence = document.createElement("blockquote");
      evidence.textContent = source.evidence;
      item.append(relevance, evidence);
      list.append(item);
    }
    section.append(list);
  }
  parent.append(section);
}
