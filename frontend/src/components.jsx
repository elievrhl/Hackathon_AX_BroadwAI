import { useEffect, useRef, useState } from 'react';
import { Heart, ArrowRight, ArrowUpRight, ArrowLeft, Check, X, Globe2, Cpu, TrendingUp, FlaskConical, Leaf, BookOpen, LogOut, Sparkles, Landmark, Lightbulb, Library, Clapperboard, Music2, Palette, HeartPulse, Trophy, CookingPot, Compass, BriefcaseBusiness, GraduationCap, Gamepad2, Telescope } from 'lucide-react';
import { TOPICS, DEFAULT_PROFILE, formatDate, contentAction } from './reader.js';
import { Play, Video, Headphones } from 'lucide-react';
import { ThemeButton } from './ThemePicker.jsx';
import { ArticleFeedback } from './FeedbackForms.jsx';
import ArticleSaveActions from './ArticleSaveActions.jsx';
const ICONS = {
  tech: Cpu, economy: TrendingUp, world: Globe2, science: FlaskConical, climate: Leaf, culture: BookOpen,
  history: Landmark, philosophy: Lightbulb, books: Library, cinema: Clapperboard, music: Music2,
  art: Palette, health: HeartPulse, sports: Trophy, food: CookingPot, travel: Compass,
  business: BriefcaseBusiness, education: GraduationCap, gaming: Gamepad2, space: Telescope,
};
export function Wordmark({
  small = false
}) {
  return <span className={`wordmark ${small ? 'wordmark-small' : ''}`}>Kiosque<span className="brand-dot">.</span></span>;
}
export function SetupLayout({ children, className = '', onExplore }) {
  return <div className={`account-page setup-page ${className}`}>
    <header className="account-header"><Wordmark small /><div className="account-header-tools">{onExplore ? <button className="text-button" onClick={onExplore}>Feuilleter une édition <ArrowUpRight size={16} /></button> : <span className="account-tagline">LE MONDE, À VOTRE MESURE.</span>}<ThemeButton /></div></header>
    <main id="main" className="account-main">
      <section className="account-editorial"><p className="eyebrow">LE PLAISIR DE DÉCOUVRIR</p><h1>Des lectures.<br />Des regards.<br /><em>Votre journal.</em></h1><p>Une sélection qui suit vos curiosités et élargit vos horizons.<br />Prenez le temps de lire ce qui vous intéresse.</p><div className="account-book-art" aria-hidden="true"><div>Kiosque<span>LE MONDE<br />S’OUVRE.</span><small>VOTRE JOURNAL PERSONNEL</small></div><i>Le monde à portée de page.</i></div></section>
      {children}
    </main>
  </div>;
}
export function SetupProgress({ step }) {
  return <>
    <div className="step-label"><span>{step === 1 ? 'FAISONS CONNAISSANCE' : 'DERNIÈRE ÉTAPE'}</span><span aria-label={`Étape ${step} sur 2`}>0{step}<span className="muted"> / 02</span></span></div>
    <div className="step-track" aria-hidden="true"><span /><span className={step === 2 ? 'active' : ''} /></div>
  </>;
}
function TopicChoices({
  value,
  onChange
}) {
  function toggle(id) {
    onChange(value.includes(id) ? value.filter(topic => topic !== id) : [...value, id]);
  }
  return <div className="topic-choices">
    {TOPICS.map(topic => {
      const Icon = ICONS[topic.id] || BookOpen;
      return <button key={topic.id} type="button" className={`topic-choice ${value.includes(topic.id) ? 'selected' : ''}`} aria-pressed={value.includes(topic.id)} onClick={() => toggle(topic.id)}>
        <Icon size={19} strokeWidth={1.5} /><span>{topic.label}</span><span className="choice-check">{value.includes(topic.id) && <Check size={13} />}</span>
      </button>;
    })}
  </div>;
}
export function Onboarding({
  initialName = '',
  saving = false,
  error = '',
  onComplete,
  onExplore
}) {
  const [step, setStep] = useState(initialName ? 1 : 0);
  const [draft, setDraft] = useState({
    ...DEFAULT_PROFILE,
    name: initialName,
    topics: [],
    notes: ''
  });
  const titleRef = useRef(null);
  useEffect(() => {
    if (step) titleRef.current?.focus({ preventScroll: true });
  }, [step]);
  return <SetupLayout className={step === 1 ? 'onboarding--interests' : ''} onExplore={onExplore}>
      <section className="onboard-panel" aria-labelledby="onboard-title">
        <SetupProgress step={step + 1} />
        <h2 id="onboard-title" ref={titleRef} tabIndex={-1}>{step === 0 ? <>Votre une <br />commence ici.</> : 'Vos centres d’intérêt'}</h2>
        <p className="panel-intro">{step === 0 ? 'Un prénom, quelques envies. Votre journal commence ici.' : 'Choisissez vos sujets, votre favori en premier.'}</p>
        {step === 0 ? <form onSubmit={event => {
          event.preventDefault();
          if (draft.name.trim()) setStep(1);
        }}>
          <label className="field">Votre prénom<input autoComplete="given-name" name="name" placeholder="Camille" value={draft.name} onChange={event => setDraft({
              ...draft,
              name: event.target.value
            })} required maxLength={40} pattern=".*\S.*" /></label>
          <button className="primary-button full-width" type="submit">Choisir mes sujets <ArrowRight size={18} /></button>
          <p className="prototype-note">Vos sujets guident la sélection de vos prochaines lectures.</p>
        </form> : <form className="interests-form" onSubmit={event => {
          event.preventDefault();
          if (draft.topics.length) onComplete({
            ...draft,
            name: draft.name.trim()
          });
        }}>
          <div className="interests-selection">
            <fieldset><legend className="sr-only">Choisissez au moins un centre d’intérêt</legend><TopicChoices value={draft.topics} onChange={topics => setDraft({
                ...draft,
                topics
              })} /></fieldset>
            <p className="sr-only" role="status">{draft.topics.length ? `${draft.topics.length} sujet${draft.topics.length > 1 ? 's' : ''} sélectionné${draft.topics.length > 1 ? 's' : ''}` : 'Choisissez au moins un sujet.'}</p>
          </div>
          <div className="interests-footer">
            <label className="field interests-context">Votre contexte <span className="optional">Facultatif</span>
              <textarea rows={2} maxLength={500} placeholder="Un métier, un projet, une envie…" value={draft.notes} onChange={event => setDraft({
                  ...draft,
                  notes: event.target.value
                })} />
            </label>
            <div className="interests-actions">
              {error && <p className="reader-error" role="alert">{error}</p>}
              <button className="text-button" type="button" onClick={() => setStep(0)}><ArrowLeft size={15} /> Retour</button>
              <button className="primary-button" type="submit" disabled={saving || !draft.topics.length}>{saving ? 'Enregistrement…' : 'Ouvrir mon journal'} <ArrowRight size={18} /></button>
            </div>
          </div>
        </form>}
        {step === 0 && <div className="panel-footnote"><span className="small-star">✳</span><span>Vos goûts évoluent. Votre journal aussi.<br />Vous pourrez tout ajuster à tout moment.</span></div>}
      </section>
  </SetupLayout>;
}
function ArticleMeta({
  article
}) {
  return <div className="article-meta">
    <span>{article.channelTitle || article.source}</span>
    {article.format === 'video' && <span className="video-label"><Play size={11} fill="currentColor" aria-hidden="true" /> YouTube</span>}
    {article.publishedAt && <><span className="meta-dot" aria-hidden="true">·</span><time dateTime={article.publishedAt}>{formatDate(article.publishedAt)}</time></>}
    {!!article.readingTimeMinutes && <><span className="meta-dot" aria-hidden="true">·</span><span className="reading-time" title="Temps de lecture estimé à 200 mots par minute.">≈ {article.readingTimeMinutes} min</span></>}
    {article.duration && <><span className="meta-dot" aria-hidden="true">·</span><span className="reading-time" title={article.format === 'podcast' ? 'Durée de l’épisode' : 'Durée de la vidéo'}>{article.duration}</span></>}
  </div>;
}

