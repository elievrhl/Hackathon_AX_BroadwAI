import test from 'node:test';
import assert from 'node:assert/strict';
import { getCollections, getCollection, createCollection, editCollection, deleteCollection, addToCollection, removeFromCollection, importBookmarks } from './api.js';
import { getArchives, getSavedArticles, saveArticle, unsaveArticle } from './api.js';

test('archives and one-click bookmarks use separate APIs and preserve the article origin', async t => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({ url, method: options.method || 'GET', body: options.body && JSON.parse(options.body) });
    return new Response(JSON.stringify({ article_ids: ['article'], items: [] }));
  });
  await getArchives('alice');
  await getSavedArticles('alice');
  await saveArticle('alice', 'article', 'edition');
  await unsaveArticle('alice', 'article');
  assert.deepEqual(calls, [
    { url: '/v1/archives?user_id=alice', method: 'GET', body: undefined },
    { url: '/v1/saved-articles?user_id=alice', method: 'GET', body: undefined },
    { url: '/v1/saved-articles/article?user_id=alice', method: 'PUT', body: { cover_id: 'edition' } },
    { url: '/v1/saved-articles/article?user_id=alice', method: 'DELETE', body: undefined },
  ]);
});

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
