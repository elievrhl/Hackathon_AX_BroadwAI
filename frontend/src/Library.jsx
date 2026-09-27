import { useEffect, useState } from 'react';
import { ArrowRight, BookOpen, Library as LibraryIcon, LogOut, Check, Bookmark, X, Plus, Pencil, Trash2, ArrowLeft, ArrowUpRight } from 'lucide-react';
import { Wordmark, Modal } from './components.jsx';
import { enterAccount } from './accounts.js';
import { formatDate, articleImageUrl, adaptCover } from './reader.js';
import './library.css';

export function AccountScreen({ onEnter }) {
  const [create, setCreate] = useState(true);
  const [error, setError] = useState('');
  function submit(event) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    try {
      const account = enterAccount({ email: data.get('email'), name: data.get('name') || '', create });
      event.currentTarget.reset();
      onEnter(account);
    } catch (reason) { setError(reason.message); }
  }
  return <div className="account-page">
    <header className="account-header"><Wordmark small /><span>LE MONDE, À VOTRE MESURE.</span></header>
    <main id="main" className="account-main">
      <section className="account-editorial"><p className="eyebrow">LE PLAISIR DE GARDER L’ESSENTIEL</p><h1>Des lectures.<br />Des idées.<br /><em>Une collection.</em></h1><p>Votre journal, vos découvertes, votre bibliothèque.<br />Classez les articles qui méritent une place chez vous.</p><div className="account-book-art" aria-hidden="true"><div>Kiosque<span>LES IDÉES<br />RESTENT.</span><small>VOTRE BIBLIOTHÈQUE PERSONNELLE</small></div><i>Le monde à portée de page.</i></div></section>
      <section className="account-panel" aria-labelledby="account-title"><p className="eyebrow">VOTRE ESPACE DE LECTURE</p><h2 id="account-title">{create ? 'Bienvenue chez vous.' : 'Heureux de vous revoir.'}</h2><div className="account-tabs"><button aria-pressed={create} onClick={() => { setCreate(true); setError(''); }}>Créer un compte</button><button aria-pressed={!create} onClick={() => { setCreate(false); setError(''); }}>Se connecter</button></div>
        <form key={String(create)} onSubmit={submit}>
          {create && <label className="field">Prénom<input name="name" autoComplete="given-name" required maxLength={40} placeholder="Camille" /></label>}
          <label className="field">Adresse e-mail<input name="email" type="email" autoComplete="off" required maxLength={254} placeholder="camille@exemple.fr" /></label>
          <label className="field">Mot de passe de démonstration<input name="password" type="password" autoComplete="off" required maxLength={128} placeholder="Un mot de passe fictif" /></label>
          <p className="account-demo">Compte de démonstration dans ce navigateur. Utilisez un mot de passe fictif : il n’est ni enregistré ni vérifié. Aucun e-mail n’est envoyé.</p>
          {error && <p className="reader-error" role="alert">{error}</p>}
          <button className="primary-button full-width" type="submit">{create ? 'Créer mon espace' : 'Entrer dans mon espace'}<ArrowRight size={18} /></button>
        </form>
      </section>
    </main><footer className="account-footer">KIOSQUE · DES REGARDS DIFFÉRENTS, UN JOURNAL À SOI.</footer>
  </div>;
}

export function AccountNav({ account, view, onView, onLogout, disabled }) {
  return <nav className="account-nav" aria-label="Mon espace"><span className="account-greeting">L’espace de <strong>{account.name}</strong></span><div><button className={view === 'journal' ? 'active' : ''} aria-current={view === 'journal' ? 'page' : undefined} disabled={disabled} onClick={() => onView('journal')}><BookOpen size={16} />Le journal</button><button className={view === 'library' ? 'active' : ''} aria-current={view === 'library' ? 'page' : undefined} disabled={disabled} onClick={() => onView('library')}><LibraryIcon size={16} />Ma bibliothèque</button><button disabled={disabled} onClick={onLogout} title="Se déconnecter"><LogOut size={16} /><span className="logout-label">Déconnexion</span></button></div></nav>;
}

export function EditionArtwork({ edition, spine = false }) {
  const [failed, setFailed] = useState([]);
  const art = edition.artwork || {};
  const photos = (art.photos || []).filter(id => !failed.includes(id));
  const serial = edition.id.slice(0, 4).toUpperCase();
  return <div className={`edition-art palette-${art.palette || 0} ${spine ? 'spine-only' : ''}`}>
    <div className="edition-spine">{spine ? <><span className="spine-brand">K.</span><div className="spine-label"><span className="spine-kicker">KIOSQUE · LA COLLECTION</span><strong>{edition.title}</strong></div><small className="spine-date"><span>№ {serial}</span>{edition.item_count} article{edition.item_count !== 1 ? 's' : ''}</small></> : <><span>K.</span><strong>{edition.title}</strong></>}</div>
    {!spine && <div className="edition-face"><div className="edition-art-meta"><span>BIBLIOTHÈQUE PERSONNELLE</span><span>№ {serial}</span></div><div className="edition-masthead">Kiosque<span>.</span></div><div className={`edition-collage photos-${photos.length}`} aria-hidden="true">{photos.map(id => <img key={id} src={articleImageUrl({ article_id: id })} alt="" loading="lazy" onError={() => setFailed(previous => [...previous, id])} />)}{!photos.length && <span className="edition-monogram">K.</span>}</div><div className="edition-cover-title">{edition.title}</div><p className="edition-cover-sections">{(art.sections || []).join(' / ')}</p><div className="edition-art-footer"><span>{formatDate(edition.created_at)}</span><span>{edition.item_count} article{edition.item_count !== 1 ? 's' : ''}</span></div></div>}
  </div>;
}

