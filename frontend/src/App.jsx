import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Check, RefreshCw } from 'lucide-react';
import { Onboarding, Preferences, ArticleDetail } from './components.jsx';
import Newspaper from './Newspaper.jsx';
import { getLibrary, saveEdition, removeEdition } from './api.js';
import { readLocal, accountKey, currentAccount, leaveAccount } from './accounts.js';
import Library, { AccountScreen, AccountNav, SaveEdition } from './Library.jsx';
import { DEFAULT_PROFILE, STORAGE_KEY, normalizeProfile, toCoverRequest, adaptCover, formatDate } from './reader.js';
import { getHealth, listCovers, getCover, createCover, sendFeedback, getLikes, setLike } from './api.js';

const STATUS_LABELS = { complete: 'complète', partial: 'partielle', fallback: 'secours' };

export default function App() {
  const [account, setAccount] = useState(currentAccount);
  function logout() {
    leaveAccount();
    const url = new URL(window.location.href);
    url.searchParams.delete('cover');
    window.history.replaceState(null, '', url);
    setAccount(null);
  }
  return account ? <ReaderApp key={account.id} account={account} onLogout={logout} /> : <AccountScreen onEnter={setAccount} />;
}

function ReaderApp({ account, onLogout }) {
  const userId = account.id;
  const read = (key, fallback = null) => readLocal(accountKey(userId, key), fallback);
  const [view, setView] = useState('journal');
  const [editions, setEditions] = useState([]);
  const [libraryLoading, setLibraryLoading] = useState(true);
  const [libraryError, setLibraryError] = useState('');
  const [libraryPending, setLibraryPending] = useState('');
  const libraryLock = useRef(false);
  const [linkedCoverId] = useState(() => new URLSearchParams(window.location.search).get('cover'));
  const [profile, setProfile] = useState(() => normalizeProfile(read(STORAGE_KEY)));
  const [cover, setCover] = useState(null);
  const [history, setHistory] = useState([]);
  const [health, setHealth] = useState(null);
  const [preferences, setPreferences] = useState(false);
  const [article, setArticle] = useState(null);
  const [saved, setSaved] = useState(() => {
    const value = read('kiosque.saved', []);
    return Array.isArray(value) ? value.filter(id => typeof id === 'string') : [];
  });
  const [feedback, setFeedback] = useState({});
  const [liked, setLiked] = useState([]);
  const [likesReady, setLikesReady] = useState(false);
  const [liking, setLiking] = useState([]);
  const pendingLikes = useRef(new Set());
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('loading');
  const [elapsed, setElapsed] = useState(0);
  const inFlight = useRef(false);
  const pendingFeedback = useRef(new Set());

  function persist(key, value) {
    try { localStorage.setItem(accountKey(userId, key), JSON.stringify(value)); }
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
      const [healthResult, historyResult, likesResult, libraryResult] = await Promise.allSettled([getHealth(), listCovers(userId), getLikes(userId), getLibrary(userId)]);
      if (!active) return;
      if (libraryResult.status === 'fulfilled') setEditions(libraryResult.value);
      else setLibraryError(libraryResult.reason.message);
      setLibraryLoading(false);
      if (likesResult.status === 'fulfilled') { setLiked(likesResult.value.article_ids); setLikesReady(true); }
      else setNotice('Les likes sont indisponibles. Rechargez la page pour réessayer.');
      if (healthResult.status === 'fulfilled') setHealth(healthResult.value);
      if (historyResult.status === 'fulfilled') setHistory(historyResult.value);
      else setError(historyResult.reason.message);
      const previous = linkedCoverId || read('kiosque.lastCover');
      if (typeof previous === 'string') {
        try {
          const raw = await getCover(previous, userId);
          if (active) displayCover(raw);
        } catch (reason) { if (active) setError(reason.message); }
      }
      if (active) {
        if (read('kiosque.pending')) setNotice('Une génération a été lancée avant de quitter la page. Actualisez l’historique pour retrouver son résultat.');
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
    try {
      displayCover(await getCover(id, userId));
      if (!profile) saveProfile({ ...DEFAULT_PROFILE, name: account.name });
      setView('journal');
    }
    catch (reason) { setError(reason.message); }
    finally { inFlight.current = false; setBusy(''); }
  }
  async function refreshHistory() {
    if (inFlight.current || busy) return;
    inFlight.current = true; setBusy('loading'); setError('');
    try {
      const [rows, status] = await Promise.all([listCovers(userId), getHealth()]);
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
      setNotice(`${raw.items.length} articles reçus. Vous pouvez sauvegarder cette revue dans votre bibliothèque.`);
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
  async function toggleLike(selected) {
    if (!likesReady || cover?.userId !== userId || pendingLikes.current.has(selected.id)) return;
    pendingLikes.current.add(selected.id);
    setLiking([...pendingLikes.current]);
    try {
      const result = await setLike({ user_id: userId, cover_id: cover.id, article_id: selected.id, liked: !liked.includes(selected.id) });
      setLiked(previous => result.liked ? [...new Set([...previous, selected.id])] : previous.filter(id => id !== selected.id));
    } catch (reason) { setNotice(`Like non enregistré : ${reason.message}`); }
    finally { pendingLikes.current.delete(selected.id); setLiking([...pendingLikes.current]); }
  }
  function reset() {
    persist(STORAGE_KEY, null); setPreferences(false); setProfile(null); setArticle(null);
    // Keep the device identity, bookmarks and server editions; no account is deleted.
  }

  async function refreshLibrary() {
    setLibraryLoading(true); setLibraryError('');
    try { setEditions(await getLibrary(userId)); }
    catch (reason) { setLibraryError(reason.message); }
    finally { setLibraryLoading(false); }
  }
  async function changeLibrary(id, remove = false) {
    if (libraryLock.current) return;
    libraryLock.current = true; setLibraryPending(id);
    try {
      await (remove ? removeEdition(userId, id) : saveEdition(userId, id));
      if (remove) setEditions(rows => rows.filter(row => row.id !== id));
      await refreshLibrary();
      setNotice(remove ? 'Revue retirée de la bibliothèque. Elle reste dans votre historique.' : 'Revue sauvegardée dans Ma bibliothèque.');
    } catch (reason) { setNotice(`Sauvegarde non modifiée : ${reason.message}`); }
    finally { libraryLock.current = false; setLibraryPending(''); }
  }
  function navigate(next) {
    setView(next); setArticle(null); setError('');
    if (next === 'library') refreshLibrary();
  }

  return <>
    <a className="skip-link" href="#main">Aller au contenu</a>
    <AccountNav account={account} view={view} onView={navigate} onLogout={onLogout} disabled={!!busy || !!libraryPending} />
    {view === 'library' ? <Library editions={editions} loading={libraryLoading} error={libraryError || error} pending={libraryPending || busy} onRetry={refreshLibrary} onOpen={openCover} onRemove={id => changeLibrary(id, true)} onJournal={() => navigate('journal')} /> : profile ? <Newspaper liked={liked} liking={liking} canLike={likesReady && cover?.userId === userId} onLike={toggleLike} profile={profile} cover={cover} saved={saved} onSave={toggleSaved} onOpen={setArticle} onPreferences={() => setPreferences(true)} busy={!!busy}>
      <section className="reader-controls" aria-label="Gestion de votre édition">
        {cover && <SaveEdition saved={editions.some(row => row.id === cover.id)} busy={!!busy || !!libraryPending || libraryLoading} onSave={() => changeLibrary(cover.id)} />}
        <details className="edition-management" open={cover ? undefined : true}>
        <summary>Préparer ou retrouver une édition</summary>
        <div className="generation-row"><div><strong>{cover ? 'La prochaine édition vous attend.' : 'Composez votre première une.'}</strong><p>{profile.size} articles souhaités · recherche web et découverte de sources activées</p><p className="field-help">La génération consomme des crédits. À leur premier affichage, les nouvelles images font aussi l’objet d’une vérification facturée ; son résultat est ensuite réutilisé.</p></div><button className="primary-button" disabled={!!busy || health?.llm_configured === false} onClick={generate}>{busy === 'generating' ? 'Préparation en cours…' : 'Générer ma une'}<ArrowRight size={18} /></button></div>
        <div className="history-row"><label htmlFor="edition-history">Mon historique de revues</label><select id="edition-history" value={cover?.id || ''} disabled={!!busy} onChange={event => openCover(event.target.value)}><option value="" disabled>Choisir une édition déjà générée</option>{history.map(row => <option key={row.id} value={row.id}>{formatDate(row.created_at)} · {row.item_count} articles · {STATUS_LABELS[row.status] || row.status} · {row.title}</option>)}</select><button className="text-button" onClick={refreshHistory} disabled={!!busy}><RefreshCw size={15} /> Actualiser</button></div>
        {!history.length && !busy && <p className="field-help">Aucune édition générée pour ce compte pour le moment.</p>}
        {cover && <a className="audit-link" href={`/admin/covers?id=${encodeURIComponent(cover.id)}`} target="_blank" rel="noreferrer">Voir la construction de cette édition : sélection, résumés, outils et coût ↗</a>}
        </details>
        {health?.llm_configured === false && <p className="reader-error" role="alert">Le backend est accessible, mais sa clé API ou ses modèles ne sont pas configurés.</p>}
        {error && <p className="reader-error" role="alert">{error}</p>}
        {busy && <div className="generation-status" role="status"><span className="working-dot" /><span>{busy === 'generating' ? `Le rédacteur prépare votre édition… ${elapsed} s écoulées. Cela peut prendre plusieurs minutes. Vous pouvez continuer à lire l’édition affichée.` : 'Chargement des éditions…'}</span></div>}
      </section>
    </Newspaper> : <Onboarding initialName={account.name} onComplete={saveProfile} onExplore={() => { saveProfile({ ...DEFAULT_PROFILE, name: account.name }); if (history.length) openCover(history[0].id); }} />}
    {preferences && <Preferences profile={profile} onSave={saveProfile} onClose={() => setPreferences(false)} onReset={reset} />}
    {article && <ArticleDetail liked={liked.includes(article.id)} liking={liking.includes(article.id)} canLike={likesReady && cover?.userId === userId} onLike={toggleLike} article={article} saved={saved.includes(article.id)} onSave={toggleSaved} canFeedback={cover.userId === userId} feedback={feedback[`${cover.id}:${article.id}`]} notice={notice} onFeedback={recordFeedback} onRead={() => recordFeedback('open')} onClose={() => setArticle(null)} />}
    <div className={`toast ${notice ? 'visible' : ''}`} role="status" aria-live="polite">{notice && <><Check size={17} /><span>{notice}</span></>}</div>
  </>;
}
