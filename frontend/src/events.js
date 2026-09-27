import { TOPICS } from './reader.js';
import { EVENTS_CATALOG } from './events-catalog.js';

export const EVENT_KINDS = { exhibition: 'Exposition', concert: 'Concert', event: 'Rencontre', show: 'Émission', podcast: 'Podcast' };
const DAY = 86_400_000;
const topicLabels = new Map(TOPICS.map(topic => [topic.id, topic.label]));

export function parisDay(now = new Date()) {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Paris', year: 'numeric', month: '2-digit', day: '2-digit' }).format(now);
}

function validDay(value) {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
}

function safeUrl(value) {
  try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password; }
  catch { return false; }
}

export function eligibleEvent(item, { now = new Date(), area = 'paris', languages = ['fr', 'en'], format = 'all' } = {}) {
  if (!safeUrl(item.url) || !EVENT_KINDS[item.kind] || !validDay(item.checkedOn)) return false;
  if (!Array.isArray(item.topics) || !item.topics.length || !item.provider || !item.id) return false;
  if (!languages.includes(item.language) || item.cancelled || item.unavailable) return false;
  if (format === 'out' && item.mode !== 'out') return false;
  if (format === 'watch' && item.kind !== 'show') return false;
  if (format === 'listen' && item.kind !== 'podcast') return false;
  const today = parisDay(now);
  if (item.checkedOn > today) return false;
  if (item.mode === 'online') {
    return (!item.availableFrom || (validDay(item.availableFrom) && item.availableFrom <= today))
      && (!item.availableUntil || (validDay(item.availableUntil) && item.availableUntil >= today));
  }
  if (item.mode !== 'out' || !area || item.area !== area) return false;
  const horizon = new Date(Date.parse(`${today}T12:00:00Z`) + 14 * DAY).toISOString().slice(0, 10);
  if (item.occurrences) {
    return item.occurrences.some(date => Date.parse(date) > now.getTime() && parisDay(new Date(date)) <= horizon);
  }
  // A missing opening date is not invented: first eligibility is the date the
  // official page was observed advertising an ongoing exhibition.
  const from = item.startsOn || item.checkedOn;
  return validDay(from) && validDay(item.endsOn) && from <= item.endsOn
    && from <= horizon && item.endsOn >= today
    && (!item.endsAt || Date.parse(item.endsAt) > now.getTime());
}

export function selectEvents(profile, options = {}) {
  const { catalog = EVENTS_CATALOG, limit = 6, ...filters } = options;
  const topics = [...new Set(profile?.topics || [])].filter(id => topicLabels.has(id));
  const candidates = catalog.filter(item => eligibleEvent(item, { ...filters, languages: profile?.languages || ['fr'] }))
    .map(item => {
      const matches = topics.filter(topic => item.topics.includes(topic));
      return { ...item, matches, score: matches.reduce((total, topic) => total + (topics.indexOf(topic) === 0 ? 3 : 2), 0) };
    }).filter(item => item.score > 0);
  const selected = [], seenIds = new Set(), seenUrls = new Set(), covered = new Set();
  const providers = new Map(), kinds = new Map(), modes = new Set();
  while (selected.length < Math.max(0, Math.min(6, limit))) {
    const pool = candidates.filter(item => !seenIds.has(item.id) && !seenUrls.has(item.url)
      && (providers.get(item.provider) || 0) < 2);
    if (!pool.length) break;
    const score = item => item.score
      + 2 * item.matches.filter(topic => !covered.has(topic)).length
      + (modes.has(item.mode) ? 0 : 2)
      + (kinds.has(item.kind) ? 0 : 1)
      - (kinds.get(item.kind) || 0);
    pool.sort((a, b) => score(b) - score(a) || a.id.localeCompare(b.id));
    const item = pool[0];
    selected.push({ ...item, reason: `Pour ${item.matches.length > 1 ? 'vos intérêts' : 'votre intérêt'} ${item.matches.map(topic => `« ${topicLabels.get(topic)} »`).join(' et ')}.` });
    seenIds.add(item.id); seenUrls.add(item.url);
    item.matches.forEach(topic => covered.add(topic));
    providers.set(item.provider, (providers.get(item.provider) || 0) + 1);
    kinds.set(item.kind, (kinds.get(item.kind) || 0) + 1); modes.add(item.mode);
  }
  return selected;
}

export function eventDateLabel(item, now = new Date()) {
  const day = value => new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Europe/Paris' }).format(new Date(`${value}T12:00:00Z`));
  if (item.mode === 'online') return item.publishedOn ? `Archive du ${day(item.publishedOn)}` : 'À découvrir en ligne';
  if (item.occurrences) {
    const next = item.occurrences.filter(date => Date.parse(date) > now.getTime()).sort()[0];
    return next ? new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Paris' }).format(new Date(next)) : 'Terminé';
  }
  if (item.startsOn && item.startsOn > parisDay(now)) return `Du ${day(item.startsOn)} au ${day(item.endsOn)}`;
  return `En cours · jusqu’au ${day(item.endsOn)}`;
}
