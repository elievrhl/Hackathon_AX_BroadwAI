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

export function articleImageUrl(item) {
  // Always use the local image service, never a URL supplied by an external page.
  if (!/^[a-zA-Z0-9_-]{1,100}$/.test(item.article_id || '')) return null;
  if (item.image_checked && !item.image) return null;
  return `/v1/articles/${encodeURIComponent(item.article_id)}/image?v=review-1`;
}

/** Keep the editor's order and section names; every item appears exactly once on the front page. */
export function adaptCover(raw) {
  if (!raw?.id || !Array.isArray(raw.items)) throw new Error('Réponse de couverture invalide.');
  const items = raw.items.map(item => ({
    id: item.article_id, title: item.title, originalTitle: item.title, coverId: item.cover_id || null,
    url: safeArticleUrl(item.url), source: item.source, publishedAt: item.published_at,
    imageUrl: articleImageUrl(item), imageAlt: item.image?.alt || '',
    section: item.selection_kind === 'exploration' ? 'Exploration' : item.section || 'À découvrir',
    reason: item.reason,
    exploration: item.selection_kind === 'exploration',
    explorationReason: item.exploration_reason || '',
    summary: item.brief?.summary || '', keyPoints: item.brief?.key_points || [],
    caveats: item.brief?.caveats || [], excerptOnly: item.extraction_status !== 'extracted',
    kind: item.reading_kind === 'evergreen' ? 'Lecture de fond'
      : item.reading_kind === 'research' ? 'Recherche' : 'Actualité',
    role: item.role,
    language: item.brief?.language,
    readingTimeMinutes: Number.isInteger(item.reading_time_minutes) && item.reading_time_minutes > 0
      ? item.reading_time_minutes : null,
  }));
  const focused = items.filter(item => !item.exploration);
  const exploration = items.filter(item => item.exploration);
  const explicitLayout = focused.some(item => item.role);
  const lead = explicitLayout ? focused.find(item => item.role === 'lead') || focused[0] : focused[0];
  const secondary = explicitLayout
    ? focused.filter(item => item !== lead && item.role === 'secondary').slice(0, 2) : focused.slice(1, 3);
  const briefs = explicitLayout
    ? focused.filter(item => item !== lead && item.role === 'brief').slice(0, 3) : focused.slice(3, 6);
  const featured = new Set([lead, ...secondary, ...briefs]);
  const sections = [...new Set(items.map(item => item.section))].map((label, index) => ({
    id: `section-${index}`, label, articles: items.filter(item => item.section === label),
  }));
  return {
    id: raw.id, userId: raw.user_id, title: raw.title, createdAt: raw.created_at,
    status: raw.status, warnings: raw.warnings || [], items, sections,
    lead, secondary, briefs, exploration,
    remainingSections: sections.map(section => ({
      ...section, articles: section.articles.filter(item => !item.exploration && !featured.has(item)),
    })).filter(section => section.articles.length),
  };
}

export function formatDate(value, long = false) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat('fr-FR', long
    ? { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }
    : { day: 'numeric', month: 'short', year: 'numeric' }).format(date);
}
