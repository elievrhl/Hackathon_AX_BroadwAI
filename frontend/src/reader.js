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
    discover_videos: true, max_videos: 3,
    discover_podcasts: true, max_podcasts: 2,
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
  // Let the server retry old misses with its bounded negative cache.
  return `/v1/articles/${encodeURIComponent(item.article_id)}/image?v=images-4`;
}

export function mediaDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds <= 0) return '';
  const value = Math.max(1, Math.floor(seconds));
  const hours = Math.floor(value / 3600), minutes = Math.floor(value / 60) % 60, remainder = value % 60;
  return [hours && `${hours} h`, minutes && `${minutes} min`, remainder && `${remainder} s`].filter(Boolean).join(' ');
}

function originalVideo(item) {
  // Old editions keep their IDs and feedback while linking to the original video.
  let url;
  try { url = new URL(item.url); } catch { return item; }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.port
    || !['recapcraft.com', 'www.recapcraft.com'].includes(url.hostname)) return item;
  const match = url.pathname.match(/^\/v\/([A-Za-z0-9_-]{11})\/?$/);
  if (!match) return item;
  const media = item.media?.video_id === match[1] ? item.media : {};
  return {
    ...item, format: 'video', url: `https://www.youtube.com/watch?v=${match[1]}`, source: 'www.youtube.com',
    title: media.original_title || item.title.replace(/\s*-\s*Summary(?: & Key Points)?\s*$/i, ''),
    media, published_at: media.original_published_at || null,
    reading_time_minutes: null, extraction_status: 'excerpt',
    brief: { ...item.brief, summary: media.original_description || '', key_points: [],
      caveats: [media.original_description ? 'Présentation issue de la description de la vidéo originale, sans transcription.' : 'Consultez la vidéo originale sur YouTube.'] },
  };
}

export function contentCount(items) {
  const videos = items.filter(item => item.format === 'video').length;
  const podcasts = items.filter(item => item.format === 'podcast').length;
  const articles = items.length - videos - podcasts;
  return [articles && `${articles} article${articles > 1 ? 's' : ''}`, videos && `${videos} vidéo${videos > 1 ? 's' : ''}`, podcasts && `${podcasts} podcast${podcasts > 1 ? 's' : ''}`].filter(Boolean).join(' · ') || '0 article';
}

export function contentAction(format) {
  return format === 'podcast' ? 'Écouter l’épisode' : format === 'video' ? 'Voir sur YouTube' : 'Lire l’article';
}

/** Keep the editor's order and section names; every item appears exactly once on the front page. */
export function adaptCover(raw) {
  if (!raw?.id || !Array.isArray(raw.items)) throw new Error('Réponse de couverture invalide.');
  const items = raw.items.map(originalVideo).map(item => ({
    id: item.article_id, title: item.title, originalTitle: item.title, coverId: item.cover_id || null,
    url: safeArticleUrl(item.url), source: item.source, publishedAt: item.published_at,
    format: item.format || 'article',
    channelTitle: item.format === 'video' ? item.media?.channel_title || '' : item.format === 'podcast' ? item.media?.show_title || '' : '',
    duration: ['video', 'podcast'].includes(item.format) ? mediaDuration(item.media?.duration_seconds) : '',
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
    readingTimeMinutes: (!item.format || item.format === 'article') && Number.isInteger(item.reading_time_minutes) && item.reading_time_minutes > 0
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
    preferenceImpact: raw.diagnostics?.preference_impact || [],
    preferenceWarnings: (raw.warnings || []).filter(text => text.startsWith('Certaines préférences')),
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
