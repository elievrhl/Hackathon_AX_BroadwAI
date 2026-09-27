import test from 'node:test';
import assert from 'node:assert/strict';
import { enterAccount, leaveAccount, currentAccount, accountKey } from './accounts.js';
import { getLibrary, saveEdition, removeEdition, listCovers, getCover } from './api.js';

function storage() {
  const entries = new Map();
  return { getItem: key => entries.get(key) ?? null, setItem: (key, value) => entries.set(key, value), removeItem: key => entries.delete(key), entries };
}
test('demo accounts preserve the first reader and isolate subsequent readers without storing passwords', () => {
  const db = storage();
  db.setItem('kiosque.user', JSON.stringify('local-existing'));
  db.setItem('kiosque.reader.v1', JSON.stringify({ name: 'Ancien', topics: ['tech'] }));
  db.setItem('kiosque.lastCover', JSON.stringify('previous-edition'));
  const alice = enterAccount({ create: true, email: ' Alice@Example.com ', name: 'Alice', password: 'never-store-this' }, db);
  assert.equal(alice.id, 'local-existing');
  assert.equal(alice.email, 'alice@example.com');
  assert.equal(db.getItem(accountKey(alice.id, 'kiosque.lastCover')), '"previous-edition"');
  assert.deepEqual(currentAccount(db), alice);
  leaveAccount(db);
  assert.equal(currentAccount(db), null);
  const bob = enterAccount({ create: true, email: 'bob@example.com', name: 'Bob' }, db);
  assert.notEqual(bob.id, alice.id);
  assert.equal(db.getItem(accountKey(bob.id, 'kiosque.reader.v1')), null);
  assert.equal(db.getItem(accountKey(bob.id, 'kiosque.lastCover')), null);
  assert.deepEqual(enterAccount({ create: false, email: 'ALICE@example.com' }, db), alice);
  assert.ok(!JSON.stringify([...db.entries]).includes('never-store-this'));
  assert.throws(() => enterAccount({ create: true, email: 'alice@example.com', name: 'Alice' }, db), /existe/);
  assert.throws(() => enterAccount({ create: false, email: 'nobody@example.com' }, db), /Créez/);
});
test('library and reader requests always carry the selected demo identity', async () => {
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
