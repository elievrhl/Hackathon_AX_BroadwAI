import { useEffect, useState } from 'react';
import { ArrowRight, BookOpen, Archive, Folder, LogOut, Check, Bookmark, X, Plus, Pencil, Trash2, ArrowUpRight } from 'lucide-react';
import { Wordmark, Modal, SetupLayout, SetupProgress, MediaBadge } from './components.jsx';
import { Play } from 'lucide-react';
import { ThemeButton } from './ThemePicker.jsx';
import { enterAccount } from './accounts.js';
import { formatDate, articleImageUrl, adaptCover, contentAction } from './reader.js';
import ArticleSaveActions from './ArticleSaveActions.jsx';
import './library.css';

export function AccountScreen({ onEnter }) {
  const [create, setCreate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true); setError('');
    try {
      const account = await enterAccount({ email: data.get('email'), name: data.get('name') || '', password: data.get('password'), create });
      form.reset();
      onEnter(account);
    } catch (reason) { setError(reason.message); }
    finally { setBusy(false); }
  }
  return <SetupLayout>
    <section className="account-panel" aria-labelledby="account-title">
      <p className="eyebrow">VOTRE ESPACE DE LECTURE</p>
      <h2 id="account-title">{create ? 'Bienvenue chez vous.' : 'Heureux de vous revoir.'}</h2>
      <div className="account-tabs"><button disabled={busy} aria-pressed={!create} onClick={() => { setCreate(false); setError(''); }}>Se connecter</button><button disabled={busy} aria-pressed={create} onClick={() => { setCreate(true); setError(''); }}>Créer un compte</button></div>
      <form key={String(create)} onSubmit={submit}>
        {create && <label className="field">Prénom<input name="name" autoComplete="given-name" disabled={busy} required maxLength={40} placeholder="Camille" /></label>}
        <label className="field">Adresse e-mail<input name="email" type="email" autoComplete="email" disabled={busy} required maxLength={254} placeholder="camille@exemple.fr" /></label>
        <label className="field">Mot de passe<input name="password" type="password" autoComplete={create ? 'new-password' : 'current-password'} disabled={busy} required minLength={create ? 12 : 1} maxLength={128} aria-describedby={create ? 'password-help' : undefined} /></label>
        {create && <p className="field-help" id="password-help">Au moins 12 caractères. Vous pouvez utiliser une phrase de passe.</p>}
        <p className="account-demo">Vos préférences et vos lectures vous suivent sur tous vos appareils.</p>
        {error && <p className="reader-error" role="alert">{error}</p>}
        <button className="primary-button full-width" disabled={busy} type="submit">{busy ? 'Connexion en cours…' : create ? 'Créer mon compte' : 'Se connecter'}<ArrowRight size={18} /></button>
      </form>
    </section>
  </SetupLayout>;
}

export function AccountNav({ account, view, onView, onLogout, disabled }) {
  return <nav className="account-nav" aria-label="Mon espace">
    <span className="account-greeting">Le journal de <strong>{account.name}</strong></span>
    <div className="account-nav-links">
      <button className="account-journal" aria-current={view === 'journal' ? 'page' : undefined} disabled={disabled} onClick={() => onView('journal')}><BookOpen size={17} aria-hidden="true" />Mon journal</button>
      <button aria-label="Articles sauvegardés" title="Articles sauvegardés" aria-current={view === 'saved' ? 'page' : undefined} disabled={disabled} onClick={() => onView('saved')}><Bookmark size={18} aria-hidden="true" /></button>
      <button aria-label="Archives" title="Archives — vos éditions complètes" aria-current={view === 'archives' ? 'page' : undefined} disabled={disabled} onClick={() => onView('archives')}><Archive size={18} aria-hidden="true" /></button>
      <ThemeButton compact />
      <button className="account-logout" aria-label="Déconnexion" title="Déconnexion" disabled={disabled} onClick={onLogout}><LogOut size={16} aria-hidden="true" /></button>
    </div>
  </nav>;
}

