import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, Check, MessageCircle, RefreshCw } from 'lucide-react';
import { Onboarding, Preferences, Modal, SetupLayout } from './components.jsx';
import ReaderChat from './ReaderChat.jsx';
import RegenerateEdition from './RegenerateEdition.jsx';
import RegenerationProgress from './RegenerationProgress.jsx';
import { regenerationMessage } from './regeneration.js';
import Newspaper from './Newspaper.jsx';
import { getArchives, getSavedArticles, saveArticle, unsaveArticle, getCollections, getCollection, createCollection, editCollection, deleteCollection, addToCollection, removeFromCollection, importBookmarks } from './api.js';
import { readLocal, accountKey, currentAccount, leaveAccount, saveAccountProfile } from './accounts.js';
import SavedArticles, { Archives, AccountScreen, AccountNav, SaveArticleDialog, CollectionForm } from './Library.jsx';
import { DEFAULT_PROFILE, normalizeProfile, initialReaderProfile, toCoverRequest, adaptCover } from './reader.js';
import { listCovers, getCover, registerDailyEdition, getDailyEdition, getRegeneration, regenerateEdition, sendFeedback, getLikes, setLike } from './api.js';

import { dailyEditionMessage, dailyEditionRefreshMs, initialEditionId } from './daily-edition.js';

export default function App() {
  const [account, setAccount] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sessionError, setSessionError] = useState('');
  async function loadSession() {
    setLoading(true); setSessionError('');
    try {
      const session = await currentAccount();
      setAccount(session.account);
    } catch (reason) { setSessionError(reason.message); }
    finally { setLoading(false); }
  }
  useEffect(() => {
    loadSession();
    const expired = () => { setAccount(null); setSessionError(''); };
    window.addEventListener('kiosque-session-expired', expired);
    return () => window.removeEventListener('kiosque-session-expired', expired);
  }, []);
  async function logout() {
    setSessionError('');
    try {
      await leaveAccount();
      const url = new URL(window.location.href);
      url.searchParams.delete('cover');
      window.history.replaceState(null, '', url);
      setAccount(null);
    } catch (reason) { setSessionError(reason.message); }
  }
  if (loading || (!account && sessionError)) return <SetupLayout><section className="account-panel"><p role={sessionError ? 'alert' : 'status'}>{sessionError || 'Ouverture de votre espace…'}</p>{sessionError && <button className="secondary-button" onClick={loadSession}>Réessayer</button>}</section></SetupLayout>;
  return <>{sessionError && <p className="reader-error" role="alert">{sessionError}</p>}{account ? <ReaderApp key={account.id} account={account} onAccountChange={setAccount} onLogout={logout} /> : <AccountScreen onEnter={setAccount} />}</>;
}

