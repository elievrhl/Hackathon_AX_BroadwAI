import test from 'node:test';
import assert from 'node:assert/strict';
import { AUDIO_RATE, DICTATION_SECONDS, DictationSession, appendDictation, canDictate, encodeWav, microphoneError } from './dictation.js';
import { setCsrfToken, transcribeDictation } from './api.js';

const flush = () => new Promise(resolve => setImmediate(resolve));
const audioBuffer = () => ({ sampleRate: AUDIO_RATE, length: AUDIO_RATE, numberOfChannels: 2, getChannelData: i => new Float32Array(AUDIO_RATE).fill(i ? 0 : 1) });

function harness({ permission, transcribe = async () => ({ text: 'De la science.' }) } = {}) {
  const tracks = [{ stopped: false, stop() { this.stopped = true; } }];
  const stream = { getTracks: () => tracks, getAudioTracks: () => tracks };
  const states = [], texts = [], errors = [], uploads = [], timers = [];
  class Recorder {
    static isTypeSupported(type) { return type.startsWith('audio/webm'); }
    constructor() { this.state = 'inactive'; this.mimeType = 'audio/webm'; }
    start() { this.state = 'recording'; }
    stop() {
      this.state = 'inactive';
      this.ondataavailable?.({ data: new Blob(['test-audio']) });
      this.onstop?.();
    }
  }
  const env = {
    isSecureContext: true,
    navigator: { mediaDevices: { getUserMedia: () => permission || Promise.resolve(stream) } },
    MediaRecorder: Recorder,
    OfflineAudioContext: class { async decodeAudioData() { return audioBuffer(); } },
    setTimeout: callback => { timers.push(callback); return timers.length; }, clearTimeout: () => {},
  };
  const session = new DictationSession({ env, onState: value => states.push(value), onTranscript: text => texts.push(text), onError: error => errors.push(error), transcribe: (...args) => { uploads.push(args); return transcribe(...args); } });
  return { session, env, states, texts, errors, tracks, stream, uploads, timers };
}

test('dictation appends without replacing the draft and reports the character limit', () => {
  assert.deepEqual(appendDictation('Plus de lecture. ', ' De la science. '), { text: 'Plus de lecture. De la science.', truncated: false });
  assert.deepEqual(appendDictation('a'.repeat(1998), '😀suite'), { text: `${'a'.repeat(1998)} `, truncated: true });
  assert.equal(appendDictation('', 'Bonjour').text, 'Bonjour');
});

test('capture only available with HTTPS/local secure context and supported APIs', () => {
  const { env } = harness();
  assert.equal(canDictate(env), true);
  assert.equal(canDictate({ ...env, isSecureContext: false }), false);
  assert.equal(canDictate({ ...env, MediaRecorder: undefined }), false);
});

test('WAV contains mono PCM audio, correct sample rate and duration', async () => {
  const blob = encodeWav(audioBuffer());
  const view = new DataView(await blob.arrayBuffer());
  assert.equal(blob.type, 'audio/wav');
  assert.equal(view.getUint32(24, true), AUDIO_RATE);
  assert.equal(view.getUint16(22, true), 1);
  assert.equal(view.getUint32(40, true), AUDIO_RATE * 2);
  assert.equal(view.getInt16(44, true), 16384);
});

test('stop releases microphone before transcription and returns editable text only', async () => {
  const h = harness();
  await h.session.start();
  assert.equal(h.states.at(-1), 'recording');
  assert.equal(h.uploads.length, 0);
  h.session.stop();
  assert.equal(h.tracks[0].stopped, true);
  await flush();
  assert.deepEqual(h.texts, ['De la science.']);
  assert.equal(h.states.at(-1), 'idle');
  assert.equal(h.uploads.length, 1);
  assert.deepEqual(h.errors, []);
});

test('closing while permission is pending stops a late microphone and sends nothing', async () => {
  let grant;
  const h = harness({ permission: new Promise(resolve => { grant = resolve; }) });
  const starting = h.session.start();
  h.session.cancel();
  grant(h.stream);
  await starting;
  assert.equal(h.tracks[0].stopped, true);
  assert.equal(h.uploads.length, 0);
  assert.deepEqual(h.texts, []);
});

test('cancel recording discards audio and does not transcribe', async () => {
  const h = harness();
  await h.session.start();
  h.session.cancel();
  await flush();
  assert.equal(h.tracks[0].stopped, true);
  assert.equal(h.uploads.length, 0);
  assert.equal(h.states.at(-1), 'idle');
});

test('cancel upload ignores a late response and aborts the request', async () => {
  let resolve;
  const h = harness({ transcribe: () => new Promise(done => { resolve = done; }) });
  await h.session.start(); h.session.stop(); await flush();
  h.session.cancel();
  assert.equal(h.uploads[0][1].aborted, true);
  resolve({ text: 'Must not enter another reader’s draft.' });
  await flush();
  assert.deepEqual(h.texts, []);
});

test('maximum-duration timer stops recording and transcribes once', async () => {
  const h = harness();
  await h.session.start(); await h.session.start();
  assert.equal(h.timers.length, 1);
  h.timers[0](); h.session.stop(); await flush();
  assert.equal(h.uploads.length, 1);
  assert.equal(h.tracks[0].stopped, true);
  assert.equal(DICTATION_SECONDS, 90);
});

test('permission denial and provider errors preserve draft by emitting no text', async () => {
  const denied = new Error('denied'); denied.name = 'NotAllowedError';
  const h = harness({ permission: Promise.reject(denied) });
  await h.session.start();
  assert.match(h.errors[0], /Autorisez le microphone/);
  assert.equal(h.states.at(-1), 'idle');
  assert.deepEqual(h.texts, []);
  const failed = harness({ transcribe: async () => { throw new Error('Service indisponible'); } });
  await failed.session.start(); failed.session.stop(); await flush();
  assert.deepEqual(failed.errors, ['Service indisponible']);
  assert.deepEqual(failed.texts, []);
  assert.match(microphoneError({ name: 'NotFoundError' }), /Aucun microphone/);
});

test('audio upload uses authenticated request without sending a chat message or retrying', async () => {
  const previous = globalThis.fetch;
  const calls = [];
  try {
    setCsrfToken('csrf-test');
    globalThis.fetch = async (url, options) => { calls.push({ url, options }); return new Response(JSON.stringify({ text: 'Bonjour' })); };
    const audio = encodeWav(audioBuffer());
    assert.deepEqual(await transcribeDictation('alice', audio), { text: 'Bonjour' });
    assert.equal(calls[0].url, '/v1/readers/alice/dictation');
    assert.equal(calls[0].options.body, audio);
    assert.equal(calls[0].options.headers['X-Kiosque-CSRF'], 'csrf-test');
    assert.equal(calls[0].options.headers['Content-Type'], 'audio/wav');
    globalThis.fetch = async () => { calls.push({}); return new Response('{}', { status: 503 }); };
    await assert.rejects(transcribeDictation('alice', audio));
    assert.equal(calls.length, 2);
  } finally { globalThis.fetch = previous; setCsrfToken(null); }
});
