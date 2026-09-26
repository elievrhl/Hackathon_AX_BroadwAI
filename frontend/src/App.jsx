import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Check, RefreshCw } from 'lucide-react';
import { Onboarding, Preferences, ArticleDetail } from './components.jsx';
import Newspaper from './Newspaper.jsx';
import { DEFAULT_PROFILE, STORAGE_KEY, normalizeProfile, toCoverRequest, adaptCover, formatDate } from './reader.js';
import { getHealth, listCovers, getCover, createCover, sendFeedback } from './api.js';

function readLocal(key, fallback = null) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
}
function localIdentity() {
  const existing = readLocal('kiosque.user');
  if (typeof existing === 'string' && /^local-[a-z0-9-]{1,80}$/i.test(existing)) return existing;
  const id = `local-${crypto.randomUUID()}`;
  try { localStorage.setItem('kiosque.user', JSON.stringify(id)); } catch { /* In-memory identity still works. */ }
  return id;
}
const STATUS_LABELS = { complete: 'complète', partial: 'partielle', fallback: 'secours' };

export default function App() {
  const [userId] = useState(localIdentity);
  const [linkedCoverId] = useState(() => new URLSearchParams(window.location.search).get('cover'));
  const [profile, setProfile] = useState(() => normalizeProfile(readLocal(STORAGE_KEY)) || (linkedCoverId ? DEFAULT_PROFILE : null));
  const [cover, setCover] = useState(null);
  const [history, setHistory] = useState([]);
  const [health, setHealth] = useState(null);
  const [preferences, setPreferences] = useState(false);
  const [article, setArticle] = useState(null);
  const [saved, setSaved] = useState(() => {
    const value = readLocal('kiosque.saved', []);
    return Array.isArray(value) ? value.filter(id => typeof id === 'string') : [];
  });
  const [feedback, setFeedback] = useState({});
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('loading');
  const [elapsed, setElapsed] = useState(0);
  const inFlight = useRef(false);
  const pendingFeedback = useRef(new Set());

  function persist(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); }
    catch { setNotice('Le stockage du navigateur est indisponible. Vos réglages restent disponibles pour cette visite.'); }
  }
  function displayCover(raw) {
    const next = adaptCover(raw);
    setCover(next);
    setArticle(null);
    persist('kiosque.lastCover', next.id);
    const url = new URL(window.location.href);
    url.searchParams.set('cover', next.id);
    window.history.replaceState(null, '', url);
    // Direct links also work for editions older than the visible history page.
    setHistory(rows => rows.some(row => row.id === raw.id) ? rows : [...rows, {
      id: raw.id, title: raw.title, created_at: raw.created_at, status: raw.status, item_count: raw.items.length,
    }]);
  }
  useEffect(() => {
    let active = true;
    async function initialize() {
      const [healthResult, historyResult] = await Promise.allSettled([getHealth(), listCovers()]);
      if (!active) return;
      if (healthResult.status === 'fulfilled') setHealth(healthResult.value);
      if (historyResult.status === 'fulfilled') setHistory(historyResult.value);
      else setError(historyResult.reason.message);
      const previous = linkedCoverId || readLocal('kiosque.lastCover');
      if (typeof previous === 'string') {
        try {
          const raw = await getCover(previous);
          if (active) displayCover(raw);
        } catch (reason) { if (active) setError(reason.message); }
      }
      if (active) {
        if (readLocal('kiosque.pending')) setNotice('Une génération a été lancée avant de quitter la page. Actualisez l’historique pour retrouver son résultat.');
        setBusy('');
      }
    }
    initialize();
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(''), 7000);
    return () => clearTimeout(timer);
  }, [notice]);
  useEffect(() => {
    if (busy !== 'generating') return;
    const start = Date.now();
    setElapsed(0);
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000);
    const warn = event => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => { clearInterval(timer); window.removeEventListener('beforeunload', warn); };
  }, [busy]);

  function saveProfile(value) {
    const next = normalizeProfile(value);
    setProfile(next);
    persist(STORAGE_KEY, next);
    setPreferences(false);
    setArticle(null);
  }
  async function openCover(id) {
    if (!id || inFlight.current || busy) return;
    inFlight.current = true;
    setBusy('loading'); setError('');
    try { displayCover(await getCover(id)); }
    catch (reason) { setError(reason.message); }
    finally { inFlight.current = false; setBusy(''); }
  }
  async function refreshHistory() {
    if (inFlight.current || busy) return;
    inFlight.current = true; setBusy('loading'); setError('');
    try {
      const [rows, status] = await Promise.all([listCovers(), getHealth()]);
      setHistory(rows); setHealth(status);
    } catch (reason) { setError(reason.message); }
    finally { inFlight.current = false; setBusy(''); }
  }
  async function generate() {
    if (inFlight.current || busy) return;
    inFlight.current = true;
    setBusy('generating'); setError(''); setArticle(null);
    persist('kiosque.pending', Date.now());
    try {
      const raw = await createCover(toCoverRequest(profile, userId));
      displayCover(raw);
      // Preserve the result even if the next history refresh fails.
      setHistory(rows => [{ id: raw.id, title: raw.title, created_at: raw.created_at, status: raw.status, item_count: raw.items.length }, ...rows.filter(row => row.id !== raw.id)]);
      persist('kiosque.pending', null);
      setNotice(`${raw.items.length} articles reçus. Votre édition est enregistrée.`);
    } catch (reason) { setError(reason.message); }
    finally { inFlight.current = false; setBusy(''); }
  }
  function toggleSaved(id) {
    const next = saved.includes(id) ? saved.filter(item => item !== id) : [...saved, id];
    setSaved(next); persist('kiosque.saved', next);
    setNotice(next.includes(id) ? 'Article gardé dans ce navigateur.' : 'Article retiré de vos favoris.');
  }
  async function recordFeedback(kind, selected = article) {
    if (!selected || cover?.userId !== userId) return;
    const key = `${cover.id}:${selected.id}`;
    if (pendingFeedback.current.has(key)) return;
    pendingFeedback.current.add(key);
    try {
      await sendFeedback({ user_id: userId, cover_id: cover.id, article_id: selected.id, kind });
      if (kind !== 'open') { setFeedback(previous => ({ ...previous, [key]: kind })); setNotice('Votre retour a été enregistré.'); }
    } catch (reason) { setNotice(`Retour non enregistré : ${reason.message}`); }
    finally { pendingFeedback.current.delete(key); }
  }
  function reset() {
    persist(STORAGE_KEY, null); setPreferences(false); setProfile(null); setArticle(null);
    // Keep the device identity, bookmarks and server editions; no account is deleted.
  }

  return <>
    <a className="skip-link" href="#main">Aller au contenu</a>
    {profile ? <Newspaper profile={profile} cover={cover} saved={saved} onSave={toggleSaved} onOpen={setArticle} onPreferences={() => setPreferences(true)} busy={!!busy}>
      <section className="reader-controls" aria-label="Gestion de votre édition">
        <details className="edition-management" open={cover ? undefined : true}>
        <summary>Préparer ou retrouver une édition</summary>
        <div className="generation-row"><div><strong>{cover ? 'La prochaine édition vous attend.' : 'Composez votre première une.'}</strong><p>{profile.size} articles souhaités · recherche web et découverte de sources activées</p><p className="field-help">La génération utilise la clé API du serveur et consomme des crédits. La consultation des éditions enregistrées est gratuite.</p></div><button className="primary-button" disabled={!!busy || health?.llm_configured === false} onClick={generate}>{busy === 'generating' ? 'Préparation en cours…' : 'Générer ma une'}<ArrowRight size={18} /></button></div>
        <div className="history-row"><label htmlFor="edition-history">Éditions du serveur local</label><select id="edition-history" value={cover?.id || ''} disabled={!!busy} onChange={event => openCover(event.target.value)}><option value="" disabled>Choisir une édition déjà générée</option>{history.map(row => <option key={row.id} value={row.id}>{formatDate(row.created_at)} · {row.item_count} articles · {STATUS_LABELS[row.status] || row.status} · {row.title}</option>)}</select><button className="text-button" onClick={refreshHistory} disabled={!!busy}><RefreshCw size={15} /> Actualiser</button></div>
        {!history.length && !busy && <p className="field-help">Aucune édition enregistrée sur ce serveur pour le moment.</p>}
        {cover && <a className="audit-link" href={`/admin/covers?id=${encodeURIComponent(cover.id)}`} target="_blank" rel="noreferrer">Voir la construction de cette édition : sélection, résumés, outils et coût ↗</a>}
        </details>
        {health?.llm_configured === false && <p className="reader-error" role="alert">Le backend est accessible, mais sa clé API ou ses modèles ne sont pas configurés.</p>}
        {error && <p className="reader-error" role="alert">{error}</p>}
        {busy && <div className="generation-status" role="status"><span className="working-dot" /><span>{busy === 'generating' ? `Le rédacteur prépare votre édition… ${elapsed} s écoulées. Cela peut prendre plusieurs minutes. Vous pouvez continuer à lire l’édition affichée.` : 'Chargement des éditions…'}</span></div>}
      </section>
    </Newspaper> : <Onboarding onComplete={saveProfile} onExplore={() => { saveProfile(DEFAULT_PROFILE); if (history.length) openCover(history[0].id); }} />}
    {preferences && <Preferences profile={profile} onSave={saveProfile} onClose={() => setPreferences(false)} onReset={reset} />}
    {article && <ArticleDetail article={article} saved={saved.includes(article.id)} onSave={toggleSaved} canFeedback={cover.userId === userId} feedback={feedback[`${cover.id}:${article.id}`]} notice={notice} onFeedback={recordFeedback} onRead={() => recordFeedback('open')} onClose={() => setArticle(null)} />}
    <div className={`toast ${notice ? 'visible' : ''}`} role="status" aria-live="polite">{notice && <><Check size={17} /><span>{notice}</span></>}</div>
  </>;
}
