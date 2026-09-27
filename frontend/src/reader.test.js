import test from 'node:test';
import assert from 'node:assert/strict';
import { adaptCover, normalizeProfile, initialReaderProfile, toCoverRequest, safeArticleUrl, articleImageUrl, DEFAULT_PROFILE, contentCount, mediaDuration, contentAction } from './reader.js';
import { createCover, getCover, listCovers, sendFeedback, getHealth } from './api.js';

test('new accounts enter the journal with an editable default selection; existing preferences survive login', () => {
  const initial = initialReaderProfile({ name: 'Camille', reader_profile: null });
  assert.equal(initial.name, 'Camille');
  assert.ok(toCoverRequest(initial, 'new-account').profile.interests.length);
  const personalized = { ...DEFAULT_PROFILE, name: 'Camille', topics: ['science'], notes: 'Astronomie' };
  assert.deepEqual(initialReaderProfile({ name: 'Camille', reader_profile: personalized }), personalized);
});

function fixture(size) {
  return {
    id: 'edition', user_id: 'local-test', title: 'Une réelle', status: size < 15 ? 'partial' : 'complete', created_at: '2026-09-26T12:00:00Z',
    items: Array.from({ length: size }, (_, i) => ({
      article_id: `article-${i}`, title: `Original ${i}`, headline: i % 2 ? null : `Titre français ${i}`,
      url: `https://example.com/${i}`, source: 'example.com', section: ['Inflation', 'Entreprises', 'International'][i % 3],
      published_at: null, reason: 'Explication éditoriale', extraction_status: 'excerpt',
      reading_time_minutes: i === 0 ? 5 : null,
      brief: { summary: 'Résumé', key_points: ['Un point'], content_type: 'analysis', caveats: ['Texte incomplet'] },
    })),
  };
}

test('request uses a stable local identity, real notes, selected languages and discovery', () => {
  const payload = toCoverRequest({ ...DEFAULT_PROFILE, topics: ['economy', 'tech'], notes: 'Mon projet', size: 20 }, 'local-device');
  assert.equal(payload.profile.user_id, 'local-device');
  assert.equal(payload.profile.notes, 'Mon projet');
  assert.deepEqual(payload.profile.languages, ['fr', 'en']);
  assert.equal(payload.profile.interests[0].weight, 3);
  assert.equal(payload.size, 20);
  assert.equal(payload.discover_web, true);
  assert.equal(payload.discover_sources, true);
  assert.equal(payload.discover_videos, true);
  assert.equal(payload.max_videos, 3);
  assert.equal(payload.discover_podcasts, true);
  assert.equal(payload.max_podcasts, 2);
  assert.ok(!('name' in payload.profile));
  assert.throws(() => toCoverRequest(DEFAULT_PROFILE, ''), /Identifiant/);
});

test('mixed editions keep original video titles, channel, duration and every card', () => {
  const raw = fixture(8);
  Object.assign(raw.items[7], { format: 'video', media: { channel_title: 'ARTE', duration_seconds: 3662 }, reading_time_minutes: 9 });
  const cover = adaptCover(raw);
  const item = cover.items[7];
  assert.equal(item.title, raw.items[7].title);
  assert.equal(item.format, 'video');
  assert.equal(item.channelTitle, 'ARTE');
  assert.equal(item.duration, '1 h 1 min 2 s');
  assert.equal(item.readingTimeMinutes, null);
  assert.equal(contentCount(cover.items), '7 articles · 1 vidéo');
  assert.equal(cover.remainingSections.flatMap(section => section.articles).filter(row => row.id === item.id).length, 1);
  assert.equal(mediaDuration(undefined), '');
  assert.equal(mediaDuration(-1), '');
  assert.equal(mediaDuration(0.5), '');
  assert.equal(mediaDuration(Infinity), '');
  assert.equal(mediaDuration(NaN), '');
  assert.equal(mediaDuration('45'), '');
  assert.equal(mediaDuration(622), '10 min 22 s');
  assert.equal(mediaDuration(3600), '1 h');
  assert.equal(mediaDuration(45), '45 s');
  assert.equal(mediaDuration(Infinity), '');
  assert.equal(mediaDuration(NaN), '');
});

test('podcasts preserve their show, duration, original title and direct episode link', () => {
  const raw = fixture(8);
  Object.assign(raw.items[6], { format: 'podcast', media: { show_title: 'Sciences à écouter', duration_seconds: 1980 }, reading_time_minutes: 8 });
  Object.assign(raw.items[7], { format: 'video' });
  const cover = adaptCover(raw);
  const podcast = cover.items[6];
  assert.equal(podcast.channelTitle, 'Sciences à écouter');
  assert.equal(podcast.duration, '33 min');
  assert.equal(podcast.title, raw.items[6].title);
  assert.equal(podcast.url, raw.items[6].url);
  assert.equal(podcast.readingTimeMinutes, null);
  assert.equal(contentAction(podcast.format), 'Écouter l’épisode');
  assert.equal(contentAction('video'), 'Voir sur YouTube');
  assert.equal(contentAction('article'), 'Lire l’article');
  assert.equal(contentCount(cover.items), '6 articles · 1 vidéo · 1 podcast');
  assert.ok(cover.remainingSections.some(section => section.articles.includes(podcast)));
});