export function EditionArtwork({ edition, spine = false }) {
  const [failed, setFailed] = useState([]);
  const art = edition.artwork || {};
  const photos = (art.photos || []).filter(id => !failed.includes(id));
  const serial = edition.id.slice(0, 4).toUpperCase();
  return <div className={`edition-art palette-${art.palette || 0} ${spine ? 'spine-only' : ''}`}>
    <div className="edition-spine">{spine ? <><span className="spine-brand">K.</span><div className="spine-label"><span className="spine-kicker">KIOSQUE · LES ARCHIVES</span><strong>{edition.title}</strong></div><small className="spine-date"><span>№ {serial}</span>{edition.item_count} contenu{edition.item_count !== 1 ? 's' : ''}</small></> : <><span>K.</span><strong>{edition.title}</strong></>}</div>
    {!spine && <div className="edition-face"><div className="edition-art-meta"><span>ÉDITION ARCHIVÉE</span><span>№ {serial}</span></div><div className="edition-masthead">Kiosque<span>.</span></div><div className={`edition-collage photos-${photos.length}`} aria-hidden="true">{photos.map(id => <img key={id} src={articleImageUrl({ article_id: id })} alt="" loading="lazy" onError={() => setFailed(previous => [...previous, id])} />)}{!photos.length && <span className="edition-monogram">K.</span>}</div><div className="edition-cover-title">{edition.title}</div><p className="edition-cover-sections">{(art.sections || []).join(' / ')}</p><div className="edition-art-footer"><span>{formatDate(edition.created_at)}</span><span>{edition.item_count} contenu{edition.item_count !== 1 ? 's' : ''}</span></div></div>}
  </div>;
}

export function CollectionForm({ collection, onSubmit, busy, error, onCancel, compact = false }) {
  const [name, setName] = useState(collection?.name || '');
  const [description, setDescription] = useState(collection?.description || '');
  return <form className="collection-form" onSubmit={event => { event.preventDefault(); if (name.trim()) onSubmit({ name: name.trim(), description: description.trim() }); }}>
    <label className="field">Nom de la collection<input autoFocus required maxLength={160} value={name} onChange={e => setName(e.target.value)} placeholder="Ex. Intelligence artificielle" /></label>
    {!compact && <label className="field">Description <span className="optional">Facultatif</span><textarea rows={2} maxLength={600} value={description} onChange={e => setDescription(e.target.value)} placeholder="Les idées que j’ai envie de retrouver…" /></label>}
    {error && <p className="reader-error" role="alert">{error}</p>}
    <div className="collection-form-actions"><button className="primary-button" disabled={busy || !name.trim()} type="submit">{busy ? 'Enregistrement…' : collection ? 'Enregistrer' : 'Créer la collection'}<Check size={16} /></button>{onCancel && <button type="button" className="text-button" disabled={busy} onClick={onCancel}>Annuler</button>}</div>
  </form>;
}

export function SaveArticleDialog({ article, collections, loading, error, busy, onToggle, onCreate, onRetry, onClose }) {
  const [creating, setCreating] = useState(false);
  return <Modal className="collection-dialog" labelId="save-article-title" onClose={() => { if (!busy) onClose(); }}>
    <p className="eyebrow">CLASSER CET ARTICLE</p><h2 id="save-article-title">Ajouter à une collection</h2><p className="collection-article-name">{article.title}</p>
    <p className="field-help">Les articles classés se retrouvent aussi dans « Articles sauvegardés ». Vous pouvez choisir plusieurs collections.</p>
    {loading ? <p role="status">Chargement de vos collections…</p> : <div className="collection-choices">{collections.map(collection => <label key={collection.id}><input type="checkbox" aria-label={collection.name} checked={collection.article_ids.includes(article.id)} disabled={busy || !!error} onChange={e => onToggle(collection.id, e.target.checked)} /><span><strong>{collection.name}</strong><small>{collection.item_count} contenu{collection.item_count !== 1 ? 's' : ''}</small></span><Bookmark size={17} /></label>)}</div>}
    {error && <p className="reader-error" role="alert">{error} <button className="text-button" disabled={busy} onClick={onRetry}>Réessayer</button></p>}
    {!loading && !error && !collections.length && <p className="field-help">Créez votre première collection pour y garder cet article.</p>}
    {creating || (!loading && !error && !collections.length) ? <CollectionForm compact busy={busy} onSubmit={async data => { if (await onCreate(data)) setCreating(false); }} onCancel={collections.length ? () => setCreating(false) : undefined} /> : <button className="text-button create-collection-link" disabled={busy || loading || !!error} onClick={() => setCreating(true)}><Plus size={17} />Nouvelle collection</button>}
    <div className="collection-dialog-footer"><span>{busy ? 'Enregistrement…' : 'Vos choix sont enregistrés automatiquement.'}</span><button className="secondary-button" disabled={busy} onClick={onClose}>Terminé</button></div>
  </Modal>;
}