function PublisherLink({ article, onRead, children, ...props }) {
  if (!article.url) return <span {...props}>{children}</span>;
  return <a {...props} href={article.url} target="_blank" rel="noopener noreferrer"
    onClick={() => onRead?.(article)} onAuxClick={event => { if (event.button === 1) onRead?.(article); }}>
    {children}
  </a>;
}

function ArticleVisual({ article, onRead, priority = false }) {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  if (!article.imageUrl || failed) return null;
  const picture = <img src={article.imageUrl} alt={article.imageAlt} loading={priority ? 'eager' : 'lazy'}
    fetchPriority={priority ? 'high' : 'auto'} decoding="async" width="900" height="600"
    onLoad={event => {
      if (event.currentTarget.naturalWidth < 120 || event.currentTarget.naturalHeight < 90) setFailed(true);
      else setLoaded(true);
    }} onError={() => setFailed(true)} />;
  const content = <>{picture}{article.format === 'video' && <span className="video-play" aria-hidden="true"><Play size={21} fill="currentColor" /></span>}</>;
  return <figure className={`article-visual${loaded ? ' is-loaded' : ''}${article.format === 'video' ? ' video-visual' : ''}${article.format === 'podcast' ? ' podcast-visual' : ''}`} inert={!loaded}>
    {article.url ? <PublisherLink className="article-image-button" article={article} onRead={onRead} aria-label={`${contentAction(article.format)} : ${article.title}`}>{content}</PublisherLink> : content}
  </figure>;
}
export function MediaBadge({ format }) {
  if (!['video', 'podcast'].includes(format)) return null;
  const Icon = format === 'podcast' ? Headphones : Video;
  return <span className="media-format-badge"><Icon size={15} strokeWidth={1.8} aria-hidden="true" /><span>{format === 'podcast' ? 'Podcast' : 'Vidéo'}</span></span>;
}

