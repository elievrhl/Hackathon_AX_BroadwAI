import test from 'node:test';
import assert from 'node:assert/strict';
import { getRegeneration, regenerateEdition } from './api.js';
import { regenerationMessage, regenerationProgress, validRegenerationReason } from './regeneration.js';

test('regeneration sends a trimmed reason and the selected edition for the current reader', async t => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({ url, options });
    return new Response(JSON.stringify({ available: true }), { status: 200 });
  });
  await getRegeneration('alice/id');
  await regenerateEdition('alice/id', 'cover-id', '  Plus de sciences  ');
  await regenerateEdition('alice/id', 'cover-id');
  assert.equal(calls[0].url, '/v1/readers/alice%2Fid/regeneration');
  assert.equal(calls[1].url, calls[0].url);
  assert.equal(calls[1].options.method, 'POST');
  assert.deepEqual(JSON.parse(calls[1].options.body), { cover_id: 'cover-id', reason: 'Plus de sciences' });
  assert.deepEqual(JSON.parse(calls[2].options.body), { cover_id: 'cover-id', reason: '' });
});

test('daily limit is displayed without retrying a paid request', async t => {
  let attempts = 0;
  t.mock.method(globalThis, 'fetch', async () => {
    attempts++;
    return new Response(JSON.stringify({ detail: 'Votre régénération du jour est déjà utilisée.' }), { status: 409 });
  });
  await assert.rejects(regenerateEdition('alice', 'cover', 'Autres sujets'), /du jour est déjà utilisée/);
  assert.equal(attempts, 1);
});

test('the optional reason may be empty and is limited to 1000 characters', () => {
  for (const value of ['!!', 'a', 'x'.repeat(1001)]) assert.equal(validRegenerationReason(value), false);
  for (const value of ['', ' ', '   ', '  Plus de littérature ', 'IA', '更新', 'économie']) assert.equal(validRegenerationReason(value), true);
});

test('status explains the daily allowance and preserves failure feedback', () => {
  assert.equal(regenerationMessage({ available: true, status: 'available' }), '');
  assert.match(regenerationMessage({ available: false, status: 'completed' }), /minuit, heure de Paris/);
  assert.match(regenerationMessage({ available: false, status: 'running' }), /automatiquement/);
  assert.match(regenerationMessage({ available: false, status: 'failed' }), /dernière édition reste disponible/);
  assert.match(regenerationMessage({ available: false, status: 'unavailable' }), /indisponible/);
});

test('estimated progress uses server elapsed time and resumes after a reload', () => {
  const status = { status: 'running', elapsed_seconds: 40, estimated_seconds: 120, receivedAt: 1000 };
  const progress = regenerationProgress(status, 11000);
  assert.equal(progress.elapsed, 50);
  assert.equal(progress.percent, 39);
  assert.match(progress.label, /1 min 10 s/);
  const reloaded = regenerationProgress({ ...status, elapsed_seconds: 50, receivedAt: 900000 }, 900000);
  assert.deepEqual(reloaded, progress);
  assert.equal(regenerationProgress({ ...status, receivedAt: 10000 }, 0).elapsed, 40);
});

test('a slow preparation never claims completion or promises zero seconds remaining', () => {
  const slow = regenerationProgress({ status: 'running', elapsed_seconds: 240, estimated_seconds: 120 });
  assert.equal(slow.percent, 95);
  assert.match(slow.label, /plus de temps que prévu/);
  const ready = regenerationProgress({ status: 'completed', elapsed_seconds: 60, estimated_seconds: 120 });
  assert.equal(ready.percent, 100);
  assert.match(ready.label, /prête/);
  assert.match(regenerationProgress({ status: 'running', elapsed_seconds: 0 }).label, /2 min/);
});
