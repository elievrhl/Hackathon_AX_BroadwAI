import test from 'node:test';
import assert from 'node:assert/strict';
import { adaptCover, normalizeProfile, toCoverRequest, safeArticleUrl, DEFAULT_PROFILE } from './reader.js';
import { createCover, getCover, listCovers, sendFeedback, getHealth } from './api.js';

function fixture(size) {
  return {
    id: 'edition', user_id: 'local-test', title: 'Une réelle', status: size < 15 ? 'partial' : 'complete', created_at: '2026-09-26T12:00:00Z',
    items: Array.from({ length: size }, (_, i) => ({
      article_id: `article-${i}`, title: `Original ${i}`, headline: i % 2 ? null : `Titre français ${i}`,
      url: `https://example.com/${i}`, source: 'example.com', section: ['Inflation', 'Entreprises', 'International'][i % 3],
      published_at: null, reason: 'Explication éditoriale', extraction_status: 'excerpt',
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
  assert.ok(!('name' in payload.profile));
  assert.throws(() => toCoverRequest(DEFAULT_PROFILE, ''), /Identifiant/);
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
      assert.equal(cover.lead.title, 'Titre français 0');
      assert.equal(cover.lead.reason, 'Explication éditoriale');
      assert.equal(cover.lead.excerptOnly, true);
      assert.deepEqual(cover.lead.caveats, ['Texte incomplet']);
      assert.equal(cover.sections[0].label, 'Inflation');
    }
    if (size > 1) assert.equal(cover.items[1].title, 'Original 1');
  }
});

test('publisher links reject executable and relative URLs', () => {
  for (const value of ['javascript:alert(1)', 'data:text/html,test', '/relative', '']) assert.equal(safeArticleUrl(value), null);
  assert.equal(safeArticleUrl('https://example.com/a'), 'https://example.com/a');
});

test('evergreen readings are identified without inventing a publication date', () => {
  const raw = fixture(1);
  raw.items[0].reading_kind = 'evergreen';
  const cover = adaptCover(raw);
  assert.equal(cover.lead.kind, 'Lecture de fond');
  assert.equal(cover.lead.publishedAt, null);
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
  await assert.rejects(getHealth(), /JSON/);
  t.mock.restoreAll();
  t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('network'); });
  await assert.rejects(listCovers(), /inaccessible/);
});