test('saved video recaps link to the original without presenting the recap as its transcript', () => {
  const raw = fixture(1);
  Object.assign(raw.items[0], {
    title: 'Designing Math - Summary & Key Points',
    url: 'https://www.recapcraft.com/v/bLSLN96Gn-w/', source: 'www.recapcraft.com',
    format: 'article', reading_time_minutes: 6,
    media: { video_id: 'bLSLN96Gn-w', duration_seconds: 1649, channel_title: 'Figma',
      original_title: 'Designing Math', original_description: 'Description originale.' },
  });
  const item = adaptCover(raw).items[0];
  assert.equal(item.id, raw.items[0].article_id);
  assert.equal(item.url, 'https://www.youtube.com/watch?v=bLSLN96Gn-w');
  assert.equal(item.title, 'Designing Math');
  assert.equal(item.format, 'video');
  assert.equal(item.duration, '27 min 29 s');
  assert.equal(item.readingTimeMinutes, null);
  assert.equal(item.summary, 'Description originale.');
  assert.deepEqual(item.keyPoints, []);
  raw.items[0].media = null;
  const unavailable = adaptCover(raw).items[0];
  assert.equal(unavailable.duration, '');
  assert.equal(unavailable.summary, '');
  raw.items[0].url = 'https://recapcraft.com.evil.example/v/bLSLN96Gn-w/';
  assert.equal(adaptCover(raw).items[0].format, 'article');
});

test('stored profiles migrate without accepting malformed preferences', () => {
  assert.equal(normalizeProfile(null), null);
  assert.equal(normalizeProfile({ name: 'Camille', topics: ['missing'] }), null);
  const profile = normalizeProfile({ name: ' Camille ', topics: ['economy', 'economy', 'missing'], languages: {}, size: 900, notes: 12 });
  assert.equal(profile.name, 'Camille');
  assert.deepEqual(profile.topics, ['economy']);
  assert.deepEqual(profile.languages, ['fr']);
  assert.equal(profile.size, 18);
});

test('editor order, headings and every article survive layout, including small fallback editions', () => {
  for (const size of [0, 1, 2, 5, 6, 15, 18, 20]) {
    const raw = fixture(size);
    const cover = adaptCover(raw);
    const rendered = [cover.lead, ...cover.secondary, ...cover.briefs, ...cover.remainingSections.flatMap(section => section.articles)].filter(Boolean);
    assert.equal(rendered.length, size);
    assert.equal(new Set(rendered.map(article => article.id)).size, size);
    assert.deepEqual(new Set(rendered.map(article => article.id)), new Set(raw.items.map(item => item.article_id)));
    assert.deepEqual(cover.items.map(item => item.id), raw.items.map(item => item.article_id));
    if (size) {
      assert.equal(cover.lead.title, 'Original 0');
      assert.equal(cover.lead.reason, 'Explication éditoriale');
      assert.equal(cover.lead.excerptOnly, true);
      assert.equal(cover.lead.readingTimeMinutes, 5);
      assert.deepEqual(cover.lead.caveats, ['Texte incomplet']);
      assert.equal(cover.sections[0].label, 'Inflation');
    }
    if (size > 1) {
      assert.equal(cover.items[1].title, 'Original 1');
      assert.equal(cover.items[1].readingTimeMinutes, null);
    }
  }
});

test('publisher links reject executable and relative URLs', () => {
  for (const value of ['javascript:alert(1)', 'data:text/html,test', '/relative', '']) assert.equal(safeArticleUrl(value), null);
  assert.equal(safeArticleUrl('https://example.com/a'), 'https://example.com/a');
});

test('article images use the backend even for previously missing artwork', () => {
  assert.equal(articleImageUrl({ article_id: 'old-edition-article' }), '/v1/articles/old-edition-article/image?v=images-4');
  assert.equal(articleImageUrl({ article_id: 'checked', image_checked: true }), '/v1/articles/checked/image?v=images-4');
  for (const article_id of ['../private', '', 'bad/id']) assert.equal(articleImageUrl({ article_id }), null);
  const raw = fixture(1);
  raw.items[0].image = { url: 'https://publisher.example/photo.jpg', alt: 'La photo de l’article' };
  raw.items[0].image_checked = true;
  assert.equal(adaptCover(raw).lead.imageUrl, '/v1/articles/article-0/image?v=images-4');
  assert.equal(adaptCover(raw).lead.imageAlt, 'La photo de l’article');
});

