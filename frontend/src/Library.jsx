import { useState } from 'react';
import { ArrowRight, BookOpen, Library as LibraryIcon, LogOut, Check, Bookmark, X } from 'lucide-react';
import { Wordmark } from './components.jsx';
import { enterAccount } from './accounts.js';
import { formatDate, articleImageUrl } from './reader.js';
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
      <section className="account-editorial"><p className="eyebrow">LE PLAISIR DE GARDER L’ESSENTIEL</p><h1>Des lectures.<br />Des idées.<br /><em>Une collection.</em></h1><p>Votre journal, vos découvertes, votre bibliothèque.<br />Retrouvez les revues qui méritent une place chez vous.</p><div className="account-book-art" aria-hidden="true"><div>Kiosque<span>LES IDÉES<br />RESTENT.</span><small>VOTRE BIBLIOTHÈQUE PERSONNELLE</small></div><i>Le monde à portée de page.</i></div></section>
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

export function SaveEdition({ saved, busy, onSave }) {
  return <div className="save-edition"><div><strong>Une revue à garder ?</strong><span>Retrouvez-la avec sa couverture dans votre bibliothèque.</span></div><button className="secondary-button" disabled={busy || saved} onClick={onSave}>{saved ? <Check size={17} /> : <Bookmark size={17} />}{saved ? 'Dans ma bibliothèque' : 'Sauvegarder la revue'}</button></div>;
}

export function EditionArtwork({ edition, spine = false }) {
  const [failed, setFailed] = useState([]);
  const art = edition.artwork || {};
  const photos = (art.photos || []).filter(id => !failed.includes(id));
  const serial = edition.id.slice(0, 4).toUpperCase();
  return <div className={`edition-art palette-${art.palette || 0} ${spine ? 'spine-only' : ''}`}>
    <div className="edition-spine">{spine ? <><span className="spine-brand">K.</span><div className="spine-label"><span className="spine-kicker">KIOSQUE · LA COLLECTION</span><strong>{edition.title}</strong></div><small className="spine-date"><span>№ {serial}</span>{formatDate(edition.created_at)}</small></> : <><span>K.</span><strong>{edition.title}</strong></>}</div>
    {!spine && <div className="edition-face"><div className="edition-art-meta"><span>LA REVUE PERSONNELLE</span><span>№ {serial}</span></div><div className="edition-masthead">Kiosque<span>.</span></div><div className={`edition-collage photos-${photos.length}`} aria-hidden="true">{photos.map(id => <img key={id} src={articleImageUrl({ article_id: id })} alt="" loading="lazy" onError={() => setFailed(previous => [...previous, id])} />)}{!photos.length && <span className="edition-monogram">K.</span>}</div><div className="edition-cover-title">{edition.title}</div><p className="edition-cover-sections">{(art.sections || []).join(' / ')}</p><div className="edition-art-footer"><span>{formatDate(edition.created_at)}</span><span>{edition.item_count} articles</span></div></div>}
  </div>;
}

export default function Library({ editions, loading, error, pending, onRetry, onOpen, onRemove, onJournal }) {
  const [spines, setSpines] = useState(false);
  return <main id="main" className="library-page"><header className="library-heading"><Wordmark small /><p className="eyebrow">VOS LECTURES ONT UNE HISTOIRE</p><h1>Ma bibliothèque<span>.</span></h1><p>Les revues que vous avez choisi de garder. À ouvrir, et à redécouvrir.</p></header>
    <div className="library-toolbar"><span>{editions.length} revue{editions.length !== 1 ? 's' : ''} sauvegardée{editions.length !== 1 ? 's' : ''}</span><div className="library-switch" aria-label="Présentation des revues"><button aria-pressed={!spines} onClick={() => setSpines(false)}>Couvertures</button><button aria-pressed={spines} onClick={() => setSpines(true)}>Tranches</button></div></div>
    {loading && <p role="status">Ouverture de votre bibliothèque…</p>}
    {error && <div className="reader-error" role="alert">{error} <button className="text-button" onClick={onRetry}>Réessayer</button></div>}
    {!loading && !error && !editions.length && <div className="library-empty"><LibraryIcon size={42} strokeWidth={1} /><h2>Votre première place est réservée.</h2><p>Ouvrez une revue, puis cliquez sur « Sauvegarder la revue ».<br />Sa couverture et sa tranche apparaîtront ici.</p><button className="primary-button" onClick={onJournal}>Retour au journal<ArrowRight size={17} /></button></div>}
    <div className={`library-shelf ${spines ? 'show-spines' : ''}`}>{editions.map(edition => <article className="library-volume" key={edition.id}><button className="edition-open" disabled={!!pending} onClick={() => onOpen(edition.id)} aria-label={`Lire ${edition.title}`}><EditionArtwork edition={edition} spine={spines} /></button><div className="library-volume-caption"><span>{formatDate(edition.created_at)}</span><h2>{edition.title}</h2><div><button className="text-button" disabled={!!pending} onClick={() => onOpen(edition.id)}>Lire la revue<ArrowRight size={14} /></button><button className="remove-edition" disabled={!!pending} onClick={() => onRemove(edition.id)} aria-label={`Retirer ${edition.title} de ma bibliothèque`} title="Retirer de ma bibliothèque"><X size={16} /></button></div></div></article>)}</div>
  </main>;
}
