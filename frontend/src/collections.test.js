import test from 'node:test';
import assert from 'node:assert/strict';
import { getCollections, getCollection, createCollection, editCollection, deleteCollection, addToCollection, removeFromCollection, importBookmarks } from './api.js';

test('article collections keep the account, memberships and creation data in every request', async t => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({ url, method: options.method || 'GET', body: options.body && JSON.parse(options.body) });
    return new Response(JSON.stringify({ id: 'library', article_ids: ['article'] }));
  });
  await getCollections('local-alice');
  await createCollection('local-alice', { name: 'Sciences', description: 'Mes lectures' });
  await getCollection('local-alice', 'library');
  await addToCollection('local-alice', 'library', 'article', 'edition');
  await removeFromCollection('local-alice', 'library', 'article');
  await editCollection('local-alice', 'library', { name: 'Astronomie', description: '' });
  await deleteCollection('local-alice', 'library');
  await importBookmarks('local-alice', ['article']);
  assert.ok(calls.every(call => call.url.endsWith('?user_id=local-alice')));
  assert.deepEqual(calls.map(call => call.method), ['GET','POST','GET','PUT','DELETE','PATCH','DELETE','POST']);
  assert.deepEqual(calls[1].body, { name: 'Sciences', description: 'Mes lectures' });
  assert.equal(calls[3].url, '/v1/collections/library/articles/article?user_id=local-alice');
  assert.deepEqual(calls[3].body, { cover_id: 'edition' });
  assert.deepEqual(calls[7].body, { article_ids: ['article'] });
});