test('explicit editorial roles put a substantive reading in the lead without losing any articles', () => {
  const raw = fixture(9);
  raw.items.forEach(item => { item.role = 'reading'; });
  raw.items[6].role = 'lead';
  raw.items[6].reading_kind = 'evergreen';
  raw.items[3].role = 'secondary';
  raw.items[1].role = 'brief';
  raw.items[7].reading_kind = 'research';
  const cover = adaptCover(raw);
  assert.equal(cover.lead.id, 'article-6');
  assert.equal(cover.lead.kind, 'Lecture de fond');
  assert.deepEqual(cover.secondary.map(item => item.id), ['article-3']);
  assert.deepEqual(cover.briefs.map(item => item.id), ['article-1']);
  assert.equal(cover.items[7].kind, 'Recherche');
  const rendered = [cover.lead, ...cover.secondary, ...cover.briefs,
    ...cover.remainingSections.flatMap(section => section.articles)];
  assert.equal(rendered.length, raw.items.length);
  assert.equal(new Set(rendered.map(item => item.id)).size, raw.items.length);
});

test('evergreen readings are identified without inventing a publication date', () => {
  const raw = fixture(1);
  raw.items[0].reading_kind = 'evergreen';
  const cover = adaptCover(raw);
  assert.equal(cover.lead.kind, 'Lecture de fond');
  assert.equal(cover.lead.publishedAt, null);
});

test('exploration stays separate from the headlines with every article and its explanation', () => {
  for (const focusedCount of [0, 1, 6, 15]) {
    const raw = fixture(focusedCount + 2);
    raw.items.slice(focusedCount).forEach(item => {
      item.selection_kind = 'exploration';
      item.exploration_reason = 'De la programmation au design des outils de pensée.';
      item.reading_kind = 'evergreen';
    });
    const cover = adaptCover(raw);
    const rendered = [cover.lead, ...cover.secondary, ...cover.briefs,
      ...cover.remainingSections.flatMap(section => section.articles), ...cover.exploration].filter(Boolean);
    assert.equal(new Set(rendered.map(item => item.id)).size, raw.items.length);
    assert.equal(rendered.length, raw.items.length);
    assert.equal(cover.exploration.length, 2);
    assert.ok(!cover.lead?.exploration);
    assert.ok(cover.exploration.every(item => item.section === 'Exploration'
      && item.explorationReason.includes('design') && item.kind === 'Lecture de fond'));
    assert.equal(cover.sections.find(section => section.label === 'Exploration').articles.length, 2);
  }
});

test('API round trip sends the actual payload and feedback and reads persisted editions', async t => {
  const calls = [];
  const raw = fixture(18);
  t.mock.method(globalThis, 'fetch', async (path, options) => {
    calls.push({ path, options });
    return new Response(JSON.stringify(path.includes('feedback') ? { saved: true } : path.endsWith('limit=100') ? [raw] : raw));
  });
  const payload = toCoverRequest(DEFAULT_PROFILE, 'local-test');
  assert.equal(adaptCover(await createCover(payload)).items.length, 18);
  assert.equal(calls[0].options.method, 'POST');
  assert.deepEqual(JSON.parse(calls[0].options.body), payload);
  await getCover('edition');
  await listCovers();
  await sendFeedback({ user_id: 'local-test', cover_id: 'edition', article_id: 'article-0', kind: 'useful' });
  assert.equal(calls[1].path, '/v1/covers/edition');
  assert.equal(calls[3].path, '/v1/feedback');
  assert.equal(calls[3].options.keepalive, false);
  const opened = { user_id: 'local-test', cover_id: 'edition', article_id: 'article-0', kind: 'open' };
  await sendFeedback(opened);
  assert.equal(calls[4].path, '/v1/feedback');
  assert.equal(calls[4].options.keepalive, true, 'Opening a publisher keeps feedback alive during navigation');
  assert.deepEqual(JSON.parse(calls[4].options.body), opened);
});

test('server failures never become simulated content or automatic paid retries', async t => {
  for (const status of [429, 503, 504, 500]) {
    let attempts = 0;
    t.mock.method(globalThis, 'fetch', async () => { attempts++; return new Response('{"detail":"Erreur"}', { status }); });
    await assert.rejects(createCover({}), error => error.status === status);
    assert.equal(attempts, 1);
    t.mock.restoreAll();
  }
  t.mock.method(globalThis, 'fetch', async () => new Response('<html>wrong proxy</html>'));
  await assert.rejects(getHealth(), /n’a pas pu être lue/);
  t.mock.restoreAll();
  t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('network'); });
  await assert.rejects(listCovers(), /inaccessible/);
});
