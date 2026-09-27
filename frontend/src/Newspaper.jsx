import { useEffect, useState } from 'react';
import { SlidersHorizontal } from 'lucide-react';
import { ArticleCard, Wordmark } from './components.jsx';
import { formatDate } from './reader.js';
import Events from './Events.jsx';
import './newspaper.css';

// Let short selections use the available width; CSS further reduces columns on small screens.
const articleColumns = count => ({ '--article-columns': Math.min(3, Math.max(1, count)) });

export default function Newspaper({ profile, cover, saved, onSave, onOrganize, saving, onOpen, onRead, onPreferences, busy, children, liked = [], liking = [], canLike, onLike }) {
  const [filter, setFilter] = useState('all');
  useEffect(() => { setFilter('all'); }, [cover?.id]);
  const sections = cover?.sections || [];
  const items = cover?.items || [];
  const filtered = items.filter(article => article.section === sections.find(section => section.id === filter)?.label);
  function card(article, variant = '') {
    return <ArticleCard liked={liked.includes(article.id)} liking={liking.includes(article.id)} canLike={canLike} onLike={onLike} key={article.id} article={article} variant={variant} saved={saved.includes(article.id)} onSave={onSave} onOrganize={onOrganize} saving={saving} onOpen={onOpen} onRead={onRead} />;
  }
  return <div className={`newspaper${cover ? ' has-edition' : ''}`}>
    <header className="paper-header">
      <div className="masthead"><button className="masthead-home" onClick={() => setFilter('all')} aria-label="Kiosque, retour à la une"><Wordmark /></button><button className="preferences-button" onClick={onPreferences} disabled={busy}><SlidersHorizontal size={16} /> Mes préférences</button></div>
      <nav className="paper-navigation" aria-label="Rubriques du journal"><div className="nav-topics"><button className={filter === 'all' ? 'active' : ''} aria-current={filter === 'all' ? 'page' : undefined} onClick={() => setFilter('all')}>La une</button><button className={filter === 'events' ? 'active' : ''} aria-current={filter === 'events' ? 'page' : undefined} onClick={() => setFilter('events')}>Événements</button>{sections.map(section => <button key={section.id} className={filter === section.id ? 'active' : ''} aria-current={filter === section.id ? 'page' : undefined} onClick={() => setFilter(section.id)}>{section.label}</button>)}</div></nav>
    </header>
    <main id="main" className="paper-main">
      <div className="edition-intro"><div><h1>{filter === 'events' ? <>À voir, à écouter,<br /><em>à vivre.</em></> : filter === 'all' ? (cover?.title || <>Le monde, <em>de votre point de vue.</em></>) : sections.find(section => section.id === filter)?.label}</h1><p>{filter === 'events' ? 'Vos centres d’intérêt prennent rendez-vous avec le monde.' : cover ? `${items.length} articles · ${formatDate(cover.createdAt)}` : 'Choisissez vos sujets, puis composez votre première édition.'}</p></div></div>
      {filter === 'events' ? <Events profile={profile} onPreferences={onPreferences} /> : <>
      {children}
      {cover && cover.status !== 'complete' && <div className="edition-warning" role="status"><strong>{cover.status === 'fallback' ? 'Édition de secours' : 'Édition partielle'}</strong><p>{cover.status === 'fallback' ? 'La sélection n’a pas été validée par le rédacteur. Ces articles ont été retenus automatiquement.' : 'Le rédacteur n’a pas pu compléter entièrement cette édition avec les articles disponibles.'}</p></div>}
      {cover && !items.length && <div className="empty-state"><h2>Aucun article retenu.</h2><p>Ajustez vos sujets ou enrichissez le catalogue depuis l’administration.</p></div>}
      {items.length > 0 && (filter === 'all' ? <>
        {cover.lead && <section className="front-stories" aria-label="Les grands titres">
          {card(cover.lead, 'lead')}
          {!!cover.secondary.length && <div className="supporting-stories article-flow" style={articleColumns(cover.secondary.length)}>{cover.secondary.map(article => card(article, 'secondary'))}</div>}
          {!!cover.briefs.length && <aside className="briefs-band"><div className="briefs-heading"><h2>En bref</h2></div><div className="article-flow" style={articleColumns(cover.briefs.length)}>{cover.briefs.map(article => card(article, 'brief'))}</div></aside>}
        </section>}
        {!!cover.remainingSections.length && <div className="topic-sections">{cover.remainingSections.map(section => <section className="topic-section" key={section.id} aria-labelledby={section.id}><div className="section-heading"><h2 id={section.id}>{section.label}</h2></div><div className="section-articles article-flow" style={articleColumns(section.articles.length)}>{section.articles.map(article => card(article, 'section-article'))}</div></section>)}</div>}
        {!!cover.exploration.length && <section className="exploration-section" aria-labelledby="exploration-heading"><div className="section-heading"><h2 id="exploration-heading">Exploration</h2></div><div className="exploration-articles article-flow" style={articleColumns(cover.exploration.length)}>{cover.exploration.map(article => card(article, 'section-article'))}</div></section>}
      </> : <section className="filtered-articles article-flow" style={articleColumns(filtered.length)} aria-label="Articles de la rubrique">{filtered.length ? filtered.map(article => card(article, 'filtered-article')) : <div className="empty-state"><h2>Aucun article dans cette rubrique.</h2><p>Retrouvez les autres lectures à la une.</p></div>}</section>)}
      {filter === 'all' && <Events profile={profile} compact onExplore={() => { setFilter('events'); window.scrollTo({ top: 0, behavior: 'smooth' }); }} onPreferences={onPreferences} />}
      </>}
    </main>
    <footer className="paper-footer"><Wordmark small /><a className="footer-demo" href="/admin" target="_blank" rel="noreferrer">Sources et administration</a></footer>
  </div>;
}
