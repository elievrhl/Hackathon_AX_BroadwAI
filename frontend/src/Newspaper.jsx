import { useEffect, useState } from 'react';
import { Bookmark, SlidersHorizontal } from 'lucide-react';
import { ArticleCard, Wordmark } from './components.jsx';
import { formatDate, contentCount } from './reader.js';
import Events from './Events.jsx';

export default function Newspaper({ profile, cover, saved, onSave, onOpen, onRead, onPreferences, busy, children, liked = [], liking = [], canLike, onLike }) {
  const [filter, setFilter] = useState('all');
  useEffect(() => { setFilter('all'); }, [cover?.id]);
  const sections = cover?.sections || [];
  const items = cover?.items || [];
  const savedCount = items.filter(article => saved.includes(article.id)).length;
  const filtered = filter === 'saved' ? items.filter(article => saved.includes(article.id)) : items.filter(article => article.section === sections.find(section => section.id === filter)?.label);
  function card(article, variant = '') {
    return <ArticleCard liked={liked.includes(article.id)} liking={liking.includes(article.id)} canLike={canLike} onLike={onLike} key={article.id} article={article} variant={variant} saved={saved.includes(article.id)} onSave={onSave} onOpen={onOpen} onRead={onRead} />;
  }
  return <div className={`newspaper${cover ? ' has-edition' : ''}`}>
    <header className="paper-header">
      <div className="masthead"><button className="masthead-home" onClick={() => setFilter('all')} aria-label="Kiosque, retour à la une"><Wordmark /></button><button className="preferences-button" onClick={onPreferences} disabled={busy}><SlidersHorizontal size={16} /> Mes préférences</button></div>
      <nav className="paper-navigation" aria-label="Rubriques du journal"><div className="nav-topics"><button className={filter === 'all' ? 'active' : ''} aria-current={filter === 'all' ? 'page' : undefined} onClick={() => setFilter('all')}>La une</button><button className={filter === 'events' ? 'active' : ''} aria-current={filter === 'events' ? 'page' : undefined} onClick={() => setFilter('events')}>Événements</button>{sections.map(section => <button key={section.id} className={filter === section.id ? 'active' : ''} aria-current={filter === section.id ? 'page' : undefined} onClick={() => setFilter(section.id)}>{section.label}</button>)}</div><button className={`saved-tab ${filter === 'saved' ? 'active' : ''}`} aria-label={`À garder, ${savedCount} contenus de cette édition`} onClick={() => setFilter('saved')}><Bookmark size={16} /><span>À garder</span>{savedCount > 0 && <span className="save-count">{savedCount}</span>}</button></nav>
    </header>
    <main id="main" className="paper-main">
      <div className="edition-intro"><div><h1>{filter === 'events' ? <>À voir, à écouter,<br /><em>à vivre.</em></> : filter === 'all' ? (cover?.title || <>Le monde, <em>de votre point de vue.</em></>) : filter === 'saved' ? 'Les idées que vous gardez.' : sections.find(section => section.id === filter)?.label}</h1><p>{filter === 'events' ? 'Vos centres d’intérêt prennent rendez-vous avec le monde.' : cover ? `${contentCount(items)} · ${formatDate(cover.createdAt)}` : 'Choisissez vos sujets, puis composez votre première édition.'}</p></div></div>
      {filter === 'events' ? <Events profile={profile} onPreferences={onPreferences} /> : <>
      {children}
      {cover && cover.status !== 'complete' && <div className="edition-warning" role="status"><strong>{cover.status === 'fallback' ? 'Édition de secours' : 'Édition partielle'}</strong><p>{cover.status === 'fallback' ? 'La sélection n’a pas été validée par le rédacteur. Ces articles ont été retenus automatiquement.' : 'Le rédacteur n’a pas pu compléter entièrement cette édition avec les articles disponibles.'}</p></div>}
      {cover && !items.length && <div className="empty-state"><h2>Aucun article retenu.</h2><p>Ajustez vos sujets ou enrichissez le catalogue depuis l’administration.</p></div>}
      {items.length > 0 && (filter === 'all' ? <>
        {cover.lead && <>
        <section className={`front-grid${cover.secondary.length ? ' has-secondary' : ''}${cover.briefs.length ? ' has-briefs' : ''}`} aria-label="Les grands titres">
          {cover.lead && card(cover.lead, 'lead')}
          {!!cover.secondary.length && <div className="secondary-column">{cover.secondary.map(article => card(article, 'secondary'))}</div>}
          {!!cover.briefs.length && <aside className="briefs-column"><div className="briefs-heading"><h2>En bref</h2></div>{cover.briefs.map(article => card(article, 'brief'))}</aside>}
        </section></>}
        <div className="sections-grid">{cover.remainingSections.map(section => <section className="topic-section" key={section.id} aria-labelledby={section.id}><div className="section-heading"><h2 id={section.id}>{section.label}</h2></div><div className="section-articles">{section.articles.map(article => card(article, 'section-article'))}</div></section>)}</div>
        {!!cover.exploration.length && <section className="exploration-section" aria-labelledby="exploration-heading"><div className="section-heading"><h2 id="exploration-heading">Exploration</h2></div><div className="exploration-grid">{cover.exploration.map(article => card(article, 'section-article'))}</div></section>}
      </> : <section className="filtered-articles" aria-label="Articles de la rubrique">{filtered.length ? filtered.map(article => card(article, 'filtered-article')) : <div className="empty-state"><Bookmark size={30} strokeWidth={1} /><h2>Un article vous fait de l’œil ?</h2><p>Choisissez une bibliothèque avec le marque-page pour le retrouver ici.</p></div>}</section>)}
      {filter === 'all' && <Events profile={profile} compact onExplore={() => { setFilter('events'); window.scrollTo({ top: 0, behavior: 'smooth' }); }} onPreferences={onPreferences} />}
      </>}
    </main>
    <footer className="paper-footer"><Wordmark small /><a className="footer-demo" href="/admin" target="_blank" rel="noreferrer">Sources et administration</a></footer>
  </div>;
}
