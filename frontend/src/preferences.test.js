import test from 'node:test';
import assert from 'node:assert/strict';
import { createPreference, updatePreference, deletePreference, getPreferences, getReaderFeedback, sendFeedback } from './api.js';
import { preferenceValue, preferenceSummary, impactText, EMPTY_PREFERENCE } from './preferences.js';
import { adaptCover } from './reader.js';

test('corrections preserve nuance and explicit scope without leaking server state into writes', () => {
  const value = { ...EMPTY_PREFERENCE, action: 'exclude', target: 'IA promotionnelle', explanation: 'Je reste intéressé par la recherche en IA.', scope: 'next', id: 'abc', status: 'active', revision: 4 };
  const payload = preferenceValue(value);
  assert.equal(payload.explanation, value.explanation);
  assert.equal(payload.scope, 'next');
  assert.equal(payload.id, undefined);
  assert.match(preferenceSummary(value), /Ne plus proposer : IA promotionnelle/);
  assert.match(impactText('diversify', 18), /3 places au total/);
  assert.match(impactText('less', 20), /3 articles/);
});

test('preference lifecycle API carries revision, ownership and explanations; errors are not retried', async t => {
  const calls = [];
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = async (path, options) => { calls.push({ path, ...options }); return new Response(JSON.stringify([])); };
  const value = { ...EMPTY_PREFERENCE, target: 'Histoire' };
  await createPreference('local-user', { ...value, id: 'stable-request-id' });
  await updatePreference('local-user', 'preference-id', { ...value, revision: 3, explanation: 'Seulement les sciences' });
  await getPreferences('local-user');
  await getReaderFeedback('local-user', 'edition');
  await deletePreference('local-user', 'preference-id', 4);
  await sendFeedback({ user_id: 'local-user', cover_id: 'edition', article_id: 'article', kind: 'not_interested', comment: 'Trop général', preference: value });
  assert.equal(calls[1].method, 'PUT');
  assert.equal(JSON.parse(calls[1].body).revision, 3);
  assert.match(calls[4].path, /revision=4$/);
  assert.equal(calls[4].method, 'DELETE');
  assert.equal(JSON.parse(calls[5].body).comment, 'Trop général');
  let attempts = 0;
  globalThis.fetch = async () => { attempts++; return new Response(JSON.stringify({ detail: 'Préférence modifiée entre-temps' }), { status: 409 }); };
  await assert.rejects(updatePreference('local-user', 'preference-id', value), /modifiée/);
  assert.equal(attempts, 1);
});

test('edition shows its saved impact rather than the latest editable preferences', () => {
  const impact = [{ id: 'rule', action: 'diversify', target: 'Histoire', selected_count: 2, article_ids: ['a', 'b'] }];
  assert.deepEqual(adaptCover({ id: 'edition', items: [], diagnostics: { preference_impact: impact } }).preferenceImpact, impact);
  assert.deepEqual(adaptCover({ id: 'legacy', items: [] }).preferenceImpact, []);
});