export function Archives({ editions, loading, error, busy, onRetry, onOpen, onView }) {
  const [spines, setSpines] = useState(false);
  return <main id="main" className="library-page archives-page">
    <header className="library-heading"><Wordmark small /><p className="eyebrow">VOTRE JOURNAL AU FIL DU TEMPS</p><h1>Archives<span>.</span></h1><p>Toutes vos éditions sont conservées ici, prêtes à être feuilletées à nouveau.</p></header>
    <div className="library-toolbar"><span>{editions.length} édition{editions.length !== 1 ? 's' : ''}</span><div className="library-switch" aria-label="Présentation des archives"><button aria-pressed={!spines} onClick={() => setSpines(false)}>Couvertures</button><button aria-pressed={spines} onClick={() => setSpines(true)}>Tranches</button></div></div>
    {loading && <p role="status">Chargement des éditions…</p>}
    {error && <div className="reader-error" role="alert">{error} <button className="text-button" onClick={onRetry}>Réessayer</button></div>}
    {!loading && !error && !editions.length && <div className="library-empty"><Archive size={38} strokeWidth={1} /><h2>Votre histoire de lecture commence ici.</h2><p>Chaque édition créée apparaîtra automatiquement dans vos archives.</p><button className="primary-button" onClick={() => onView('journal')}>Ouvrir mon journal<ArrowRight size={17} /></button></div>}
    <div className={`library-shelf ${spines ? 'show-spines' : ''}`}>{editions.map(edition => <article className="library-volume" key={edition.id}>
      <button className="edition-open" disabled={busy || loading} onClick={() => onOpen(edition.id)} aria-label={`Lire l’édition ${edition.title}`}><EditionArtwork edition={edition} spine={spines} /></button>
      <div className="library-volume-caption"><span>{formatDate(edition.created_at)} · {edition.item_count} contenus</span><h2>{edition.title}</h2><div><button className="text-button" disabled={busy || loading} onClick={() => onOpen(edition.id)}>Feuilleter l’édition<ArrowRight size={14} /></button></div></div>
    </article>)}</div>
  </main>;
}

function SavedArticle({ item, collections, selected, busy, onSave, onOrganize, onRead, onRemove }) {
  const [failed, setFailed] = useState(false);
  return <article className="collection-reading">
    {item.imageUrl && !failed && <a className={`collection-reading-image${item.format === 'video' ? ' video-visual' : item.format === 'podcast' ? ' podcast-visual' : ''}`} href={item.url || undefined} target="_blank" rel="noopener noreferrer" tabIndex={-1} aria-hidden="true" onClick={() => onRead(item)}><img src={item.imageUrl} alt="" loading="lazy" onError={() => setFailed(true)} />{item.format === 'video' && <span className="video-play"><Play size={20} fill="currentColor" /></span>}</a>}
    <div className="collection-reading-body"><p className="eyebrow">{item.channelTitle || item.source}{item.format === 'video' ? ' · YouTube' : ''}</p><MediaBadge format={item.format} duration={item.duration} /><h2>{item.url ? <a href={item.url} target="_blank" rel="noopener noreferrer" onClick={() => onRead(item)}>{item.title}</a> : item.title}</h2><p className="collection-reading-meta">{[item.publishedAt && formatDate(item.publishedAt), item.readingTimeMinutes && `${item.readingTimeMinutes} min de lecture`].filter(Boolean).join(' · ')}</p>
      {!!collections.length && <p className="article-collection-names"><Folder size={13} aria-hidden="true" />{collections.map(c => c.name).join(' · ')}</p>}
      <div className="collection-reading-actions"><ArticleSaveActions article={item} saved busy={busy} onSave={onSave} onOrganize={onOrganize} labelled />
        {selected && <button className="text-button" disabled={busy} onClick={() => onRemove(selected.id, item.id)}><X size={15} aria-hidden="true" />Retirer de cette collection</button>}
        {item.url && <a className="text-button" href={item.url} target="_blank" rel="noopener noreferrer" onClick={() => onRead(item)}>{contentAction(item.format)}<ArrowUpRight size={16} /></a>}
      </div>
    </div>
  </article>;
}

