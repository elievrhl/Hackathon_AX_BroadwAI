import { useEffect, useState } from 'react';
import { ArrowUpRight, ArrowRight, MapPin, Headphones, MonitorPlay, CalendarDays } from 'lucide-react';
import { CATALOG_CHECKED_ON } from './events-catalog.js';
import { EVENT_KINDS, eventDateLabel, selectEvents } from './events.js';
import './events.css';

const FILTERS = [['all', 'Tout'], ['out', 'Sortir'], ['watch', 'Regarder'], ['listen', 'Écouter']];
const dateLabel = new Intl.DateTimeFormat('fr-FR', { dateStyle: 'long', timeZone: 'Europe/Paris' });

export default function Events({ profile, compact = false, onExplore, onPreferences }) {
  const [format, setFormat] = useState('all');
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const update = () => setNow(new Date());
    const timer = window.setInterval(update, 60_000);
    document.addEventListener('visibilitychange', update);
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', update); };
  }, []);
  const suggestions = selectEvents(profile, { now, format: compact ? 'all' : format });
  const items = compact ? suggestions.slice(0, 3) : suggestions;
  const checkedLabel = dateLabel.format(new Date(`${CATALOG_CHECKED_ON}T12:00:00Z`));
  return <section className={`events-section${compact ? ' events-preview' : ''}`} aria-labelledby={compact ? 'events-preview-title' : 'events-title'}>
    <div className="events-heading">
      <div><p className="eyebrow">PROLONGEZ VOS CURIOSITÉS</p><h2 id={compact ? 'events-preview-title' : 'events-title'}>{compact ? 'À voir, à écouter, à vivre.' : 'Des idées pour votre prochain temps libre.'}</h2></div>
      {compact && <button className="text-button" onClick={onExplore}>Tous les événements <ArrowRight size={16} /></button>}
    </div>
    <div className="events-context"><span><MapPin size={15} aria-hidden="true" /> Paris et alentours</span><span>Sorties en cours ou sous 14 jours · Émissions et podcasts en ligne</span></div>
    {!compact && <div className="events-filters" role="group" aria-label="Format des suggestions">{FILTERS.map(([value, label]) => <button type="button" key={value} aria-pressed={format === value} onClick={() => setFormat(value)}>{label}</button>)}</div>}
    <p className="events-count" role="status">{items.length ? `${items.length} suggestion${items.length > 1 ? 's' : ''} selon vos sujets cochés` : 'Aucune suggestion correspondant à vos sujets dans cette sélection.'}</p>
    {items.length ? <div className="events-grid">{items.map(item => {
      const Icon = item.mode === 'out' ? CalendarDays : item.kind === 'podcast' ? Headphones : MonitorPlay;
      return <article className={`event-card event-${item.mode}`} key={item.id}>
        <div className="event-kicker"><span><Icon size={16} aria-hidden="true" />{EVENT_KINDS[item.kind]}</span><span>{item.mode === 'out' ? 'À vivre' : item.kind === 'podcast' ? 'À écouter' : 'À voir'}</span></div>
        <p className="event-date">{eventDateLabel(item, now)}</p>
        <h3><a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a></h3>
        <p className="event-description">{item.description}</p>
        <p className="event-reason">{item.reason}</p>
        <div className="event-practical"><p><MapPin size={14} aria-hidden="true" />{item.venue}</p><p>{item.practical}</p></div>
        <a className="event-link" href={item.url} target="_blank" rel="noopener noreferrer" aria-label={`Voir le site officiel : ${item.title} (nouvel onglet)`}>{item.mode === 'out' ? 'Informations et réservation' : item.kind === 'podcast' ? 'Découvrir le podcast' : 'Découvrir le programme'}<ArrowUpRight size={16} aria-hidden="true" /></a>
      </article>;
    })}</div> : <div className="events-empty"><CalendarDays size={28} strokeWidth={1} /><p>Le catalogue de démonstration est encore limité. Essayez un autre format ou ajustez vos sujets.</p><button className="text-button" onClick={onPreferences}>Mes préférences <ArrowRight size={15} /></button></div>}
    <details className="events-provenance"><summary>Catalogue de démonstration · sources consultées le {checkedLabel}</summary><p>Les suggestions proviennent d’une sélection préparée sur les sites officiels. Les sorties terminées sont retirées selon leurs dates connues. Les horaires, annulations, places restantes et droits de diffusion ne sont pas actualisés en direct : consultez le site officiel avant de vous organiser.</p><p>La sélection suit les sujets cochés dans vos préférences. Les messages du Courrier du lecteur et les notes libres concernent pour l’instant les articles.</p></details>
  </section>;
}