export function CollectionForm({ collection, onSubmit, busy, error, onCancel, compact = false }) {
  const [name, setName] = useState(collection?.name || '');
  const [description, setDescription] = useState(collection?.description || '');
  return <form className="collection-form" onSubmit={event => { event.preventDefault(); if (name.trim()) onSubmit({ name: name.trim(), description: description.trim() }); }}>
    <label className="field">Nom de la bibliothèque<input autoFocus required maxLength={160} value={name} onChange={e => setName(e.target.value)} placeholder="Ex. Intelligence artificielle" /></label>
    {!compact && <label className="field">Description <span className="optional">Facultatif</span><textarea rows={2} maxLength={600} value={description} onChange={e => setDescription(e.target.value)} placeholder="Les idées que j’ai envie de retrouver…" /></label>}
    {error && <p className="reader-error" role="alert">{error}</p>}
    <div className="collection-form-actions"><button className="primary-button" disabled={busy || !name.trim()} type="submit">{busy ? 'Enregistrement…' : collection ? 'Enregistrer' : 'Créer la bibliothèque'}<Check size={16} /></button>{onCancel && <button type="button" className="text-button" disabled={busy} onClick={onCancel}>Annuler</button>}</div>
  </form>;
}

export function SaveArticleDialog({ article, collections, loading, error, busy, onToggle, onCreate, onRetry, onClose }) {
  const [creating, setCreating] = useState(false);
  return <Modal className="collection-dialog" labelId="save-article-title" onClose={() => { if (!busy) onClose(); }}>
    <p className="eyebrow">UNE PLACE POUR CETTE LECTURE</p><h2 id="save-article-title">Enregistrer dans…</h2><p className="collection-article-name">{article.title}</p>
    <p className="field-help">Un article peut appartenir à plusieurs bibliothèques.</p>
    {loading ? <p role="status">Chargement de vos bibliothèques…</p> : <div className="collection-choices">{collections.map(collection => <label key={collection.id}><input type="checkbox" aria-label={collection.name} checked={collection.article_ids.includes(article.id)} disabled={busy || !!error} onChange={e => onToggle(collection.id, e.target.checked)} /><span><strong>{collection.name}</strong><small>{collection.item_count} article{collection.item_count !== 1 ? 's' : ''}</small></span><Bookmark size={17} /></label>)}</div>}
    {error && <p className="reader-error" role="alert">{error} <button className="text-button" disabled={busy} onClick={onRetry}>Réessayer</button></p>}
    {!loading && !error && !collections.length && <p className="field-help">Créez votre première bibliothèque pour y garder cet article.</p>}
    {creating || (!loading && !error && !collections.length) ? <CollectionForm compact busy={busy} onSubmit={async data => { if (await onCreate(data)) setCreating(false); }} onCancel={collections.length ? () => setCreating(false) : undefined} /> : <button className="text-button create-collection-link" disabled={busy || loading || !!error} onClick={() => setCreating(true)}><Plus size={17} />Nouvelle bibliothèque</button>}
    <div className="collection-dialog-footer"><span>{busy ? 'Enregistrement…' : 'Vos choix sont enregistrés automatiquement.'}</span><button className="secondary-button" disabled={busy} onClick={onClose}>Terminé</button></div>
  </Modal>;
}

function CollectionArticle({ item, onRemove, onSave, onRead, busy }) {
  const [failed, setFailed] = useState(false);
  const image = articleImageUrl({ article_id: item.id });
  return <article className="collection-reading">
    {image && !failed && <a className="collection-reading-image" href={item.url || undefined} target="_blank" rel="noopener noreferrer" tabIndex={-1} aria-hidden="true" onClick={() => onRead(item)}><img src={image} alt="" loading="lazy" onError={() => setFailed(true)} /></a>}
    <div className="collection-reading-body"><p className="eyebrow">{item.source}</p><h2><a href={item.url || undefined} target="_blank" rel="noopener noreferrer" onClick={() => onRead(item)}>{item.title}</a></h2><p className="collection-reading-meta">{item.publishedAt && formatDate(item.publishedAt)}{item.readingTimeMinutes ? ` · ${item.readingTimeMinutes} min de lecture` : ''}</p><div className="collection-reading-actions"><button className="text-button" disabled={busy} onClick={() => onSave(item)}><Bookmark size={15} />Organiser</button><button className="text-button" disabled={busy} onClick={() => onRemove(item.id)}><X size={15} />Retirer de cette bibliothèque</button>{item.url && <a className="text-button" href={item.url} target="_blank" rel="noopener noreferrer" onClick={() => onRead(item)}>Lire l’article<ArrowUpRight size={16} /></a>}</div></div>
  </article>;
}

