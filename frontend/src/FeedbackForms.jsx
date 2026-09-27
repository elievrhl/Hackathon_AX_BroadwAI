import { useEffect, useRef, useState } from 'react';

import { ACTIONS, TARGETS, FORMATS, LEVELS, EMPTY_PREFERENCE, REASONS, preferenceValue, preferenceSummary, impactText } from './preferences.js';

function PreferenceFields({ value, onChange, size }) {
  const change = (key, next) => onChange({ ...value, [key]: next });
  const choices = value.target_kind === 'content_type' ? FORMATS : value.target_kind === 'level' ? LEVELS : null;
  return <>
    <div className="feedback-field-grid">
      <label className="field">Effet souhaité<select value={value.action} onChange={e => change('action', e.target.value)}>{Object.entries(ACTIONS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label className="field">Ce que cela concerne<select value={value.target_kind} onChange={e => onChange({ ...value, target_kind: e.target.value, target: e.target.value === 'content_type' ? 'analysis' : e.target.value === 'level' ? 'beginner' : '' })}>{Object.entries(TARGETS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    </div>
    <label className="field">{value.target_kind === 'source' ? 'Domaine de la source' : 'Sujet ou caractéristique visée'}{choices
      ? <select value={value.target} onChange={e => change('target', e.target.value)}>{Object.entries(choices).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
      : <input required minLength={2} maxLength={150} value={value.target} onChange={e => change('target', e.target.value)} placeholder={value.target_kind === 'source' ? 'example.org' : value.target_kind === 'treatment' ? 'Les articles promotionnels sur l’IA' : 'L’histoire des sciences'} />}</label>
    <label className="field">Nuancer ou réexpliquer <span className="optional">Facultatif</span><textarea rows={3} maxLength={1000} value={value.explanation} onChange={e => change('explanation', e.target.value)} placeholder="Par exemple : seulement sur les sujets que je connais déjà. Mon intérêt pour l’IA reste le même." /></label>
    <label className="field">Pendant combien de temps ?<select value={value.scope} onChange={e => change('scope', e.target.value)}><option value="persistent">Pour mes prochaines éditions</option><option value="next">Pour la prochaine édition seulement</option></select></label>
    <div className="preference-preview" aria-live="polite"><strong>{preferenceSummary(value)}</strong><p>{impactText(value.action, size)}</p><p>{value.scope === 'next' ? 'Valable pour la prochaine édition enregistrée contenant des articles, même partielle.' : 'Valable jusqu’à votre prochaine correction ou suppression.'}</p></div>
  </>;
}

export function ArticleFeedback({ article, feedback, onFeedback, onMemory, size }) {
  const [kind, setKind] = useState(feedback?.kind || 'not_interested');
  const [reason, setReason] = useState(feedback?.reason || 'other');
  const [comment, setComment] = useState(feedback?.comment || '');
  const [future, setFuture] = useState(false);
  const [value, setValue] = useState({ ...EMPTY_PREFERENCE, action: 'less' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const preferenceId = useRef(crypto.randomUUID());
  const lock = useRef(false);
  useEffect(() => {
    if (feedback) { setKind(feedback.kind); setReason(feedback.reason || 'other'); setComment(feedback.comment || ''); }
  }, [feedback]);
  async function submit(payload) {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError('');
    try { await onFeedback(payload); }
    catch (e) { setError(e.message); }
    finally { lock.current = false; setBusy(false); }
  }
  return <section className="article-feedback" aria-label="Votre avis sur cet article">
    <div className="feedback-options">{[['useful', 'Pertinent'], ['already_known', 'Déjà vu'], ['not_interested', 'Pas pour moi']].map(([key, label]) => <button key={key} className="secondary-button" disabled={busy} aria-pressed={feedback?.kind === key} onClick={() => { setKind(key); if (feedback?.kind !== key) submit({ kind: key }); }}>{label}</button>)}</div>
    <details><summary>Expliquer ou préciser pour la suite</summary><form onSubmit={e => { e.preventDefault(); submit({ kind, reason, comment, ...(future && !feedback?.preference_id ? { preference: { ...preferenceValue(value), id: preferenceId.current } } : {}) }); }}><fieldset disabled={busy}>
      <label className="field">Votre avis<select value={kind} onChange={e => setKind(e.target.value)}><option value="not_interested">Pas pour moi</option><option value="useful">Pertinent</option><option value="already_known">Déjà vu</option></select></label>
      <label className="field">Ce qui motive votre avis<select value={reason} onChange={e => setReason(e.target.value)}>{Object.entries(REASONS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label className="field">Votre explication <span className="optional">Facultatif</span><textarea rows={3} maxLength={1000} value={comment} onChange={e => setComment(e.target.value)} placeholder="Cet article était trop introductif, mais le sujet m’intéresse toujours…" /></label>
      {feedback?.preference_id ? <button type="button" className="secondary-button" onClick={onMemory}>Voir ou corriger la préférence associée</button> : <><label className="future-feedback"><input type="checkbox" checked={future} onChange={e => setFuture(e.target.checked)} /> Ajuster aussi mes prochaines lectures</label>{future ? <PreferenceFields value={value} onChange={setValue} size={size} /> : <p className="field-help">Ce retour concerne uniquement cet article. Il ne changera pas vos sujets habituels.</p>}</>}
      <button className="primary-button" type="submit">{busy ? 'Enregistrement…' : 'Enregistrer mon retour'}</button>
    </fieldset></form></details>
    {error && <p className="reader-error" role="alert">{error}</p>}
  </section>;
}
