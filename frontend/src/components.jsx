import { useEffect, useRef, useState } from 'react';
import { Heart, ArrowRight, ArrowUpRight, ArrowLeft, Bookmark, Check, X, Globe2, Cpu, TrendingUp, FlaskConical, Leaf, BookOpen, LogOut, Sparkles, Landmark, Lightbulb, Library, Clapperboard, Music2, Palette, HeartPulse, Trophy, CookingPot, Compass, BriefcaseBusiness, GraduationCap, Gamepad2, Telescope } from 'lucide-react';
import { TOPICS, DEFAULT_PROFILE, formatDate } from './reader.js';
import { ArticleFeedback } from './FeedbackForms.jsx';
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
    if (step) titleRef.current?.focus();
  }, [step]);
  return <div className="onboarding">
    <header className="welcome-header"><Wordmark small /><span className="header-note">Le monde, à votre mesure.</span><button className="text-button" onClick={onExplore}>Feuilleter une édition <ArrowUpRight size={16} /></button></header>
    <main id="main" className="welcome-main">
      <section className="welcome-editorial" aria-label="Bienvenue chez Kiosque">
        <div className="eyebrow"><span className="red-rule" />VOTRE JOURNAL PERSONNEL</div>
        <h1>Moins de bruit. <br />Plus de <em>sens.</em></h1>
        <p className="welcome-description">Le plaisir d’ouvrir un journal. <br />Avec une une qui vous ressemble.</p>
        <div className="sample-paper" aria-label="Aperçu d’une édition fictive">
          <div className="sample-meta"><span>UNE ÉDITION, PLUSIEURS REGARDS</span><span>Nº 001</span></div>
          <div className="sample-name">Kiosque<span>.</span></div>
          <div className="sample-rule" />
          <div className="sample-columns"><div><span className="eyebrow">LE GRAND ANGLE</span><h2>Le monde change.<br />Votre regard aussi.</h2><p>Technologie, société, culture : les idées se croisent, l’essentiel se dessine.</p></div><div className="sample-side"><span className="eyebrow">ET AUSSI</span><h3>L’économie à hauteur de vie</h3><hr /><h3>La science ouvre de nouvelles fenêtres</h3></div></div>
          <div className="sample-bottom">18 articles · une sélection personnelle · de nouveaux horizons</div>
        </div>
        <div className="edition-mark"><span>01 —</span> Une autre façon de prendre le temps.</div>
      </section>
      <section className="onboard-panel" aria-labelledby="onboard-title">
        <div className="step-label"><span>{step === 0 ? 'FAISONS CONNAISSANCE' : 'VOS CENTRES D’INTÉRÊT'}</span><span>0{step + 1}<span className="muted"> / 02</span></span></div>
        <div className="step-track"><span /><span className={step === 1 ? 'active' : ''} /></div>
        <h2 id="onboard-title" ref={titleRef} tabIndex={-1}>{step === 0 ? <>Votre une <br />commence ici.</> : <>Qu’est-ce qui <br />vous anime ?</>}</h2>
        <p className="panel-intro">{step === 0 ? 'Un prénom, quelques envies. Votre journal commence ici.' : 'Choisissez vos sujets. Le premier aura plus de poids ; le rédacteur composera votre sélection.'}</p>
        {step === 0 ? <form onSubmit={event => {
          event.preventDefault();
          if (draft.name.trim()) setStep(1);
        }}>
          <label className="field">Votre prénom<input autoComplete="given-name" name="name" placeholder="Camille" value={draft.name} onChange={event => setDraft({
              ...draft,
              name: event.target.value
            })} required maxLength={40} pattern=".*\S.*" /></label>
          <button className="primary-button full-width" type="submit">Choisir mes sujets <ArrowRight size={18} /></button>
          <p className="prototype-note">Votre profil est conservé dans ce navigateur. Les éditions sont enregistrées sur votre serveur local.</p>
        </form> : <form onSubmit={event => {
          event.preventDefault();
          if (draft.topics.length) onComplete({
            ...draft,
            name: draft.name.trim()
          });
        }}>
          <fieldset><legend className="sr-only">Choisissez au moins un centre d’intérêt</legend><TopicChoices value={draft.topics} onChange={topics => setDraft({
              ...draft,
              topics
            })} /></fieldset>
          <div className="selection-hint" aria-live="polite">{draft.topics.length ? `${draft.topics.length} sujet${draft.topics.length > 1 ? 's' : ''} sélectionné${draft.topics.length > 1 ? 's' : ''}` : 'Un sujet suffit pour commencer.'}</div>
          <label className="field optional-field">Un peu de contexte ? <span className="optional">Facultatif</span><textarea rows={2} maxLength={500} placeholder="Je lance un projet et je m’intéresse à l’IA, sans être spécialiste…" value={draft.notes} onChange={event => setDraft({
              ...draft,
              notes: event.target.value
            })} /></label>
          <p className="field-help">Le rédacteur utilisera vos sujets et ce contexte pour choisir les articles. La génération se lance à l’étape suivante.</p>
          <button className="primary-button full-width" type="submit" disabled={!draft.topics.length}>Ouvrir mon journal <ArrowRight size={18} /></button>
          <button className="text-button back-button" type="button" onClick={() => setStep(0)}><ArrowLeft size={15} /> Retour</button>
        </form>}
        <div className="panel-footnote"><span className="small-star">✳</span><span>Vos goûts évoluent. Votre journal aussi.<br />Vous pourrez tout ajuster à tout moment.</span></div>
      </section>
    </main>
    <footer className="welcome-footer"><span>UN PEU DE RECUL SUR UN MONDE QUI AVANCE.</span><span>Kiosque · Prototype du hackathon</span></footer>
  </div>;
}
function ArticleMeta({
  article
}) {
  return <div className="article-meta">
    <span>{article.source}</span>
    {article.publishedAt && <><span className="meta-dot" aria-hidden="true">·</span><time dateTime={article.publishedAt}>{formatDate(article.publishedAt)}</time></>}
    {!!article.readingTimeMinutes && <><span className="meta-dot" aria-hidden="true">·</span><span className="reading-time" title="Temps de lecture estimé à 200 mots par minute.">≈ {article.readingTimeMinutes} min</span></>}
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
  return <figure className={`article-visual${loaded ? ' is-loaded' : ''}`}>
    {article.url ? <PublisherLink className="article-image-button" article={article} onRead={onRead} aria-label={`Lire : ${article.title}`}>{picture}</PublisherLink> : picture}
  </figure>;
}
export function ArticleCard({
  article,
  variant = '',
  liked, liking, canLike, onLike,
  onOpen,
  onRead,
  saved,
  onSave
}) {
  return <article className={`article-card ${variant}`} data-article-id={article.id}>
    <div className="article-inner">
      {variant !== 'brief' && <ArticleVisual key={article.imageUrl} article={article} onRead={onRead} priority={variant === 'lead'} />}
      <h3><PublisherLink className="article-title" article={article} onRead={onRead}>{article.title}</PublisherLink></h3>
      <ArticleMeta article={article} />
      <div className="article-actions"><button className="article-details-button" onClick={() => onOpen(article)} aria-label={`Fiche et avis : ${article.title}`}>Fiche & avis</button><LikeButton article={article} liked={liked} busy={liking} enabled={canLike} onLike={onLike} /><button className={`save-button ${saved ? 'is-saved' : ''}`} aria-label={`Enregistrer dans une bibliothèque : ${article.title}`} aria-pressed={saved} onClick={() => onSave(article.id)} title={saved ? 'Organiser dans mes bibliothèques' : 'Enregistrer dans une bibliothèque'}><Bookmark size={17} fill={saved ? 'currentColor' : 'none'} strokeWidth={1.5} /></button></div>
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
    <h2 id="article-title">{article.title}</h2>
    <ArticleMeta article={article} />
    <ArticleVisual key={article.imageUrl} article={article} onRead={onRead} priority />
    {article.exploration && article.explorationReason && <p className="exploration-reason">{article.explorationReason}</p>}
    <div className="publisher-action">{article.url && <a className="primary-button" href={article.url} target="_blank" rel="noopener noreferrer" onClick={() => onRead(article)}>Lire chez {article.source} <ArrowRight size={17} /></a>}</div>
    <details className="article-brief"><summary>Voir la fiche de lecture</summary><p className="detail-summary">{article.summary}</p>
      {!!article.keyPoints.length && <div className="detail-keypoints"><h3>L’essentiel</h3><ol>{article.keyPoints.map((point, index) => <li key={index}>{point}</li>)}</ol></div>}
      {article.excerptOnly && <p className="prototype-note">Fiche préparée à partir d’un extrait : le texte intégral n’a pas pu être récupéré.</p>}
      {!!article.caveats.length && <ul className="article-caveats">{article.caveats.map((note, index) => <li key={index}>{note}</li>)}</ul>}
    </details>
    {article.reason && <div className="relevance"><Sparkles size={18} strokeWidth={1.5} /><div><h3>Pourquoi cet article ?</h3><p>{article.reason}</p></div></div>}
    {canFeedback ? <ArticleFeedback article={article} feedback={feedback} onFeedback={onFeedback} onMemory={onMemory} size={size} /> : <p className="prototype-note">Cette édition a été créée avec un autre profil local. Les retours seront disponibles sur vos propres éditions.</p>}
    <div className="detail-actions"><button className="secondary-button" onClick={() => onSave(article.id)}><Bookmark size={17} fill={saved ? 'currentColor' : 'none'} />{saved ? 'Organiser dans mes bibliothèques' : 'Enregistrer dans une bibliothèque'}</button><button className="text-button" onClick={onClose}>Retour au journal <ArrowRight size={16} /></button></div>
    <p className="prototype-note detail-disclaimer">La lecture complète se fait sur le site de l’éditeur, qui peut demander un abonnement.</p>
    {notice && <p className="feedback-notice" role="status">{notice}</p>}
  </Modal>;
}
export function Preferences({
  profile,
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
            })} /><span>{size} articles</span></label>)}</div></fieldset>
      <label className="field">Votre contexte <span className="optional">Facultatif</span><textarea rows={2} maxLength={500} value={draft.notes} onChange={event => setDraft({
          ...draft,
          notes: event.target.value
        })} placeholder="Un métier, un projet, une curiosité…" /></label>
      <label className="field">Langues des articles<select value={draft.languages.includes('en') ? 'fr-en' : 'fr'} onChange={event => setDraft({ ...draft, languages: event.target.value === 'fr-en' ? ['fr', 'en'] : ['fr'] })}><option value="fr-en">Français et anglais</option><option value="fr">Français</option></select></label>
      <p className="field-help">Ces préférences seront utilisées pour votre prochaine génération.</p>
      <button className="primary-button full-width" disabled={!draft.topics.length} type="submit">Enregistrer mes préférences <Check size={18} /></button>
      <p className="prototype-note">Le profil reste dans ce navigateur ; ses intérêts et son contexte sont envoyés au rédacteur lors de la génération.</p>
      <button className="secondary-button" type="button" onClick={onMemory}>Écrire à Kiosque · Ma fiche lecteur</button>
      <button className="text-button reset-button" type="button" onClick={onReset}><LogOut size={15} /> Reconfigurer mon profil local</button>
    </form>
  </Modal>;
}

function LikeButton({ article, liked, busy, enabled, onLike }) {
  return <button type="button" className={`like-button${liked ? ' is-liked' : ''}`} disabled={!enabled || busy}
    aria-label={`${liked ? 'Retirer mon like' : 'J’aime'} : ${article.title}`} aria-pressed={!!liked}
    title={enabled ? (liked ? 'Retirer ce like de mes préférences' : 'J’aime — affine mes prochaines sélections') : 'Les likes sont disponibles sur vos propres éditions après chargement.'}
    onClick={() => onLike(article)}><Heart size={17} strokeWidth={1.5} fill={liked ? 'currentColor' : 'none'} /></button>;
}