function ReaderApp({ account, onAccountChange, onLogout }) {
  const userId = account.id;
  const read = (key, fallback = null) => readLocal(accountKey(userId, key), fallback);
  const [view, setView] = useState('journal');
  const [collections, setCollections] = useState([]);
  const [savedArticles, setSavedArticles] = useState({ article_ids: [], items: [] });
  const [archives, setArchives] = useState([]);
  const [archivesLoading, setArchivesLoading] = useState(false);
  const [archivesError, setArchivesError] = useState('');
  const [selectedCollection, setSelectedCollection] = useState(null);
  const [savingArticle, setSavingArticle] = useState(null);
  const [collectionForm, setCollectionForm] = useState(null);
  const [libraryLoading, setLibraryLoading] = useState(true);
  const [libraryError, setLibraryError] = useState('');
  const [libraryPending, setLibraryPending] = useState('');
  const libraryLock = useRef(false);
  const [linkedCoverId] = useState(() => new URLSearchParams(window.location.search).get('cover'));
  const [profile, setProfile] = useState(() => initialReaderProfile(account));
  const [cover, setCover] = useState(null);
  const [history, setHistory] = useState([]);
  const [preferences, setPreferences] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileError, setProfileError] = useState('');
  const profileLock = useRef(false);
  const [memory, setMemory] = useState(false);
  const saved = savedArticles.article_ids;
  const [liked, setLiked] = useState([]);
  const [likesReady, setLikesReady] = useState(false);
  const [liking, setLiking] = useState([]);
  const pendingLikes = useRef(new Set());
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('loading');
  const [daily, setDaily] = useState(null);
  const dailyRefreshMs = dailyEditionRefreshMs(daily, !!cover);
  const [dailyError, setDailyError] = useState('');
  const [regeneration, setRegeneration] = useState(null);
  const [regeneratingCover, setRegeneratingCover] = useState(null);
  const [regenerationError, setRegenerationError] = useState('');
  const pinnedEdition = useRef(Boolean(linkedCoverId));
  const displayedEdition = useRef(null);
  const currentEdition = useRef(null);
  const inFlight = useRef(false);
  const pendingFeedback = useRef(new Set());

  function acceptRegeneration(status) {
    setRegeneration({ ...status, receivedAt: Date.now() });
  }

  function persist(key, value) {
    try { localStorage.setItem(accountKey(userId, key), JSON.stringify(value)); }
    catch { setNotice('Le stockage du navigateur est indisponible. Vos réglages restent disponibles pour cette visite.'); }
  }
  function displayCover(raw, pin = false) {
    const isArchive = pin && raw.id !== currentEdition.current?.id;
    pinnedEdition.current = isArchive;
    displayedEdition.current = raw.id;
    const next = adaptCover(raw);
    setCover(next);
    if (!isArchive) {
      currentEdition.current = raw;
      persist('kiosque.lastCover', next.id);
    }
    const url = new URL(window.location.href);
    if (isArchive) url.searchParams.set('cover', next.id);
    else url.searchParams.delete('cover');
    window.history.replaceState(null, '', url);
    // Direct links also work for editions older than the visible history page.
    setHistory(rows => rows.some(row => row.id === raw.id) ? rows : [...rows, {
      id: raw.id, title: raw.title, created_at: raw.created_at, status: raw.status, item_count: raw.items.length,
    }]);
  }
  useEffect(() => {
    let active = true;
    async function initialize() {
      const [historyResult, likesResult, libraryResult] = await Promise.allSettled([listCovers(userId), getLikes(userId), loadCollections()]);
      if (!active) return;
      if (libraryResult.status === 'fulfilled') acceptLibrary(libraryResult.value);
      else setLibraryError(libraryResult.reason.message);
      setLibraryLoading(false);
      if (likesResult.status === 'fulfilled') { setLiked(likesResult.value.article_ids); setLikesReady(true); }
      else setNotice('Les likes sont indisponibles. Rechargez la page pour réessayer.');
      if (historyResult.status === 'fulfilled') setHistory(historyResult.value);
      else setError(historyResult.reason.message);
      // Keep the current edition available when a linked archive is being read.
      const currentId = initialEditionId(null, historyResult.status === 'fulfilled' ? historyResult.value : [], read('kiosque.lastCover')) || linkedCoverId;
      const ids = [...new Set([currentId, linkedCoverId].filter(Boolean))];
      const editions = await Promise.allSettled(ids.map(id => getCover(id, userId)));
      if (!active) return;
      editions.forEach((result, index) => {
        if (result.status === 'fulfilled') displayCover(result.value, ids[index] !== currentId);
        else setError(result.reason.message);
      });
      if (active) {
        setBusy('');
      }
    }
    initialize();
    return () => { active = false; };
  }, []);
  useEffect(() => {
    let active = true;
    getRegeneration(userId).then(value => { if (active) acceptRegeneration(value); })
      .catch(() => { if (active) setRegenerationError('Impossible de vérifier la régénération. Réessayez dans un instant.'); });
    return () => { active = false; };
  }, [userId]);
  useEffect(() => {
    if (!profile) return;
    let active = true, refreshing = false;
    async function refreshRegeneration() {
      if (document.hidden || refreshing) return;
      refreshing = true;
      try {
        const status = await getRegeneration(userId);
        if (!active) return;
        if (regeneration?.status === 'running' && status.status === 'completed' && !pinnedEdition.current && !inFlight.current) {
          // Another edition may have been prepared since this attempt completed.
          const rows = await listCovers(userId);
          if (active) setHistory(rows);
          if (rows[0]?.id && rows[0].id !== displayedEdition.current) {
            const raw = await getCover(rows[0].id, userId);
            if (active && !inFlight.current && !pinnedEdition.current) displayCover(raw);
          }
        }
        // A request can still be reserving its allowance when the first poll arrives.
        if (active && !(busy === 'regenerating' && status.available)) acceptRegeneration(status);
      } catch { /* Keep the last known progress; the next read will reconcile it. */ }
      finally { refreshing = false; }
    }
    const timer = window.setInterval(refreshRegeneration, busy === 'regenerating' || regeneration?.status === 'running' ? 2500 : 10000);
    document.addEventListener('visibilitychange', refreshRegeneration);
    return () => { active = false; clearInterval(timer); document.removeEventListener('visibilitychange', refreshRegeneration); };
  }, [userId, !!profile, busy, regeneration?.status]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(''), 7000);
    return () => clearTimeout(timer);
  }, [notice]);
  useEffect(() => {
    if (!profile) return;
    let active = true;
    let retry;
    async function syncProfile() {
      try {
        const status = await registerDailyEdition(userId, toCoverRequest(profile, userId));
        if (active) { setDaily(status); setDailyError(''); }
      } catch {
        if (active) {
          setDailyError('Votre une sera disponible dès que possible.');
          // The server reserves the first edition once, even if this request is retried.
          retry = window.setTimeout(syncProfile, 30_000);
        }
      }
    }
    syncProfile();
    return () => { active = false; clearTimeout(retry); };
  }, [profile]);
  useEffect(() => {
    if (!profile || !daily?.registered || busy === 'loading') return;
    let active = true;
    let refreshing = false;
    async function refreshDaily() {
      if (document.hidden || refreshing || inFlight.current) return;
      refreshing = true;
      try {
        const [rows, status, regenerationStatus] = await Promise.all([listCovers(userId), getDailyEdition(userId), getRegeneration(userId)]);
        if (!active) return;
        setHistory(rows); setDaily(status);
        acceptRegeneration(regenerationStatus);
        const latest = rows[0]?.id;
        if (latest && latest !== displayedEdition.current && !pinnedEdition.current) {
          const raw = await getCover(latest, userId);
          if (active && !pinnedEdition.current && !inFlight.current) displayCover(raw);
        }
      } catch (reason) {
        if (active) setNotice(`La mise à jour des éditions est momentanément indisponible : ${reason.message}`);
      } finally { refreshing = false; }
    }
    refreshDaily();
    const timer = window.setInterval(refreshDaily, dailyRefreshMs);
    document.addEventListener('visibilitychange', refreshDaily);
    return () => { active = false; clearInterval(timer); document.removeEventListener('visibilitychange', refreshDaily); };
  }, [profile, daily?.registered, dailyRefreshMs, busy === 'loading']);

  async function saveProfile(value) {
    if (profileLock.current) return false;
    const next = normalizeProfile(value);
    profileLock.current = true; setProfileSaving(true); setProfileError('');
    try {
      const updated = await saveAccountProfile(next);
      onAccountChange(updated);
      setProfile(normalizeProfile(updated.reader_profile));
      setPreferences(false);
      return true;
    } catch (reason) { setProfileError(reason.message); return false; }
    finally { profileLock.current = false; setProfileSaving(false); }
  }
  async function regenerate(reason) {
    if (inFlight.current || busy || !regeneration?.available || !regeneratingCover) return;
    inFlight.current = true;
    setBusy('regenerating'); setRegenerationError(''); setError('');
    acceptRegeneration({ ...regeneration, status: 'running', available: false, elapsed_seconds: 0 });
    try {
      const raw = await regenerateEdition(userId, regeneratingCover, reason);
      displayCover(raw);
      setHistory(rows => [{ id: raw.id, title: raw.title, created_at: raw.created_at, status: raw.status, item_count: raw.items.length }, ...rows.filter(row => row.id !== raw.id)]);
      setRegeneratingCover(null);
      setNotice(reason.trim() ? 'Votre nouvelle une est prête. Votre retour guidera aussi les sept prochains jours.' : 'Votre nouvelle une est prête.');
    } catch (failure) {
      setRegenerationError(failure.message);
      setError(failure.message);
    } finally {
      try {
        const status = await getRegeneration(userId);
        acceptRegeneration(status);
        // The persisted outcome is clearer than a generic connection/retry error.
        if (!status.available) { setRegenerationError(''); setError(''); }
      }
      catch { setRegeneration(null); }
      inFlight.current = false; setBusy('');
    }
  }
  async function openCover(id) {
    if (!id || inFlight.current || busy) return;
    inFlight.current = true;
    setBusy('loading'); setError('');
    try {
      displayCover(await getCover(id, userId), true);
      if (!profile) await saveProfile({ ...DEFAULT_PROFILE, name: account.name });
      setView('journal');
    }
    catch (reason) { setError(reason.message); }
    finally { inFlight.current = false; setBusy(''); }
  }
  function returnToCurrentEdition() {
    if (inFlight.current || busy || libraryLock.current) return;
    if (currentEdition.current) displayCover(currentEdition.current);
    else {
      pinnedEdition.current = false;
      displayedEdition.current = null;
      setCover(null);
      const url = new URL(window.location.href);
      url.searchParams.delete('cover');
      window.history.replaceState(null, '', url);
    }
    setError('');
    setView('journal');
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
  async function toggleSavedArticle(selected) {
    if (!selected || libraryLoading || libraryLock.current) return;
    const removing = saved.includes(selected.id);
    const result = await mutateCollection(async () => {
      const next = removing
        ? await unsaveArticle(userId, selected.id)
        : await saveArticle(userId, selected.id, articleOrigin(selected));
      setSavedArticles(next);
      if (removing) {
        const withoutArticle = collection => ({ ...collection, article_ids: collection.article_ids.filter(id => id !== selected.id), item_count: collection.article_ids.filter(id => id !== selected.id).length });
        setCollections(rows => rows.map(withoutArticle));
        setSelectedCollection(previous => previous ? withoutArticle(previous) : null);
      }
      return next;
    }, removing ? 'Article retiré des sauvegardes et des collections.' : 'Article sauvegardé. Retrouvez-le dans « Articles sauvegardés ».');
    if (!result) setNotice('La sauvegarde n’a pas pu être mise à jour. Réessayez.');
  }
  async function recordFeedback(value, selected) {
    const payload = typeof value === 'string' ? { kind: value } : value;
    const { kind } = payload;
    if (!selected) return;
    const coverId = articleOrigin(selected);
    if (!coverId) return;
    const key = `${coverId}:${selected.id}:${kind}`;
    if (pendingFeedback.current.has(key)) return;
    pendingFeedback.current.add(key);
    try {
      await sendFeedback({ ...payload, user_id: userId, cover_id: coverId, article_id: selected.id });
      if (kind !== 'open') setNotice('Votre avis a été enregistré.');
    } catch (reason) { if (kind === 'open') setNotice(`Retour non enregistré : ${reason.message}`); else throw reason; }
    finally { pendingFeedback.current.delete(key); }
  }
  function recordOpen(selected) { return recordFeedback('open', selected); }
  function respondToArticle(selected, details) {
    if (!articleOrigin(selected)) return Promise.reject(new Error('Cet article n’est pas rattaché à une de vos éditions.'));
    return recordFeedback({ kind: 'not_interested', ...details }, selected);
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
  function openMemory() { setPreferences(false); setMemory(true); }

  async function loadCollections() {
    const old = read('kiosque.saved', []);
    if (!read('kiosque.collectionsMigrated') && Array.isArray(old) && old.length) {
      await importBookmarks(userId, old.filter(id => typeof id === 'string'));
      persist('kiosque.collectionsMigrated', true);
    }
    const [nextCollections, nextSaved] = await Promise.all([getCollections(userId), getSavedArticles(userId)]);
    return { collections: nextCollections, savedArticles: nextSaved };
  }
  function acceptLibrary(data) {
    setCollections(data.collections);
    setSavedArticles(data.savedArticles);
  }
  async function refreshLibrary(includeSelected = true) {
    if (libraryLock.current) return;
    setLibraryLoading(true); setLibraryError('');
    try {
      acceptLibrary(await loadCollections());
      if (includeSelected && selectedCollection) setSelectedCollection(await getCollection(userId, selectedCollection.id));
    } catch (reason) { setLibraryError(reason.message); }
    finally { setLibraryLoading(false); }
  }
  function acceptCollection(collection) {
    setCollections(rows => [collection, ...rows.filter(row => row.id !== collection.id)]);
    setSelectedCollection(previous => previous?.id === collection.id ? collection : previous);
    if (collection.items?.length) setSavedArticles(previous => {
      const additions = collection.items.filter(item => !previous.article_ids.includes(item.article_id));
      return { article_ids: [...additions.map(item => item.article_id), ...previous.article_ids], items: [...additions, ...previous.items] };
    });
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
    }, collectionForm?.id ? 'Collection mise à jour.' : 'Collection créée.');
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
    }, 'Article retiré de cette collection. Il reste dans vos articles sauvegardés.');
  }
  async function removeCollection(id) {
    await mutateCollection(async () => {
      await deleteCollection(userId, id);
      setCollections(rows => rows.filter(row => row.id !== id));
      setSelectedCollection(null);
      return true;
    }, 'Collection supprimée. Vos articles sauvegardés sont conservés.');
  }
  async function refreshArchives() {
    setArchivesLoading(true); setArchivesError('');
    try { setArchives(await getArchives(userId)); }
    catch (reason) { setArchivesError(reason.message); }
    finally { setArchivesLoading(false); }
  }
  function navigate(next) {
    if (libraryLock.current) return;
    if (next === 'journal' && pinnedEdition.current) returnToCurrentEdition();
    setView(next); setError(''); setLibraryError('');
    if (next === 'saved') { setSelectedCollection(null); refreshLibrary(false); }
    if (next === 'archives') refreshArchives();
  }

  return <>
    <a className="skip-link" href="#main">Aller au contenu</a>
    {(profile || view !== 'journal') && <AccountNav account={account} view={view} onView={navigate} onLogout={onLogout} disabled={!!busy || !!libraryPending} />}
    {view === 'archives' ? <Archives editions={archives} loading={archivesLoading} error={archivesError || error} busy={!!busy} onRetry={refreshArchives} onOpen={openCover} onView={navigate} /> : view === 'saved' ? <SavedArticles savedArticles={savedArticles} collections={collections} selected={selectedCollection} loading={libraryLoading} error={libraryError} pending={libraryPending} onRetry={refreshLibrary} onOpen={openCollection} onBack={() => { setSelectedCollection(null); setLibraryError(''); }} onCreate={() => { setLibraryError(''); setCollectionForm({}); }} onEdit={collection => { setLibraryError(''); setCollectionForm(collection); }} onDelete={removeCollection} onRemoveArticle={removeCollectionArticle} onSaveArticle={toggleSavedArticle} onOrganize={chooseSave} onFeedback={respondToArticle} onRead={recordOpen} onView={navigate} /> : profile ? <Newspaper liked={liked} liking={liking} canLike={likesReady && cover?.userId === userId} onLike={toggleLike} cover={cover} saved={saved} onSave={toggleSavedArticle} onOrganize={chooseSave} saving={libraryLoading || !!libraryPending} onFeedback={cover?.userId === userId ? respondToArticle : undefined} onRead={recordOpen} onPreferences={() => setPreferences(true)} busy={!!busy}>
      <section className="reader-controls" aria-label="Gestion de votre édition">
        <div className="reader-actions">
        {pinnedEdition.current && <button className="text-button" onClick={returnToCurrentEdition} disabled={!!busy || !!libraryPending} title="Revenir à mon édition actuelle" aria-label="Retour à mon édition actuelle"><ArrowLeft size={16} aria-hidden="true" /> Retour</button>}
        <button className="text-button" onClick={openMemory}><MessageCircle size={16} aria-hidden="true" /> Écrire à Kiosque</button>
        {cover?.userId === userId && !pinnedEdition.current && <button className="text-button" disabled={!!busy || !regeneration?.available || !daily?.registered} onClick={() => { setRegenerationError(''); setRegeneratingCover(cover.id); }}><RefreshCw size={16} aria-hidden="true" /> Refaire ma une</button>}
        </div>
        {(busy === 'regenerating' || regeneration?.status === 'running') && <RegenerationProgress status={regeneration} />}
        {cover && !pinnedEdition.current && !regeneration?.available && busy !== 'regenerating' && regeneration?.status !== 'running' && <p className="regeneration-status" role="status">{!regeneration && regenerationError ? regenerationError : regenerationMessage(regeneration)}</p>}
        {busy !== 'loading' && (dailyError || dailyEditionMessage(daily, !!cover)) && <p className="daily-edition-status" role="status">{dailyError || dailyEditionMessage(daily, !!cover)}</p>}
        {error && <p className="reader-error" role="alert">{error}</p>}
        {busy && busy !== 'regenerating' && <div className="generation-status" role="status"><span className="working-dot" /><span>Chargement des éditions…</span></div>}
      </section>
    </Newspaper> : <Onboarding initialName={account.name} saving={profileSaving} error={profileError} onComplete={saveProfile} onExplore={async () => { if (await saveProfile({ ...DEFAULT_PROFILE, name: account.name }) && history.length) openCover(history[0].id); }} />}
    {preferences && <Preferences profile={profile} saving={profileSaving} error={profileError} onSave={saveProfile} onClose={() => setPreferences(false)} />}
    {regeneratingCover && <RegenerateEdition busy={busy === 'regenerating'} status={regeneration} error={regenerationError} onSubmit={regenerate} onClose={() => setRegeneratingCover(null)} />}
    {savingArticle && <SaveArticleDialog article={savingArticle} collections={collections} loading={libraryLoading} busy={!!libraryPending} error={libraryError} onToggle={toggleCollectionArticle} onCreate={saveCollection} onRetry={refreshLibrary} onClose={() => setSavingArticle(null)} />}
    {collectionForm && <Modal className="collection-dialog" labelId="collection-form-title" onClose={() => { if (!libraryPending) setCollectionForm(null); }}><p className="eyebrow">VOS ARTICLES, VOS ENVIES</p><h2 id="collection-form-title">{collectionForm.id ? 'Modifier la collection' : 'Nouvelle collection'}</h2><CollectionForm key={collectionForm.id || 'new'} collection={collectionForm.id ? collectionForm : null} busy={!!libraryPending} error={libraryError} onSubmit={saveCollection} onCancel={() => setCollectionForm(null)} /></Modal>}
    {profile && <Modal className="reader-chat-dialog" labelId="memory-title" open={memory} onClose={() => setMemory(false)}><ReaderChat userId={userId} profile={profile} generating={daily?.status === 'running'} open={memory} /></Modal>}
    <div className={`toast ${notice ? 'visible' : ''}`} role="status" aria-live="polite">{notice && <><Check size={17} /><span>{notice}</span></>}</div>
  </>;
}