export function ArticleCard({
  article,
  variant = '',
  liked, liking, canLike, onLike,
  onOpen,
  onRead,
  saved,
  onSave,
  onOrganize,
  saving
}) {
  return <article className={`article-card ${variant}`} data-article-id={article.id}>
    <div className="article-inner">
      <ArticleVisual key={article.imageUrl} article={article} onRead={onRead} priority={variant === 'lead'} />
      <div className="article-copy">
        <MediaBadge format={article.format} />
        <h3><PublisherLink className="article-title" article={article} onRead={onRead}>{article.title}</PublisherLink></h3>
        <ArticleMeta article={article} />
        <div className="article-actions"><button className="article-details-button" onClick={() => onOpen(article)} aria-label={`Fiche et avis : ${article.title}`}>Fiche & avis</button><LikeButton article={article} liked={liked} busy={liking} enabled={canLike} onLike={onLike} /><ArticleSaveActions article={article} saved={saved} busy={saving} onSave={onSave} onOrganize={onOrganize} /></div>
      </div>
    </div>
  </article>;
}
export function Modal({
  className = '',
  labelId,
  open = true,
  onClose,
  children
}) {
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!open) return;
    const originalOverflow = document.body.style.overflow;
    dialog.showModal();
    document.body.style.overflow = 'hidden';
    return () => {
      dialog.close();
      document.body.style.overflow = originalOverflow;
    };
  }, [open]);
  return <dialog className={className} ref={ref} aria-labelledby={labelId} onCancel={onClose} onClick={event => {
    if (event.target === event.currentTarget) {
      const rect = event.currentTarget.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose();
    }
  }}>
    <button className="close-button" onClick={onClose} aria-label="Fermer"><X size={22} /></button>{children}
  </dialog>;
}
export function ArticleDetail({
  liked, liking, canLike, onLike,
  article,
  saved,
  onSave,
  onOrganize,
  saving,
  canFeedback,
  feedback,
  notice,
  onFeedback,
  onMemory,
  size,
  onRead,
  onClose
}) {
  return <Modal className="article-dialog" labelId="article-title" onClose={onClose}>
    <Wordmark small />
    <div className="detail-kicker eyebrow">{article.section} <span>/</span> {article.kind}</div>
    <LikeButton article={article} liked={liked} busy={liking} enabled={canLike} onLike={onLike} />
    <MediaBadge format={article.format} />
    <h2 id="article-title">{article.title}</h2>
    <ArticleMeta article={article} />
    <ArticleVisual key={article.imageUrl} article={article} onRead={onRead} priority />
    {article.exploration && article.explorationReason && <p className="exploration-reason">{article.explorationReason}</p>}
    <div className="publisher-action">{article.url && <a className="primary-button" href={article.url} target="_blank" rel="noopener noreferrer" onClick={() => onRead(article)}>{contentAction(article.format)} <ArrowRight size={17} /></a>}</div>
    <details className="article-brief"><summary>Voir la fiche de lecture</summary><p className="detail-summary">{article.summary}</p>
      {!!article.keyPoints.length && <div className="detail-keypoints"><h3>L’essentiel</h3><ol>{article.keyPoints.map((point, index) => <li key={index}>{point}</li>)}</ol></div>}
      {article.excerptOnly && <p className="prototype-note">{article.format === 'podcast' ? 'Sujet présenté à partir de la description de l’épisode. L’audio n’a pas été transcrit.' : article.format === 'video' ? 'Sujet présenté à partir de la description de la chaîne. La vidéo n’a pas été transcrite.' : 'Fiche préparée à partir d’un extrait : le texte intégral n’a pas pu être récupéré.'}</p>}
      {!!article.caveats.length && <ul className="article-caveats">{article.caveats.map((note, index) => <li key={index}>{note}</li>)}</ul>}
    </details>
    {article.reason && <div className="relevance"><Sparkles size={18} strokeWidth={1.5} /><div><h3>{article.format === 'podcast' ? 'Pourquoi cet épisode ?' : article.format === 'video' ? 'Pourquoi cette vidéo ?' : 'Pourquoi cet article ?'}</h3><p>{article.reason}</p></div></div>}
    {canFeedback ? <ArticleFeedback article={article} feedback={feedback} onFeedback={onFeedback} onMemory={onMemory} size={size} /> : <p className="prototype-note">Cette édition appartient à un autre lecteur. Les retours seront disponibles sur vos propres éditions.</p>}
    <div className="detail-actions"><ArticleSaveActions article={article} saved={saved} busy={saving} onSave={onSave} onOrganize={onOrganize} labelled /><button className="text-button" onClick={onClose}>Retour au journal <ArrowRight size={16} /></button></div>
    <p className="prototype-note detail-disclaimer">{article.format === 'podcast' ? 'L’épisode s’ouvre chez son éditeur, ou via son lien audio public.' : article.format === 'video' ? 'La vidéo s’ouvre directement sur YouTube.' : 'La lecture complète se fait sur le site de l’éditeur, qui peut demander un abonnement.'}</p>
    {notice && <p className="feedback-notice" role="status">{notice}</p>}
  </Modal>;
}
export function Preferences({
  profile,
  saving = false,
  error = '',
  onSave,
  onClose,
  onReset,
  onMemory
}) {
  const [draft, setDraft] = useState({
    ...profile,
    topics: [...profile.topics]
  });
  return <Modal className="profile-dialog" labelId="profile-title" onClose={onClose}>
    <span className="eyebrow">UNE UNE QUI VOUS RESSEMBLE</span><h2 id="profile-title">Votre regard,<br /><em>vos réglages.</em></h2>
    <form onSubmit={event => {
      event.preventDefault();
      if (draft.topics.length && draft.name.trim()) onSave({
        ...draft,
        name: draft.name.trim()
      });
    }}>
      <label className="field">Votre prénom<input name="name" autoComplete="given-name" value={draft.name} onChange={event => setDraft({
          ...draft,
          name: event.target.value
        })} required maxLength={40} pattern=".*\S.*" /></label>
      <fieldset><legend>Vos sujets</legend><TopicChoices value={draft.topics} onChange={topics => setDraft({
          ...draft,
          topics
        })} /></fieldset>
      <p className="field-help">Le premier sujet reçoit plus de poids. Gardez-en au moins un.</p>
      <fieldset className="edition-size"><legend>La taille de votre édition</legend><div className="size-options">{[15, 18, 20].map(size => <label key={size} className={draft.size === size ? 'active' : ''}><input type="radio" name="size" value={size} checked={draft.size === size} onChange={() => setDraft({
              ...draft,
              size
            })} /><span>{size} contenus</span></label>)}</div></fieldset>
      <label className="field">Votre contexte <span className="optional">Facultatif</span><textarea rows={2} maxLength={500} value={draft.notes} onChange={event => setDraft({
          ...draft,
          notes: event.target.value
        })} placeholder="Un métier, un projet, une curiosité…" /></label>
      <label className="field">Langues des articles<select value={draft.languages.includes('en') ? 'fr-en' : 'fr'} onChange={event => setDraft({ ...draft, languages: event.target.value === 'fr-en' ? ['fr', 'en'] : ['fr'] })}><option value="fr-en">Français et anglais</option><option value="fr">Français</option></select></label>
      <p className="field-help">Ces préférences seront utilisées pour votre prochaine une.</p>
      {error && <p className="reader-error" role="alert">{error}</p>}
      <button className="primary-button full-width" disabled={saving || !draft.topics.length} type="submit">{saving ? 'Enregistrement…' : 'Enregistrer mes préférences'} <Check size={18} /></button>
      <p className="prototype-note">Vos préférences accompagnent vos prochaines lectures.</p>
      <button className="secondary-button" type="button" onClick={onMemory}>Écrire à Kiosque · Ma fiche lecteur</button>
      <button className="text-button reset-button" type="button" disabled={saving} onClick={onReset}><LogOut size={15} /> Rechoisir mes centres d’intérêt</button>
    </form>
  </Modal>;
}

function LikeButton({ article, liked, busy, enabled, onLike }) {
  return <button type="button" className={`like-button${liked ? ' is-liked' : ''}`} disabled={!enabled || busy}
    aria-label={`${liked ? 'Retirer mon like' : 'J’aime'} : ${article.title}`} aria-pressed={!!liked}
    title={enabled ? (liked ? 'Retirer ce like de mes préférences' : 'J’aime — affine mes prochaines sélections') : 'Les likes sont disponibles sur vos propres éditions après chargement.'}
    onClick={() => onLike(article)}><Heart size={17} strokeWidth={1.5} fill={liked ? 'currentColor' : 'none'} /></button>;
}
