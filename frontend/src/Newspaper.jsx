import { useEffect, useState } from 'react';
import { Bookmark, ChevronDown, Clock3, SlidersHorizontal, ArrowUpRight } from 'lucide-react';
import { ArticleCard, Wordmark } from './components.jsx';
import { formatDate } from './reader.js';

export default function Newspaper({ profile, cover, saved, onSave, onOpen, onPreferences, busy, children }) {
  const [filter, setFilter] = useState('all');
  useEffect(() => { setFilter('all'); }, [cover?.id]);
  const firstName = profile.name.split(' ')[0];
  const sections = cover?.sections || [];
  const items = cover?.items || [];
  const savedCount = items.filter(article => saved.includes(article.id)).length;
  const filtered = filter === 'saved' ? items.filter(article => saved.includes(article.id)) : items.filter(article => article.section === sections.find(section => section.id === filter)?.label);
  function card(article, variant = '', index) {
    return <ArticleCard key={article.id} article={article} variant={variant} saved={saved.includes(article.id)} index={index} onSave={onSave} onOpen={onOpen} />;
  }
  return <div className={`newspaper${cover ? ' has-edition' : ''}`}>
    <div className="demo-banner"><span>VOTRE ÉDITION LOCALE</span><span className="demo-detail">Des sources réelles · une sélection personnelle</span></div>
    <header className="paper-header">
      <div className="utility-bar"><span className="edition-date">{formatDate(cover?.createdAt || new Date(), true)}</span><span className="edition-label">VOTRE JOURNAL PERSONNEL</span><button className="profile-button" onClick={onPreferences} disabled={busy}><span className="avatar">{firstName.charAt(0).toUpperCase()}</span><span>{firstName}</span><ChevronDown size={14} /></button></div>
      <div className="masthead"><span className="masthead-aside">Les idées se croisent.<br />Votre regard se précise.</span><button className="masthead-home" onClick={() => setFilter('all')} aria-label="Kiosque, retour à la une"><Wordmark /></button><span className="masthead-aside right">ÉDITION PERSONNELLE<br /><span className="issue-number">{cover ? cover.id.slice(0, 6).toUpperCase() : 'À COMPOSER'}</span></span></div>
      <nav className="paper-navigation" aria-label="Rubriques du journal"><div className="nav-topics"><button className={filter === 'all' ? 'active' : ''} aria-current={filter === 'all' ? 'page' : undefined} onClick={() => setFilter('all')}>La une</button>{sections.map(section => <button key={section.id} className={filter === section.id ? 'active' : ''} aria-current={filter === section.id ? 'page' : undefined} onClick={() => setFilter(section.id)}>{section.label}</button>)}</div><button className={`saved-tab ${filter === 'saved' ? 'active' : ''}`} aria-label={`À garder, ${savedCount} articles de cette édition`} onClick={() => setFilter('saved')}><Bookmark size={16} /><span>À garder</span>{savedCount > 0 && <span className="save-count">{savedCount}</span>}</button></nav>
    </header>
    <main id="main" className="paper-main">
      <div className="edition-intro"><div><div className="eyebrow red-text">BONJOUR {firstName.toLocaleUpperCase('fr-FR')}</div><h1>{filter === 'all' ? (cover?.title || <>Le monde, <em>de votre point de vue.</em></>) : filter === 'saved' ? 'Les idées que vous gardez.' : sections.find(section => section.id === filter)?.label}</h1><p>{cover ? `${items.length} articles · ${sections.length} rubriques · édition du ${formatDate(cover.createdAt)}` : 'Vos sujets donnent le cap. Le rédacteur compose votre journal.'}</p></div><button className="preferences-button" onClick={onPreferences} disabled={busy}><SlidersHorizontal size={16} /> Mes préférences</button></div>
      {children}
      {cover && cover.status !== 'complete' && <div className="edition-warning" role="status"><strong>{cover.status === 'fallback' ? 'Édition de secours' : 'Édition partielle'}</strong><p>{cover.status === 'fallback' ? 'La sélection n’a pas été validée par le rédacteur. Ces articles ont été retenus automatiquement.' : 'Le rédacteur n’a pas pu compléter entièrement cette édition avec les articles disponibles.'}</p></div>}
      {cover && !items.length && <div className="empty-state"><h2>Aucun article retenu.</h2><p>Ajustez vos sujets ou enrichissez le catalogue depuis l’administration.</p></div>}
      {items.length > 0 && (filter === 'all' ? <>
        {cover.lead && <><div className="front-label"><span>L’ESSENTIEL DE VOTRE ÉDITION</span><span className="front-label-right">VOTRE SÉLECTION, EN PERSPECTIVE ↓</span></div>
        <section className="front-grid" aria-label="Les grands titres">
          {cover.lead && card(cover.lead, 'lead')}
          {!!cover.secondary.length && <div className="secondary-column">{cover.secondary.map(article => card(article, 'secondary'))}</div>}
          {!!cover.briefs.length && <aside className="briefs-column"><div className="briefs-heading"><Clock3 size={16} /><h2>En bref</h2></div>{cover.briefs.map((article, index) => card(article, 'brief', index))}<div className="briefs-foot">L’essentiel, puis le temps<br />d’aller plus loin.</div></aside>}
        </section></>}
        <div className="editorial-note"><span className="editorial-asterisk">✳</span><p><strong>Des titres pour choisir.</strong> Les articles complets vous attendent chez leurs éditeurs.</p></div>
        <div className="sections-grid">{cover.remainingSections.map((section, index) => <section className="topic-section" key={section.id} aria-labelledby={section.id}><div className="section-heading"><h2 id={section.id}>{section.label}</h2><span className="section-index">{String(index + 1).padStart(2, '0')}</span></div><div className="section-articles">{section.articles.map(article => card(article, 'section-article'))}</div></section>)}</div>
        {!!cover.exploration.length && <section className="exploration-section" aria-labelledby="exploration-heading"><div className="section-heading"><h2 id="exploration-heading">Exploration</h2><span className="section-index">{cover.exploration.length} {cover.exploration.length === 1 ? 'découverte' : 'découvertes'}</span></div><p className="exploration-intro">Pour compléter votre édition, des thèmes voisins qui ouvrent d’autres perspectives.</p><div className="exploration-grid">{cover.exploration.map(article => card(article, 'section-article'))}</div></section>}
        <div className="end-of-edition"><span className="end-symbol">K<span>.</span></span><div><h2>Vous avez fait le tour.<br /><em>Pas besoin de faire défiler à l’infini.</em></h2><p>{items.length} articles. Des idées à laisser infuser. À votre rythme.</p></div><button className="text-button" disabled={busy} onClick={onPreferences}>Affiner mes intérêts <ArrowUpRight size={16} /></button></div>
      </> : <section className="filtered-articles" aria-label="Articles de la rubrique">{filtered.length ? filtered.map(article => card(article, 'filtered-article')) : <div className="empty-state"><Bookmark size={30} strokeWidth={1} /><h2>Un article vous fait de l’œil ?</h2><p>Gardez-le avec le marque-page pour le retrouver ici.</p></div>}</section>)}
    </main>
    <footer className="paper-footer"><Wordmark small /><span>Le monde mérite plus qu’un fil d’actualité.</span><a className="footer-demo" href="/admin" target="_blank" rel="noreferrer">Sources et administration</a></footer>
  </div>;
}
