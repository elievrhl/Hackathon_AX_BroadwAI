import test from 'node:test';
import assert from 'node:assert/strict';
import { request } from './api.js';

test('reader errors keep infrastructure details out of the journal and chat', async t => {
  for (const path of ['/v1/covers', '/v1/readers/alice/messages']) {
    for (const status of [500, 502, 503, 504]) {
      t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({
        detail: 'Configurer OPENAI_API_KEY dans .env ; erreur PostgreSQL /srv/app/internal.py',
      }), { status }));
      await assert.rejects(request(path), error => {
        assert.equal(error.status, status);
        assert.doesNotMatch(error.message, /OPENAI|\.env|PostgreSQL|\/srv\/|500|502|503|504/);
        return true;
      });
      t.mock.restoreAll();
    }
  }
});

test('reader errors preserve actionable validation and conflict messages', async t => {
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({
    detail: 'Cette collection existe déjà.',
  }), { status: 409 }));
  await assert.rejects(request('/v1/collections'), /Cette collection existe déjà/);
});
