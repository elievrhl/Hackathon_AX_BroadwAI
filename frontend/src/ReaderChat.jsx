import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowUp, Check, Feather, NotebookPen } from 'lucide-react';
import { getPreferences, getReaderMessages, sendReaderMessage } from './api.js';
import { TOPICS, toCoverRequest } from './reader.js';
import { preferenceSummary } from './preferences.js';
import './reader-chat.css';

const IDEAS = [
  ['Explorer un sujet', 'J’aimerais découvrir l’histoire des sciences.'],
  ['Plus de recul', 'Moins d’actualités à chaud, plus d’analyses de fond.'],
  ['Une envie du moment', 'Pour la prochaine édition, j’aimerais lire aussi sur l’architecture.'],
];
const CHANGE_LABELS = { added: 'Ajouté', updated: 'Ajusté', removed: 'Retiré' };

function Signature() {
  return <div className="chat-signature"><span className="chat-avatar" aria-hidden="true">k.</span><strong>Kiosque</strong><span>Votre rédacteur</span></div>;
}

export default function ReaderChat({ userId, profile, generating, open }) {
  const [rows, setRows] = useState([]);
  const [turns, setTurns] = useState([]);
  const [draft, setDraft] = useState('');
  const [pending, setPending] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [loadFailed, setLoadFailed] = useState(false);
  const [highlighted, setHighlighted] = useState([]);
  const [showDossier, setShowDossier] = useState(false);
  const attempt = useRef(null);
  const lock = useRef(false);
  const input = useRef(null);
  const conversation = useRef(null);
  const alive = useRef(true);
  const dossierTitle = useRef(null);

  async function load() {
    setLoading(true); setError('');
    try {
      const [preferences, messages] = await Promise.all([getPreferences(userId), getReaderMessages(userId)]);
      if (alive.current) { setRows(preferences); setTurns(messages); setLoadFailed(false); }
    } catch (e) {
      if (alive.current) { setError(e.message); setLoadFailed(true); }
    } finally { if (alive.current) setLoading(false); }
  }
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, [userId]);
  useEffect(() => { if (open && !lock.current) load(); }, [userId, open]);
  useEffect(() => {
    if (open && !loading && !showDossier) input.current?.focus({ preventScroll: true });
  }, [open, loading, showDossier]);
  useEffect(() => {
    if (open && conversation.current) conversation.current.scrollTop = turns.length || pending ? conversation.current.scrollHeight : 0;
  }, [turns, pending, open, loading, showDossier]);

  async function send(event) {
    event.preventDefault();
    const message = draft.trim();
    if (lock.current || loading || loadFailed || message.length < 2) return;
    lock.current = true;
    // Reuse the message id after an uncertain network result; the server replays it safely.
    if (attempt.current?.message !== message) attempt.current = { id: crypto.randomUUID(), message };
    const outgoing = attempt.current;
    setPending(outgoing); setError(''); setHighlighted([]);
    try {
      const turn = await sendReaderMessage(userId, { ...outgoing, profile: toCoverRequest(profile, userId).profile });
      if (!alive.current) return;
      setTurns(previous => [...previous.filter(item => item.id !== turn.id), turn].slice(-30));
      // Fetch the current fiche even on an idempotent replay of an older message.
      try { setRows(await getPreferences(userId)); }
      catch { setLoadFailed(true); setError('Le message est enregistré. Actualisez pour retrouver votre fiche.'); }
      setHighlighted(turn.changes.filter(change => change.kind !== 'removed').map(change => change.preference.id));
      setDraft(''); attempt.current = null;
    } catch (e) {
      if (alive.current) setError(e.message);
    } finally {
      lock.current = false;
      if (alive.current) { setPending(null); if (input.current?.getClientRects().length) input.current.focus({ preventScroll: true }); }
    }
  }
  function choose(text) { setDraft(text); input.current?.focus(); }
  function viewDossier() { setShowDossier(true); }
  useEffect(() => {
    if (open && showDossier) dossierTitle.current?.focus({ preventScroll: true });
  }, [open, showDossier]);
  const active = rows.filter(row => row.status === 'active');
  const applied = rows.filter(row => row.status === 'applied');
  const latest = turns.at(-1);

  return <div className={`reader-chat${showDossier ? ' is-dossier-open' : ''}`}>
    <header className="chat-heading">
      <div><span className="eyebrow"><Feather size={14} aria-hidden="true" /> LE COURRIER DU LECTEUR</span><h2 id="memory-title">Écrire à Kiosque</h2></div>
      <button className="dossier-toggle" type="button" aria-expanded={showDossier} aria-controls="reader-dossier" onClick={() => setShowDossier(value => !value)}>{showDossier ? <ArrowLeft size={16} aria-hidden="true" /> : <NotebookPen size={16} aria-hidden="true" />}<span>{showDossier ? 'Revenir au message' : 'Ma fiche'}</span>{!showDossier && !!highlighted.length && <span className="dossier-update-dot" aria-label="Fiche mise à jour" />}</button>
    </header>
    <div className="chat-workspace">
      <section className="chat-main" aria-label="Conversation avec Kiosque">
        <div className={`chat-messages${!turns.length && !pending ? ' is-empty' : ''}`} ref={conversation} role="log" aria-label="Messages" aria-live="polite" aria-relevant="additions text" tabIndex={0}>
          {!turns.length && !pending && <div className="chat-welcome"><span className="welcome-feather" aria-hidden="true"><Feather size={28} strokeWidth={1.2} /></span><h3>Qu’avez-vous envie de lire ?</h3><p>Un sujet qui vous intrigue, une envie de changement…<br /> Je le retiendrai pour vos prochaines lectures.</p></div>}
          {loading && <p className="chat-loading" role="status">J’ouvre notre conversation…</p>}
          {!loading && !turns.length && !pending && <div className="chat-ideas" aria-label="Idées de messages">{IDEAS.map(([label, text]) => <button key={label} type="button" onClick={() => choose(text)} disabled={loadFailed}>{label}</button>)}</div>}
          {turns.map(turn => <div className="chat-turn" key={turn.id}>
            <div className="chat-user-message"><span>Vous</span><p>{turn.message}</p></div>
            <div className="chat-reply"><Signature /><p>{turn.reply}</p>
              {!!turn.changes.length && <div className="chat-receipt"><button type="button" className="chat-receipt-title" onClick={viewDossier}><Check size={15} aria-hidden="true" /> Fiche mise à jour <span>· Voir</span></button><details><summary>{turn.changes.length} ajustement{turn.changes.length > 1 ? 's' : ''} retenu{turn.changes.length > 1 ? 's' : ''}</summary><ul>{turn.changes.map((change, i) => <li key={i}><span>{CHANGE_LABELS[change.kind]}</span>{preferenceSummary(change.preference)}{change.preference.scope === 'next' && <small>Pour la prochaine édition</small>}</li>)}</ul></details></div>}
            </div>
          </div>)}
          {pending && <div className="chat-turn"><div className="chat-user-message"><span>Vous · envoi en cours</span><p>{pending.message}</p></div><div className="chat-reply"><Signature /><div className="chat-reading" role="status"><span aria-hidden="true"><i /><i /><i /></span>Kiosque lit votre message…</div></div></div>}
        </div>
        <form className="chat-composer" onSubmit={send}>
          {generating && <p className="chat-generation-note">Une édition est en préparation. Ce message guidera la suivante.</p>}
          {error && <div className="chat-error" role="alert">{error}{loadFailed && <button type="button" onClick={load} disabled={loading}>Actualiser la conversation</button>}</div>}
          <label className="sr-only" htmlFor="reader-message">Votre message à Kiosque</label>
          <div className="chat-input-wrap"><textarea id="reader-message" ref={input} rows={2} maxLength={2000} value={draft} disabled={loading || loadFailed} readOnly={!!pending} onChange={e => setDraft(e.target.value)} placeholder="En ce moment, j’aimerais lire…" aria-describedby="chat-input-help" onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); e.currentTarget.form.requestSubmit(); } }} /><button type="submit" aria-label="Envoyer le message" title="Envoyer le message (Entrée)" disabled={!!pending || loading || loadFailed || draft.trim().length < 2}><ArrowUp size={21} aria-hidden="true" /></button></div>
          <span className="sr-only" id="chat-input-help">Entrée pour envoyer. Maj + Entrée pour une nouvelle ligne. 2 000 caractères maximum.</span>
          <div className="chat-composer-footer"><span>Messages lus par l’IA · crédits du serveur</span>{draft.length > 1800 && <span>{draft.length}/2 000</span>}</div>
        </form>
      </section>
      <aside className="reader-dossier" id="reader-dossier" aria-labelledby="dossier-title" hidden={!showDossier}>
        <h3 id="dossier-title" ref={dossierTitle} tabIndex={-1}>Votre fiche lecteur</h3>
        <p className="dossier-name">{profile.name}</p>
        <div className="dossier-subjects"><h4>Vos sujets de départ</h4><div>{profile.topics.map(id => <span key={id}>{TOPICS.find(topic => topic.id === id)?.short}</span>)}</div></div>
        {profile.notes && <div className="dossier-context"><h4>Votre contexte</h4><p>{profile.notes}</p></div>}
        <div className="dossier-preferences"><h4>Ce que je retiens</h4>
          {loading ? <p>Ouverture de la fiche…</p> : loadFailed ? <p>La fiche n’a pas pu être chargée.</p> : active.length ? <ul>{active.map(row => <li key={`${row.id}:${row.revision}`} className={highlighted.includes(row.id) ? 'dossier-changed' : ''}><span className="dossier-rule-dot" aria-hidden="true" /><div><strong>{preferenceSummary(row)}</strong>{row.explanation && <p>{row.explanation}</p>}<small>{row.scope === 'next' ? 'Prochaine édition seulement' : 'Pour vos prochaines éditions'}</small></div></li>)}</ul> : <p className="dossier-empty">Vos envies trouveront leur place ici, au fil de la conversation.</p>}
        </div>
        {!!applied.length && <details className="dossier-applied"><summary>Envies ponctuelles réalisées ({applied.length})</summary>{applied.map(row => <p key={row.id}>{preferenceSummary(row)} · <a href={`?cover=${encodeURIComponent(row.applied_cover_id)}`}>Voir l’édition</a></p>)}</details>}
        <p className="dossier-footnote">Un autre message suffit pour ajuster cette fiche.</p>
        {!!latest?.changes.length && <p className="dossier-saved"><Check size={14} aria-hidden="true" /> Enregistrée pour vos prochaines lectures</p>}
      </aside>
    </div>
  </div>;
}
