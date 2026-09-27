import test from 'node:test';
import assert from 'node:assert/strict';
import { getReaderMessages, sendReaderMessage } from './api.js';

test('reader messages preserve the request id, text and profile, with no automatic retry', async () => {
  const original = globalThis.fetch;
  const requests = [];
  const body = { id: 'stable-message-id', message: 'Moins de bruit, plus d’analyses.', profile: { user_id: 'local-test' } };
  try {
    globalThis.fetch = async (url, options) => {
      requests.push({ url, options });
      return new Response(JSON.stringify(options.method === 'POST' ? { ...body, changes: [] } : []));
    };
    assert.deepEqual(await getReaderMessages('local-test'), []);
    await sendReaderMessage('local-test', body);
    assert.equal(requests[1].url, '/v1/readers/local-test/messages');
    assert.deepEqual(JSON.parse(requests[1].options.body), body);
    globalThis.fetch = async () => { requests.push({}); return new Response(JSON.stringify({ detail: 'Kiosque lit déjà un message.' }), { status: 429 }); };
    await assert.rejects(sendReaderMessage('local-test', body), /Kiosque lit déjà un message/);
    assert.equal(requests.length, 3);
    globalThis.fetch = async () => { throw new Error('offline'); };
    await assert.rejects(sendReaderMessage('local-test', body), /Votre message est conservé/);
  } finally { globalThis.fetch = original; }
});
