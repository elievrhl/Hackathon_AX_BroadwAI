import test from 'node:test';
import assert from 'node:assert/strict';
import { dailyEditionMessage, initialEditionId } from './daily-edition.js';
import { registerDailyEdition, getDailyEdition } from './api.js';
import { DEFAULT_PROFILE, toCoverRequest } from './reader.js';

test('opening the journal prefers the latest edition while explicit archive links stay pinned', () => {
  const history = [{ id: 'today' }, { id: 'yesterday' }];
  assert.equal(initialEditionId(null, history, 'yesterday'), 'today');
  assert.equal(initialEditionId('archive', history, 'yesterday'), 'archive');
  assert.equal(initialEditionId(null, [], 'yesterday'), 'yesterday');
  assert.equal(initialEditionId(null, [], null), null);
});

test('registration saves personalization without posting a paid cover request', async () => {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return new Response(JSON.stringify({ registered: true, enabled: true }), { status: 200 });
  };
  try {
    const payload = toCoverRequest(DEFAULT_PROFILE, 'alice/id');
    await registerDailyEdition('alice/id', payload);
    await getDailyEdition('alice/id');
    assert.equal(calls[0].url, '/v1/readers/alice%2Fid/daily-edition');
    assert.equal(calls[0].options.method, 'PUT');
    assert.deepEqual(JSON.parse(calls[0].options.body), payload);
    assert.equal(calls[1].url, calls[0].url);
    assert.equal(calls[1].options.method, undefined);
    assert.ok(calls.every(call => call.url !== '/v1/covers'));
  } finally { globalThis.fetch = original; }
});

test('daily status never promises an active schedule when it is unavailable', () => {
  assert.match(dailyEditionMessage(null), /Activation/);
  assert.match(dailyEditionMessage({ enabled: false }), /indisponible/);
  assert.match(dailyEditionMessage({ enabled: true, status: 'running' }), /se prépare/);
  assert.match(dailyEditionMessage({ enabled: true, status: 'failed' }), /n’a pas pu/);
  assert.match(dailyEditionMessage({ enabled: true, status: 'scheduled' }), /4 h, heure de Paris/);
});
