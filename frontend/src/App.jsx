import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Check, MessageCircle, RefreshCw } from 'lucide-react';
import { Onboarding, Preferences, ArticleDetail, Modal } from './components.jsx';
import ReaderChat from './ReaderChat.jsx';
import { preferenceSummary } from './preferences.js';
import Newspaper from './Newspaper.jsx';
import { getCollections, getCollection, createCollection, editCollection, deleteCollection, addToCollection, removeFromCollection, importBookmarks } from './api.js';
import { readLocal, accountKey, currentAccount, leaveAccount } from './accounts.js';
import Library, { AccountScreen, AccountNav, SaveArticleDialog, CollectionForm } from './Library.jsx';
import { DEFAULT_PROFILE, STORAGE_KEY, normalizeProfile, toCoverRequest, adaptCover, formatDate } from './reader.js';
import { getHealth, listCovers, getCover, createCover, sendFeedback, getLikes, setLike, getReaderFeedback } from './api.js';

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
  const [collections, setCollections] = useState([]);
  const [selectedCollection, setSelectedCollection] = useState(null);
  const [savingArticle, setSavingArticle] = useState(null);
  const [collectionForm, setCollectionForm] = useState(null);
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
  const [memory, setMemory] = useState(false);
  const [article, setArticle] = useState(null);
  const [feedback, setFeedback] = useState({});
  const saved = [...new Set(collections.flatMap(collection => collection.article_ids))];
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
      const [healthResult, historyResult, likesResult, libraryResult] = await Promise.allSettled([getHealth(), listCovers(userId), getLikes(userId), loadCollections()]);
      if (!active) return;
      if (libraryResult.status === 'fulfilled') setCollections(libraryResult.value);
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
    if (!cover || cover.userId !== userId) return;
    let active = true;
    getReaderFeedback(userId, cover.id).then(rows => {
      if (!active) return;
      const values = {};
      for (const row of rows) if (row.kind !== 'open' && row.kind !== 'impression') values[`${cover.id}:${row.article_id}`] = row;
      setFeedback(previous => ({ ...values, ...previous }));
    }).catch(e => { if (active) setNotice(`Les avis précédents n’ont pas pu être chargés : ${e.message}`); });
    return () => { active = false; };
  }, [cover?.id, userId]);
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
    setBusy('generating'); setError('');
    persist('kiosque.pending', Date.now());
    try {
      const raw = await createCover(toCoverRequest(profile, userId));
      displayCover(raw);
      // Preserve the result even if the next history refresh fails.
      setHistory(rows => [{ id: raw.id, title: raw.title, created_at: raw.created_at, status: raw.status, item_count: raw.items.length }, ...rows.filter(row => row.id !== raw.id)]);
      persist('kiosque.pending', null);
      setNotice(`${raw.items.length} contenus reçus. Classez vos découvertes dans vos bibliothèques.`);
    } catch (reason) { setError(reason.message); }
    finally { inFlight.current = false; setBusy(''); }
  }
  function articleOrigin(selected) {
    return selected.coverId || (cover?.userId === userId && cover.items.some(item => item.id === selected.id) ? cover.id : null);
  }
  function chooseSave(selected) {
    if (!selected) return;
    setLibraryError('');
    setSavingArticle({ ...selected, coverId: articleOrigin(selected) });
    refreshLibrary();
  }
  function saveFromJournal(id) { chooseSave(cover?.items.find(item => item.id === id)); }
  async function recordFeedback(value, selected = article) {
    const payload = typeof value === 'string' ? { kind: value } : value;
    const { kind } = payload;
    if (!selected) return;
    const coverId = articleOrigin(selected);
    if (!coverId) return;
    const key = `${coverId}:${selected.id}`;
    if (pendingFeedback.current.has(key)) return;
    pendingFeedback.current.add(key);
    try {
      const result = await sendFeedback({ ...payload, user_id: userId, cover_id: coverId, article_id: selected.id });
      if (kind !== 'open') {
        setFeedback(previous => ({ ...previous, [key]: { ...previous[key], ...payload, preference_id: result.preference?.id || previous[key]?.preference_id } }));
        setNotice(result.preference ? 'Votre retour et la préférence associée sont enregistrés pour la prochaine génération.' : 'Votre retour sur cet article a été enregistré.');
      }
    } catch (reason) { if (kind === 'open') setNotice(`Retour non enregistré : ${reason.message}`); else throw reason; }
    finally { pendingFeedback.current.delete(key); }
  }
  function recordOpen(selected) { return recordFeedback('open', selected); }
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
    persist(STORAGE_KEY, null); setPreferences(false); setProfile(null);
    // Keep the device identity, bookmarks and server editions; no account is deleted.
  }
  function openMemory() { setArticle(null); setPreferences(false); setMemory(true); }

  async function loadCollections() {
    const old = read('kiosque.saved', []);
    if (!read('kiosque.collectionsMigrated') && Array.isArray(old) && old.length) {
      await importBookmarks(userId, old.filter(id => typeof id === 'string'));
      persist('kiosque.collectionsMigrated', true);
    }
    return getCollections(userId);
  }
  async function refreshLibrary(includeSelected = true) {
    setLibraryLoading(true); setLibraryError('');
    try {
      setCollections(await loadCollections());
      if (includeSelected && selectedCollection) setSelectedCollection(await getCollection(userId, selectedCollection.id));
    } catch (reason) { setLibraryError(reason.message); }
    finally { setLibraryLoading(false); }
  }
  function acceptCollection(collection) {
    setCollections(rows => [collection, ...rows.filter(row => row.id !== collection.id)]);
    setSelectedCollection(previous => previous?.id === collection.id ? collection : previous);
  }
  async function mutateCollection(action, message) {
    if (libraryLock.current) return null;
    libraryLock.current = true; setLibraryPending('saving'); setLibraryError('');
    try {
      const result = await action();
      if (message) setNotice(message);
      return result;
    } catch (reason) { setLibraryError(reason.message); return null; }
    finally { libraryLock.current = false; setLibraryPending(''); }
  }
  async function openCollection(id) {
    setLibraryLoading(true); setLibraryError('');
    try { setSelectedCollection(await getCollection(userId, id)); }
    catch (reason) { setLibraryError(reason.message); }
    finally { setLibraryLoading(false); }
  }
  async function saveCollection(data) {
    const result = await mutateCollection(async () => {
      let collection = collectionForm?.id
        ? await editCollection(userId, collectionForm.id, data)
        : await createCollection(userId, data);
      acceptCollection(collection);
      if (savingArticle) {
        collection = await addToCollection(userId, collection.id, savingArticle.id, savingArticle.coverId);
        acceptCollection(collection);
      }
      return collection;
    }, collectionForm?.id ? 'Bibliothèque mise à jour.' : 'Bibliothèque créée.');
    if (result) setCollectionForm(null);
    return !!result;
  }
  async function toggleCollectionArticle(id, add) {
    if (!savingArticle) return;
    await mutateCollection(async () => {
      const result = add
        ? await addToCollection(userId, id, savingArticle.id, savingArticle.coverId)
        : await removeFromCollection(userId, id, savingArticle.id);
      acceptCollection(result);
      return result;
    });
  }
  async function removeCollectionArticle(id, articleId) {
    await mutateCollection(async () => {
      const result = await removeFromCollection(userId, id, articleId);
      acceptCollection(result); return result;
    }, 'Article retiré de cette bibliothèque.');
  }
  async function removeCollection(id) {
    await mutateCollection(async () => {
      await deleteCollection(userId, id);
      setCollections(rows => rows.filter(row => row.id !== id));
      setSelectedCollection(null);
      return true;
    }, 'Bibliothèque supprimée.');
  }
  function navigate(next) {
    setView(next); setArticle(null); setError(''); setLibraryError('');
    if (next === 'library') { setSelectedCollection(null); refreshLibrary(false); }
  }

  return <>
    <a className="skip-link" href="#main">Aller au contenu</a>
    <AccountNav account={account} view={view} onView={navigate} onLogout={onLogout} disabled={!!busy || !!libraryPending} />
    {view === 'library' ? <Library collections={collections} selected={selectedCollection} loading={libraryLoading} error={libraryError} pending={libraryPending} onRetry={refreshLibrary} onOpen={openCollection} onBack={() => { setSelectedCollection(null); setLibraryError(''); }} onCreate={() => { setLibraryError(''); setCollectionForm({}); }} onEdit={collection => { setLibraryError(''); setCollectionForm(collection); }} onDelete={removeCollection} onRemoveArticle={removeCollectionArticle} onSaveArticle={chooseSave} onRead={recordOpen} onJournal={() => navigate('journal')} /> : profile ? <Newspaper liked={liked} liking={liking} canLike={likesReady && cover?.userId === userId} onLike={toggleLike} profile={profile} cover={cover} saved={saved} onSave={saveFromJournal} onOpen={setArticle} onRead={recordOpen} onPreferences={() => setPreferences(true)} busy={!!busy}>
      <section className="reader-controls" aria-label="Gestion de votre édition">
        <div className="reader-actions">
        <button className="text-button" onClick={openMemory}><MessageCircle size={16} aria-hidden="true" /> Écrire à Kiosque</button>
        </div>
        {cover?.userId === userId && !!cover.preferenceImpact?.length && <details className="preference-impact"><summary>Vos demandes dans cette édition</summary><ul>{cover.preferenceImpact.map(row => <li key={row.id}>{preferenceSummary(row)} · {row.selected_count} article{row.selected_count !== 1 ? 's' : ''} retenu{row.selected_count !== 1 ? 's' : ''}{row.action === 'exclude' ? ' correspondant à la cible exclue' : ''}{row.explanation && <p>{row.explanation}</p>}{['more', 'diversify'].includes(row.action) && row.selected_count === 0 && <p>Aucune lecture correspondante n’a pu être retenue dans cette édition.</p>}</li>)}</ul>{cover.preferenceWarnings.map((warning, i) => <p key={i} className="edition-warning">{warning}</p>)}<p className="field-help">Bilan de cette édition au moment de sa création. Les corrections suivantes s’appliqueront aux prochaines générations.</p></details>}
        <details className="edition-management" open={cover ? undefined : true}>
        <summary>Mes éditions</summary>
        <div className="generation-row"><div><strong>{cover ? 'La prochaine édition vous attend.' : 'Composez votre première une.'}</strong><p>{profile.size} contenus souhaités · articles, jusqu’à 3 vidéos et 2 podcasts pertinents</p><p className="field-help">La génération consomme des crédits. À leur premier affichage, les nouvelles photos d’articles font aussi l’objet d’une vérification facturée ; son résultat est ensuite réutilisé.</p></div><button className="primary-button" disabled={!!busy || health?.llm_configured === false} onClick={generate}>{busy === 'generating' ? 'Préparation en cours…' : 'Générer ma une'}<ArrowRight size={18} /></button></div>
        <div className="history-row"><label htmlFor="edition-history">Mon historique de revues</label><select id="edition-history" value={cover?.id || ''} disabled={!!busy} onChange={event => openCover(event.target.value)}><option value="" disabled>Choisir une édition déjà générée</option>{history.map(row => <option key={row.id} value={row.id}>{formatDate(row.created_at)} · {row.item_count} contenus · {STATUS_LABELS[row.status] || row.status} · {row.title}</option>)}</select><button className="text-button" onClick={refreshHistory} disabled={!!busy}><RefreshCw size={15} /> Actualiser</button></div>
        {!history.length && !busy && <p className="field-help">Aucune édition générée pour ce compte pour le moment.</p>}
        {cover && <a className="audit-link" href={`/admin/covers?id=${encodeURIComponent(cover.id)}`} target="_blank" rel="noreferrer">Voir la construction de cette édition : sélection, résumés, outils et coût ↗</a>}
        </details>
        {health?.llm_configured === false && <p className="reader-error" role="alert">Le backend est accessible, mais sa clé API ou ses modèles ne sont pas configurés.</p>}
        {error && <p className="reader-error" role="alert">{error}</p>}
        {busy && <div className="generation-status" role="status"><span className="working-dot" /><span>{busy === 'generating' ? `Le rédacteur prépare votre édition… ${elapsed} s écoulées. Cela peut prendre plusieurs minutes. Vous pouvez continuer à lire l’édition affichée.` : 'Chargement des éditions…'}</span></div>}
      </section>
    </Newspaper> : <Onboarding initialName={account.name} onComplete={saveProfile} onExplore={() => { saveProfile({ ...DEFAULT_PROFILE, name: account.name }); if (history.length) openCover(history[0].id); }} />}
    {preferences && <Preferences profile={profile} onSave={saveProfile} onClose={() => setPreferences(false)} onReset={reset} onMemory={openMemory} />}
    {savingArticle && <SaveArticleDialog article={savingArticle} collections={collections} loading={libraryLoading} busy={!!libraryPending} error={libraryError} onToggle={toggleCollectionArticle} onCreate={saveCollection} onRetry={refreshLibrary} onClose={() => setSavingArticle(null)} />}
    {collectionForm && <Modal className="collection-dialog" labelId="collection-form-title" onClose={() => { if (!libraryPending) setCollectionForm(null); }}><p className="eyebrow">VOS ARTICLES, VOS ENVIES</p><h2 id="collection-form-title">{collectionForm.id ? 'Modifier la bibliothèque' : 'Nouvelle bibliothèque'}</h2><CollectionForm key={collectionForm.id || 'new'} collection={collectionForm.id ? collectionForm : null} busy={!!libraryPending} error={libraryError} onSubmit={saveCollection} onCancel={() => setCollectionForm(null)} /></Modal>}
    {profile && <Modal className="reader-chat-dialog" labelId="memory-title" open={memory} onClose={() => setMemory(false)}><ReaderChat userId={userId} profile={profile} generating={busy === 'generating'} open={memory} /></Modal>}
    {article && <ArticleDetail key={`${cover.id}:${article.id}`} liked={liked.includes(article.id)} liking={liking.includes(article.id)} canLike={likesReady && cover?.userId === userId} onLike={toggleLike} article={article} saved={saved.includes(article.id)} onSave={() => { setArticle(null); chooseSave(article); }} canFeedback={cover.userId === userId} feedback={feedback[`${cover.id}:${article.id}`]} notice={notice} onFeedback={recordFeedback} onRead={() => recordFeedback('open')} onClose={() => setArticle(null)} onMemory={openMemory} size={profile?.size || 18} />}
    <div className={`toast ${notice ? 'visible' : ''}`} role="status" aria-live="polite">{notice && <><Check size={17} /><span>{notice}</span></>}</div>
  </>;
}