export default function Library({ collections, selected, loading, error, pending, onRetry, onOpen, onBack, onEdit, onDelete, onRemoveArticle, onSaveArticle, onRead, onCreate, onJournal }) {
  const [spines, setSpines] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  useEffect(() => { setConfirmDelete(false); }, [selected?.id]);
  if (selected) {
    const articles = adaptCover({ ...selected, user_id: '', items: selected.items || [] }).items;
    return <main id="main" className="library-page collection-page">
      <button className="text-button collection-back" onClick={() => { setConfirmDelete(false); onBack(); }}><ArrowLeft size={16} />Toutes mes bibliothèques</button>
      <header className="collection-heading"><div className="collection-cover"><EditionArtwork key={selected.id} edition={selected} /></div><div><p className="eyebrow">MA BIBLIOTHÈQUE</p><h1>{selected.name}</h1>{selected.description && <p className="collection-description">{selected.description}</p>}<p className="field-help">{selected.item_count} article{selected.item_count !== 1 ? 's' : ''} · Mise à jour le {formatDate(selected.updated_at)}</p><div className="collection-heading-actions"><button className="secondary-button" disabled={!!pending} onClick={() => onEdit(selected)}><Pencil size={15} />Modifier</button><button className="text-button" disabled={!!pending} onClick={() => setConfirmDelete(true)}><Trash2 size={15} />Supprimer</button></div></div></header>
      {confirmDelete && <div className="collection-delete-confirm" role="alert"><p>Supprimer « {selected.name} » et son classement ? Les articles restent dans vos autres bibliothèques et dans le journal.</p><button className="secondary-button" disabled={!!pending} onClick={() => onDelete(selected.id)}>Supprimer cette bibliothèque</button><button className="text-button" disabled={!!pending} onClick={() => setConfirmDelete(false)}>Annuler</button></div>}
      {error && <p className="reader-error" role="alert">{error}</p>}
      {!articles.length && <div className="library-empty"><Bookmark size={34} strokeWidth={1} /><h2>Les premières pages sont à vous.</h2><p>Dans le journal, cliquez sur le marque-page d’un article<br />et choisissez « {selected.name} ».</p><button className="primary-button" onClick={onJournal}>Explorer le journal<ArrowRight size={17} /></button></div>}
      <div className="collection-readings">{articles.map(item => <CollectionArticle key={item.id} item={item} busy={!!pending} onRead={onRead} onSave={onSaveArticle} onRemove={id => onRemoveArticle(selected.id, id)} />)}</div>
    </main>;
  }
  return <main id="main" className="library-page"><header className="library-heading"><Wordmark small /><p className="eyebrow">À CHAQUE CURIOSITÉ, SA COLLECTION</p><h1>Ma bibliothèque<span>.</span></h1><p>Un thème, un projet, une envie. Rassemblez les articles qui vont ensemble.</p></header>
    <div className="library-toolbar"><span>{collections.length} bibliothèque{collections.length !== 1 ? 's' : ''}</span><div className="library-toolbar-actions"><div className="library-switch" aria-label="Présentation des bibliothèques"><button aria-pressed={!spines} onClick={() => setSpines(false)}>Couvertures</button><button aria-pressed={spines} onClick={() => setSpines(true)}>Tranches</button></div><button className="primary-button" disabled={!!pending || loading} onClick={onCreate}><Plus size={16} />Nouvelle bibliothèque</button></div></div>
    {loading && <p role="status">Ouverture de vos bibliothèques…</p>}
    {error && <div className="reader-error" role="alert">{error} <button className="text-button" onClick={onRetry}>Réessayer</button></div>}
    {!loading && !error && !collections.length && <div className="library-empty"><LibraryIcon size={42} strokeWidth={1} /><h2>Donnez une place à vos idées.</h2><p>« Sciences », « À lire ce week-end », « Mon prochain projet »…<br />Créez une bibliothèque, puis ajoutez vos articles depuis le journal.</p><button className="primary-button" onClick={onCreate}>Créer ma première bibliothèque<Plus size={17} /></button></div>}
    <div className={`library-shelf ${spines ? 'show-spines' : ''}`}>{collections.map(collection => <article className="library-volume" key={collection.id}><button className="edition-open" disabled={!!pending || loading} onClick={() => onOpen(collection.id)} aria-label={`Ouvrir la bibliothèque ${collection.name}`}><EditionArtwork edition={collection} spine={spines} /></button><div className="library-volume-caption"><span>{collection.item_count} article{collection.item_count !== 1 ? 's' : ''}</span><h2>{collection.name}</h2><div><button className="text-button" disabled={!!pending || loading} onClick={() => onOpen(collection.id)}>Voir les articles<ArrowRight size={14} /></button><button className="remove-edition" disabled={!!pending} onClick={() => onEdit(collection)} aria-label={`Modifier ${collection.name}`}><Pencil size={15} /></button></div></div></article>)}</div>
  </main>;
}