export default function SavedArticles({ savedArticles, collections, selected, loading, error, pending, onRetry, onOpen, onBack, onEdit, onDelete, onRemoveArticle, onSaveArticle, onOrganize, onRead, onCreate, onView }) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  useEffect(() => { setConfirmDelete(false); }, [selected?.id]);
  const all = adaptCover({ id: 'saved-articles', items: savedArticles.items }).items;
  const articles = selected ? all.filter(item => selected.article_ids.includes(item.id)) : all;
  return <main id="main" className="library-page saved-articles-page">
    <header className="saved-heading"><p className="eyebrow">À RETROUVER QUAND VOUS VOULEZ</p><h1>Articles sauvegardés<span>.</span></h1><p>Un clic sur le marque-page pour garder une lecture. Le menu « … » permet de la classer dans une collection.</p></header>
    <div className="saved-layout"><aside className="collection-sidebar" aria-label="Filtrer les articles par collection">
      <button className={!selected ? 'active' : ''} aria-pressed={!selected} onClick={onBack}>Tous les articles<span>{all.length}</span></button>
      <div className="collection-sidebar-heading"><h2>Collections</h2><button className="text-button" aria-label="Nouvelle collection" title="Nouvelle collection" disabled={pending || loading} onClick={onCreate}><Plus size={17} /></button></div>
      {!collections.length && <p>Regroupez vos lectures par sujet ou par envie.</p>}
      {collections.map(collection => <button key={collection.id} className={selected?.id === collection.id ? 'active' : ''} aria-pressed={selected?.id === collection.id} disabled={loading || pending} onClick={() => onOpen(collection.id)}><Folder size={15} aria-hidden="true" /><span className="collection-filter-name">{collection.name}</span><span>{collection.item_count}</span></button>)}
    </aside><section className="saved-results" aria-label={selected?.name || 'Tous les articles sauvegardés'}>
      <div className="saved-results-heading"><div><h2>{selected?.name || 'Tous les articles'}</h2><p>{articles.length} contenu{articles.length !== 1 ? 's' : ''}{selected?.description ? ` · ${selected.description}` : ''}</p></div>{selected && <div className="collection-heading-actions"><button className="text-button" disabled={pending} onClick={() => onEdit(selected)}><Pencil size={15} />Modifier</button><button className="text-button" disabled={pending} onClick={() => setConfirmDelete(true)}><Trash2 size={15} />Supprimer</button></div>}</div>
      {confirmDelete && <div className="collection-delete-confirm" role="alert"><p>Supprimer la collection « {selected.name} » ? Les articles resteront dans vos articles sauvegardés.</p><button className="secondary-button" disabled={pending} onClick={() => onDelete(selected.id)}>Supprimer la collection</button><button className="text-button" disabled={pending} onClick={() => setConfirmDelete(false)}>Annuler</button></div>}
      {loading && <p role="status">Chargement de vos lectures…</p>}
      {error && <div className="reader-error" role="alert">{error} <button className="text-button" onClick={onRetry}>Réessayer</button></div>}
      {!loading && !error && !articles.length && <div className="library-empty"><Bookmark size={34} strokeWidth={1} /><h2>{selected ? 'Une collection à remplir.' : 'Gardez vos prochaines découvertes.'}</h2><p>{selected ? 'Sur un article, ouvrez « … », puis « Ajouter à une collection ».' : 'Cliquez sur le marque-page d’un article : il vous attendra ici.'}</p><button className="secondary-button" onClick={() => onView('journal')}>Explorer le journal<ArrowRight size={17} /></button></div>}
      <div className="collection-readings">{articles.map(item => <SavedArticle key={item.id} item={item} selected={selected} collections={collections.filter(c => c.article_ids.includes(item.id))} busy={!!pending || loading} onRead={onRead} onSave={onSaveArticle} onOrganize={onOrganize} onRemove={onRemoveArticle} />)}</div>
    </section></div>
  </main>;
}
