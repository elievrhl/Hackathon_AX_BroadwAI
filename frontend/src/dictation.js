export const DICTATION_SECONDS = 90;
export const AUDIO_RATE = 24000;

export function canDictate(env = globalThis) {
  return !!(env.isSecureContext && env.navigator?.mediaDevices?.getUserMedia
    && env.MediaRecorder && (env.OfflineAudioContext || env.webkitOfflineAudioContext));
}

export function appendDictation(draft, transcript, limit = 2000) {
  const combined = [draft.trimEnd(), transcript.trim()].filter(Boolean).join(' ');
  let text = combined.slice(0, limit);
  // Do not leave half an emoji at the textarea's UTF-16 character boundary.
  if (/[\uD800-\uDBFF]$/.test(text)) text = text.slice(0, -1);
  return { text, truncated: combined.length > text.length };
}

export function microphoneError(error) {
  if (['NotAllowedError', 'PermissionDeniedError', 'SecurityError'].includes(error?.name)) return 'Autorisez le microphone dans votre navigateur pour dicter un message.';
  if (error?.name === 'NotFoundError') return 'Aucun microphone détecté. Branchez un micro puis réessayez.';
  if (error?.name === 'NotReadableError') return 'Le microphone est occupé. Fermez l’application qui l’utilise puis réessayez.';
  return 'Le microphone n’a pas pu démarrer. Vous pouvez toujours écrire votre message.';
}

export function encodeWav(buffer) {
  if (buffer.sampleRate !== AUDIO_RATE || !buffer.numberOfChannels) throw new Error('Invalid audio');
  const frames = Math.min(buffer.length, AUDIO_RATE * DICTATION_SECONDS);
  if (frames < AUDIO_RATE / 4) throw new Error('Parlez quelques secondes avant d’arrêter la dictée.');
  const data = new ArrayBuffer(44 + frames * 2);
  const view = new DataView(data);
  const label = (offset, value) => [...value].forEach((character, i) => view.setUint8(offset + i, character.charCodeAt(0)));
  label(0, 'RIFF'); view.setUint32(4, 36 + frames * 2, true); label(8, 'WAVE');
  label(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, 1, true); view.setUint32(24, AUDIO_RATE, true);
  view.setUint32(28, AUDIO_RATE * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  label(36, 'data'); view.setUint32(40, frames * 2, true);
  const channels = Array.from({ length: buffer.numberOfChannels }, (_, i) => buffer.getChannelData(i));
  for (let i = 0; i < frames; i++) {
    const sample = Math.max(-1, Math.min(1, channels.reduce((sum, channel) => sum + channel[i], 0) / channels.length));
    view.setInt16(44 + i * 2, Math.round(sample * (sample < 0 ? 32768 : 32767)), true);
  }
  return new Blob([data], { type: 'audio/wav' });
}

// A session owns its microphone, buffers, timer and upload. Closing the dialog or
// switching accounts invalidates even a late permission grant / transcription.
export class DictationSession {
  constructor({ transcribe, onState, onTranscript, onError, env = globalThis }) {
    Object.assign(this, { transcribe, onState, onTranscript, onError, env });
    this.current = null;
  }

  async start() {
    if (this.current) return;
    const session = { chunks: [], bytes: 0, abort: new AbortController() };
    this.current = session;
    this.onState('requesting');
    try {
      const stream = await this.env.navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      if (this.current !== session) { stream.getTracks().forEach(track => track.stop()); return; }
      session.stream = stream;
      const mimeType = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'].find(type => this.env.MediaRecorder.isTypeSupported?.(type));
      const recorder = new this.env.MediaRecorder(stream, { ...(mimeType ? { mimeType } : {}), audioBitsPerSecond: 64000 });
      session.recorder = recorder;
      recorder.ondataavailable = event => {
        if (this.current !== session || !event.data.size) return;
        session.bytes += event.data.size;
        if (session.bytes > 10 * 1024 * 1024) { this.fail(session, 'Cette dictée est trop longue. Essayez un message plus court.'); return; }
        session.chunks.push(event.data);
      };
      recorder.onerror = () => this.fail(session, 'La dictée a été interrompue. Votre message écrit est conservé.');
      recorder.onstop = () => this.finish(session);
      stream.getAudioTracks().forEach(track => { track.onended = () => this.stop(); });
      recorder.start(1000);
      session.timer = this.env.setTimeout(() => this.stop(), DICTATION_SECONDS * 1000);
      this.onState('recording');
    } catch (error) { this.fail(session, microphoneError(error)); }
  }

  releaseMicrophone(session) {
    this.env.clearTimeout(session.timer);
    session.stream?.getTracks().forEach(track => { track.onended = null; track.stop(); });
  }

  stop() {
    const session = this.current;
    if (!session || session.recorder?.state !== 'recording') return;
    this.onState('transcribing');
    session.recorder.stop();
    this.releaseMicrophone(session);
  }

  async finish(session) {
    if (this.current !== session) return;
    this.releaseMicrophone(session);
    this.onState('transcribing');
    try {
      const blob = new Blob(session.chunks, { type: session.recorder.mimeType });
      session.chunks = [];
      if (!blob.size) throw new Error('Aucun son enregistré. Réessayez en parlant près du micro.');
      const AudioDecoder = this.env.OfflineAudioContext || this.env.webkitOfflineAudioContext;
      const decoder = new AudioDecoder(1, 1, AUDIO_RATE);
      const audio = encodeWav(await decoder.decodeAudioData(await blob.arrayBuffer()));
      if (this.current !== session) return;
      const result = await this.transcribe(audio, session.abort.signal);
      if (this.current !== session) return;
      if (typeof result?.text !== 'string' || !result.text.trim()) throw new Error('Aucune parole reconnue. Réessayez en parlant près du micro.');
      this.current = null;
      this.onTranscript(result.text);
      this.onState('idle');
    } catch (error) {
      this.fail(session, error.name === 'EncodingError' ? 'Le son n’a pas pu être lu. Essayez une nouvelle dictée.' : error.message || 'La dictée n’a pas pu être transcrite. Réessayez.');
    }
  }

  fail(session, message) {
    if (this.current !== session) return;
    this.cancel();
    this.onError(message);
  }

  cancel() {
    const session = this.current;
    this.current = null;
    if (!session) return;
    session.abort.abort();
    if (session.recorder) {
      session.recorder.onstop = null;
      session.recorder.ondataavailable = null;
      session.recorder.onerror = null;
      if (session.recorder.state !== 'inactive') session.recorder.stop();
    }
    this.releaseMicrophone(session);
    session.chunks = [];
    this.onState('idle');
  }
}
