import test from 'node:test';
import assert from 'node:assert/strict';
import { enterAccount, leaveAccount, currentAccount, saveAccountProfile } from './accounts.js';
import { getLibrary, saveEdition, removeEdition, listCovers, getCover } from './api.js';

test('accounts and preferences are restored from the server with cookie credentials', async () => {
  const original = globalThis.fetch;
  const calls = [];
  const account = { id: 'server-account', email: 'alice@example.com', reader_profile: { topics: ['tech'] } };
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return new Response(url.endsWith('/logout') ? null : JSON.stringify({ account, csrf_token: 'session-csrf' }), { status: url.endsWith('/logout') ? 204 : 200 });
  };
  try {
    assert.equal((await currentAccount()).account.id, account.id);
    assert.deepEqual(await enterAccount({ email: ' alice@example.com ', name: ' Alice ', password: 'not stored on device', create: true }), account);
    await saveAccountProfile(account.reader_profile);
    await leaveAccount();
    assert.deepEqual(calls.map(c => c.url), ['/v1/auth/session', '/v1/auth/register', '/v1/auth/profile', '/v1/auth/logout']);
    assert.ok(calls.every(c => c.options.credentials === 'same-origin'));
    assert.equal(calls[1].options.headers['X-Kiosque-CSRF'], 'session-csrf');
    assert.equal(JSON.parse(calls[1].options.body).password, 'not stored on device');
    assert.deepEqual(JSON.parse(calls[2].options.body), { profile: account.reader_profile });
  } finally { globalThis.fetch = original; }
});
test('library and reader requests always carry the selected server identity', async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => { calls.push([url, options.method || 'GET']); return { ok: true, json: async () => [] }; };
  try {
    await getLibrary('local-alice');
    await saveEdition('local-alice', 'edition');
    await removeEdition('local-bob', 'edition');
    await listCovers('local-bob');
    await getCover('edition', 'local-bob');
    assert.deepEqual(calls, [
      ['/v1/library?user_id=local-alice', 'GET'],
      ['/v1/library/edition?user_id=local-alice', 'PUT'],
      ['/v1/library/edition?user_id=local-bob', 'DELETE'],
      ['/v1/covers?limit=100&user_id=local-bob', 'GET'],
      ['/v1/covers/edition?user_id=local-bob', 'GET'],
    ]);
  } finally { globalThis.fetch = original; }
});
