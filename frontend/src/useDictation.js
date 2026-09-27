import { useEffect, useRef, useState } from 'react';
import { getDictation, transcribeDictation } from './api.js';
import { canDictate, DictationSession } from './dictation.js';

export default function useDictation({ userId, open, onTranscript }) {
  const [state, setState] = useState('idle');
  const [available, setAvailable] = useState(false);
  const [error, setError] = useState('');
  const [seconds, setSeconds] = useState(0);
  const session = useRef(null);
  const busy = useRef(false);
  const transcript = useRef(onTranscript);
  transcript.current = onTranscript;

  useEffect(() => {
    if (!open) return;
    let alive = true;
    const controller = new AbortController();
    setAvailable(false); setError(''); setState('idle');
    const dictation = new DictationSession({
      transcribe: (audio, signal) => transcribeDictation(userId, audio, signal),
      onState: value => { busy.current = value !== 'idle'; if (alive) setState(value); },
      onTranscript: text => { if (alive) transcript.current(text); },
      onError: message => { if (alive) setError(message); },
    });
    session.current = dictation;
    if (canDictate()) getDictation(userId, controller.signal).then(result => {
      if (alive) setAvailable(result.enabled);
    }).catch(() => { /* Typing remains available when dictation is unavailable. */ });
    const hide = () => {
      if (document.hidden && busy.current) {
        dictation.cancel();
        setError('La dictée a été annulée en quittant la page. Votre message écrit est conservé.');
      }
    };
    document.addEventListener('visibilitychange', hide);
    return () => {
      alive = false; controller.abort(); dictation.cancel(); busy.current = false;
      document.removeEventListener('visibilitychange', hide);
      if (session.current === dictation) session.current = null;
    };
  }, [userId, open]);

  useEffect(() => {
    setSeconds(0);
    if (state !== 'recording') return;
    const started = Date.now();
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [state]);

  return {
    state, seconds, available, error, busy,
    start: () => { setError(''); if (available) session.current?.start(); },
    stop: () => session.current?.stop(),
    cancel: () => session.current?.cancel(),
  };
}
