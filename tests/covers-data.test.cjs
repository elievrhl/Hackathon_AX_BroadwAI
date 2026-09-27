const test = require('node:test');
const assert = require('node:assert/strict');
const {build} = require('../broadwai/static/covers-data.js');

const article = id => ({article_id: id, title: `Article ${id}`, source: 'example.com'});
const event = (kind, id, extra = {}) => ({kind, article_id: id, ...extra});

test('early availability checks are distinct from editorial examination and preparation', () => {
  const result = build({items: [], diagnostics: {events: [
    event('access_checked', 'ok', {status: 'full_text', checked: true}),
    event('access_checked', 'blocked', {status: 'unavailable', checked: true}),
    event('candidate_skipped', 'blocked', {reason: 'Aucun contenu exploitable'}),
    {kind: 'editorial_preview', candidates: [article('ok')]},
  ]}});
  assert.equal(result.counts.examined, 1);
  assert.equal(result.counts.started, 0);
  assert.equal(result.articles.get('blocked').status, 'rejected');
  assert.equal(result.articles.get('ok').access.status, 'full_text');
});

test('counts distinct articles across repeated searches and preparation attempts', () => {
  const result = build({items: [article('a')], diagnostics: {
    candidates: [article('a')],
    events: [
      {kind: 'editorial_preview', candidates: [article('a'), article('b')]},
      {kind: 'search_screen_requested', candidates: [article('a'), article('c')]},
      {kind: 'shortlist', shortlisted_ids: ['a', 'b'], ranked: []},
      {kind: 'shortlist', shortlisted_ids: ['a', 'c'], ranked: []},
      event('candidate_prepare', 'a'), event('candidate_prepare', 'a'),
      event('summary_cache_hit', 'a'), event('summary_completed', 'a'),
    ],
  }});
  assert.equal(result.rows.length, 3);
  assert.deepEqual(result.counts, {examined: 3, scheduled: 3, started: 1, generated: 1, reused: 1, ready: 1, selected: 1});
  assert.equal(result.articles.get('b').status, 'waiting');
});

test('a received summary does not imply a valid candidate or a published article', () => {
  const result = build({items: [], diagnostics: {candidates: [], events: [
    event('candidate_prepare', 'stale'),
    event('summary_completed', 'stale', {brief: {summary: 'Contenu ancien'}}),
    event('candidate_skipped', 'stale', {reason: 'Actualité périmée'}),
    event('candidate_prepare', 'error'), event('summary_failed', 'error', {error: 'Budget épuisé'}),
  ]}});
  assert.equal(result.articles.get('stale').status, 'rejected');
  assert.equal(result.articles.get('stale').reason, 'Actualité périmée');
  assert.equal(result.articles.get('stale').brief.summary, 'Contenu ancien');
  assert.equal(result.articles.get('error').status, 'failed');
  assert.equal(result.counts.generated, 1);
  assert.equal(result.counts.ready, 0);
});

test('final membership overrides a previous quota removal and extraction failure', () => {
  const result = build({
    items: [{...article('a'), reason: 'Angle retenu'}],
    trace: [{step: 2, outcome: {removed_by_constraints: [{article_id: 'a', reason: 'Quota de source'}, {article_id: 'b', reason: 'Doublon'}]}}],
    diagnostics: {candidates: [article('a'), article('b')], events: [event('extract_failed', 'a', {error: 'Timeout'})]},
  });
  assert.equal(result.articles.get('a').status, 'selected');
  assert.equal(result.articles.get('a').reason, 'Angle retenu');
  assert.equal(result.articles.get('a').removal.step, 2);
  assert.equal(result.articles.get('b').status, 'ready');
  assert.match(result.articles.get('b').reason, /Motif final individuel non enregistré/);
});

test('exploration reserves and proposals are not treated as prepared articles', () => {
  const result = build({items: [], diagnostics: {editorial_plan: {picks: [
    {article_id: 'reserve', exploration: true, exploration_reason: 'Thème connexe'},
    {article_id: 'proposal', reason: 'Sujet prometteur'},
  ]}, events: [{kind: 'editorial_preview', candidates: [article('reserve'), article('proposal'), article('other')]}]}});
  assert.equal(result.articles.get('reserve').status, 'reserve');
  assert.equal(result.articles.get('proposal').status, 'proposed');
  assert.equal(result.articles.get('other').status, 'examined');
  assert.equal(result.counts.started, 0);
});

test('legacy traces do not invent zeros, preparation history or rejection reasons', () => {
  const result = build({items: [article('a')], trace: [{step: 1, outcome: {removed_by_constraints: [{article_id: 'unknown', reason: 'Identifiant inconnu'}]}}]});
  assert.equal(result.counts.selected, 1);
  for (const key of ['examined', 'scheduled', 'started', 'generated', 'reused', 'ready']) assert.equal(result.counts[key], null);
  assert.equal(result.articles.get('a').status, 'selected');
  assert.equal(result.articles.get('unknown').status, 'unknown');
});

test('an extraction error alone does not imply rejection when an excerpt was usable', () => {
  const result = build({items: [], diagnostics: {candidates: [article('a')], events: [
    event('extract_failed', 'a', {error: 'Timeout'}), event('summary_cache_hit', 'a'), event('candidate_ready', 'a'),
  ]}});
  assert.equal(result.articles.get('a').status, 'ready');
  assert.match(result.articles.get('a').reason, /motif individuel de non-sélection non enregistré/);
});
