import test from 'node:test';
import assert from 'node:assert/strict';
import { dailyEditionMessage, dailyEditionRefreshMs, initialEditionId } from './daily-edition.js';
import { registerDailyEdition, getDailyEdition } from './api.js';
import { DEFAULT_PROFILE, toCoverRequest } from './reader.js';

test('opening the journal prefers the latest edition while explicit archive links stay pinned', () => {
  const history = [{ id: 'today' }, { id: 'yesterday' }];
  assert.equal(initialEditionId(null, history, 'yesterday'), 'today');
  assert.equal(initialEditionId('archive', history, 'yesterday'), 'archive');
  assert.equal(initialEditionId(null, [], 'yesterday'), 'yesterday');
  assert.equal(initialEditionId(null, [], null), null);
});

test('registration delegates initial preparation and duplicate protection to the server', async () => {
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
  assert.match(dailyEditionMessage(null), /Préparation/);
  assert.match(dailyEditionMessage({ enabled: false }), /indisponible/);
  assert.match(dailyEditionMessage({ enabled: true, status: 'queued' }), /première une/);
  assert.match(dailyEditionMessage({ enabled: true, status: 'running' }), /se prépare/);
  assert.match(dailyEditionMessage({ enabled: true, status: 'queued' }), /apparaîtra ici automatiquement/);
  assert.match(dailyEditionMessage({ enabled: true, status: 'failed' }), /n’a pas pu/);
  assert.equal(dailyEditionMessage({ enabled: true, status: 'scheduled' }, true), '');
  assert.equal(dailyEditionMessage({ enabled: true, status: 'ready' }, true), '');
  assert.doesNotMatch(dailyEditionMessage({ enabled: true, status: 'failed' }), /dernière édition/);
  assert.match(dailyEditionMessage({ enabled: true, status: 'failed' }, true), /dernière édition/);
});

test('pending editions are refreshed promptly until preparation ends', () => {
  assert.equal(dailyEditionRefreshMs({ status: 'queued' }), 2_500);
  assert.equal(dailyEditionRefreshMs({ status: 'running' }), 2_500);
  assert.equal(dailyEditionRefreshMs({ status: 'ready' }, false), 2_500);
  for (const status of ['ready', 'failed', 'disabled', 'scheduled']) {
    assert.equal(dailyEditionRefreshMs({ status }), 60_000);
  }
  assert.equal(dailyEditionRefreshMs(null), 60_000);
});
