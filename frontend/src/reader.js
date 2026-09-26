export const TOPICS = [
  { id: 'tech', label: 'Tech & IA', short: 'Tech & IA', query: 'intelligence artificielle, développement logiciel, technology, AI' },
  { id: 'economy', label: 'Économie', short: 'Économie', query: 'économie, inflation, emploi, economics, economy' },
  { id: 'world', label: 'Monde & société', short: 'Monde', query: 'actualité générale, géopolitique, société, world news' },
  { id: 'science', label: 'Sciences', short: 'Sciences', query: 'sciences, recherche, science, research' },
  { id: 'climate', label: 'Climat & vivant', short: 'Climat', query: 'climat, biodiversité, climate, environment' },
  { id: 'culture', label: 'Culture & idées', short: 'Culture', query: 'culture, arts, ideas' },
  { id: 'history', label: 'Histoire', short: 'Histoire', query: 'histoire, archéologie, patrimoine, history, archaeology, heritage' },
  { id: 'philosophy', label: 'Philosophie', short: 'Philosophie', query: 'philosophie, éthique, pensée critique, philosophy, ethics, critical thinking' },
  { id: 'books', label: 'Livres & littérature', short: 'Livres', query: 'livres, littérature, écriture, books, literature, writing' },
  { id: 'cinema', label: 'Cinéma & séries', short: 'Cinéma', query: 'cinéma, séries, films, réalisation, cinema, television, filmmaking' },
  { id: 'music', label: 'Musique', short: 'Musique', query: 'musique, artistes, composition, music, musicians, songwriting' },
  { id: 'art', label: 'Art & design', short: 'Art & design', query: 'art, design, architecture, photographie, visual arts, photography' },
  { id: 'health', label: 'Santé & psychologie', short: 'Santé', query: 'santé, psychologie, neurosciences, health, psychology, neuroscience' },
  { id: 'sports', label: 'Sport', short: 'Sport', query: 'sport, athlètes, entraînement, sports, athletes, training' },
  { id: 'food', label: 'Cuisine & gastronomie', short: 'Cuisine', query: 'cuisine, gastronomie, cultures alimentaires, cooking, gastronomy, food culture' },
  { id: 'travel', label: 'Voyages & découvertes', short: 'Voyages', query: 'voyages, géographie, découverte de lieux, travel, geography, places' },
  { id: 'business', label: 'Entrepreneuriat', short: 'Entreprises', query: 'entrepreneuriat, entreprises, création de produits, entrepreneurship, startups, product development' },
  { id: 'education', label: 'Éducation', short: 'Éducation', query: 'éducation, pédagogie, apprentissage, education, teaching, learning' },
  { id: 'gaming', label: 'Jeux vidéo', short: 'Jeux vidéo', query: 'jeux vidéo, création de jeux, game design, video games, game development' },
  { id: 'space', label: 'Espace & astronomie', short: 'Espace', query: 'espace, astronomie, exploration spatiale, space, astronomy, space exploration' },
];

export const DEFAULT_PROFILE = {
  name: 'Lecteur', topics: ['tech', 'economy', 'world'], notes: '',
  level: 'intermediate', languages: ['fr', 'en'], size: 18,
};
export const STORAGE_KEY = 'kiosque.reader.v1';

export function normalizeProfile(data) {
  if (!data || typeof data.name !== 'string' || !data.name.trim() || !Array.isArray(data.topics)) return null;
  const topics = [...new Set(data.topics)].filter(id => TOPICS.some(topic => topic.id === id));
  if (!topics.length) return null;
  return {
    ...DEFAULT_PROFILE,
    name: data.name.trim().slice(0, 40), topics,
    notes: typeof data.notes === 'string' ? data.notes.slice(0, 500) : '',
    size: [15, 18, 20].includes(data.size) ? data.size : 18,
    languages: Array.isArray(data.languages) && data.languages.includes('en') ? ['fr', 'en'] : ['fr'],
    level: ['beginner', 'intermediate', 'expert'].includes(data.level) ? data.level : 'intermediate',
  };
}

export function toCoverRequest(profile, userId) {
  if (!userId) throw new Error('Identifiant local manquant.');
  const valid = normalizeProfile(profile);
  if (!valid) throw new Error('Choisissez au moins un sujet.');
  return {
    profile: {
      user_id: userId,
      interests: valid.topics.map((id, index) => ({
        topic: TOPICS.find(topic => topic.id === id).query, weight: index === 0 ? 3 : 2,
      })),
      languages: valid.languages, level: valid.level, notes: valid.notes,
    },
    size: valid.size, max_per_source: 3, discover_web: true, discover_sources: true,
  };
}

export function safeArticleUrl(value) {
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : null;
  } catch { return null; }
}

const KINDS = { news: 'Actualité', analysis: 'Analyse', tutorial: 'Guide', opinion: 'Opinion', research: 'Recherche', other: 'À découvrir' };

/** Keep the editor's order and section names; every item appears exactly once on the front page. */
export function adaptCover(raw) {
  if (!raw?.id || !Array.isArray(raw.items)) throw new Error('Réponse de couverture invalide.');
  const items = raw.items.map(item => ({
    id: item.article_id, title: item.headline || item.title, originalTitle: item.title,
    url: safeArticleUrl(item.url), source: item.source, publishedAt: item.published_at,
    section: item.section || 'À découvrir', reason: item.reason,
    summary: item.brief?.summary || '', keyPoints: item.brief?.key_points || [],
    caveats: item.brief?.caveats || [], excerptOnly: item.extraction_status !== 'extracted',
    kind: item.reading_kind === 'evergreen' ? 'Lecture de fond' : KINDS[item.brief?.content_type] || 'Article',
    language: item.brief?.language,
  }));
  const sections = [...new Set(items.map(item => item.section))].map((label, index) => ({
    id: `section-${index}`, label, articles: items.filter(item => item.section === label),
  }));
  return {
    id: raw.id, userId: raw.user_id, title: raw.title, createdAt: raw.created_at,
    status: raw.status, warnings: raw.warnings || [], items, sections,
    lead: items[0], secondary: items.slice(1, 3), briefs: items.slice(3, 6),
    remainingSections: sections.map(section => ({
      ...section, articles: section.articles.filter(item => items.indexOf(item) >= 6),
    })).filter(section => section.articles.length),
  };
}

export function formatDate(value, long = false) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat('fr-FR', long
    ? { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }
    : { day: 'numeric', month: 'short', year: 'numeric' }).format(date);
}
