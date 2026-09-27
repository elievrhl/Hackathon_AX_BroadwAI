import { useEffect, useId, useRef, useState } from 'react';
import { ArrowLeft, Bookmark, ChevronRight, FolderPlus, MoreHorizontal, ThumbsDown } from 'lucide-react';
import { REASONS } from './preferences.js';

export default function ArticleSaveActions({ article, saved, busy, onSave, onOrganize, onFeedback, labelled = false }) {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState('actions');
  const [comment, setComment] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [placement, setPlacement] = useState({ below: false, height: 400 });
  const pending = useRef(false);
  const root = useRef(null);
  const trigger = useRef(null);
  const menu = useRef(null);
  const menuId = useId();
  useEffect(() => {
    if (!open) return;
    const outside = event => { if (!pending.current && !root.current?.contains(event.target)) setOpen(false); };
    document.addEventListener('pointerdown', outside);
    return () => document.removeEventListener('pointerdown', outside);
  }, [open]);
  useEffect(() => {
    if (open && step !== 'actions') menu.current?.querySelector(step === 'other' ? 'textarea' : 'button')?.focus();
  }, [open, step]);
  function closeMenu() {
    setOpen(false);
    requestAnimationFrame(() => trigger.current?.focus());
  }
  function toggleMenu() {
    if (open) { closeMenu(); return; }
    const rect = trigger.current.getBoundingClientRect();
    const above = rect.top - 12;
    const below = window.innerHeight - rect.bottom - 12;
    setPlacement({ below: below > above, height: Math.max(above, below) });
    setStep('actions'); setComment(''); setError(''); setOpen(true);
  }
  function choose(action) {
    closeMenu();
    action();
  }
  async function sendReason(reason) {
    if (pending.current) return;
    pending.current = true;
    setSending(true); setError('');
    try {
      await onFeedback(article, { reason, comment: reason === 'other' ? comment.trim() : '' });
      closeMenu();
    } catch (failure) { setError(failure.message); }
    finally { pending.current = false; setSending(false); }
  }
  const saveLabel = saved ? 'Retirer des articles sauvegardés et des collections' : 'Sauvegarder l’article';
  return <div className={`article-save-actions${labelled ? ' labelled' : ''}`}>
    <button type="button" className={`save-button ${saved ? 'is-saved' : ''} ${labelled ? 'save-labelled' : ''}`} disabled={busy}
      aria-label={`${saveLabel} : ${article.title}`} aria-pressed={saved} title={saveLabel} onClick={() => onSave(article)}>
      <Bookmark size={17} fill={saved ? 'currentColor' : 'none'} strokeWidth={1.5} aria-hidden="true" />
      {labelled && <span>{saved ? 'Sauvegardé' : 'Sauvegarder'}</span>}
    </button>
    <div className="article-more" ref={root} onBlur={event => { if (!pending.current && !event.currentTarget.contains(event.relatedTarget)) setOpen(false); }} onKeyDown={event => {
      if (event.key === 'Escape' && open && !pending.current) { event.preventDefault(); closeMenu(); }
    }}>
      <button type="button" className="article-more-trigger" ref={trigger} disabled={busy || sending} aria-expanded={open} aria-controls={menuId}
        aria-label={`Options de l’article : ${article.title}`} title="Options de l’article" onClick={toggleMenu}><MoreHorizontal size={19} aria-hidden="true" /></button>
      {open && <div className={`article-more-menu${placement.below ? ' opens-below' : ''}`} id={menuId} ref={menu} style={{ '--article-menu-height': `${placement.height}px` }} aria-busy={sending}>
        {step === 'actions' ? <>
          {onFeedback && <button type="button" title="Choisir une raison" onClick={() => setStep('reasons')}><ThumbsDown size={16} aria-hidden="true" /><span>Je n’aime pas cet article</span><ChevronRight className="article-menu-chevron" size={16} aria-hidden="true" /></button>}
          <button type="button" disabled={busy} onClick={() => choose(() => onOrganize(article))}><FolderPlus size={16} aria-hidden="true" />Ajouter à une collection…</button>
        </> : <>
          <button className="article-feedback-back" type="button" disabled={sending} onClick={() => { setStep(step === 'other' ? 'reasons' : 'actions'); setError(''); }}><ArrowLeft size={15} aria-hidden="true" />Retour</button>
          <p className="article-feedback-question">Qu’est-ce qui ne vous plaît pas ?</p>
          {step === 'reasons' ? <div aria-label="Raison de votre avis">{Object.entries(REASONS).map(([reason, label]) => <button type="button" key={reason} disabled={sending} onClick={() => reason === 'other' ? setStep('other') : sendReason(reason)}>{label}</button>)}</div> : <form className="article-feedback-other" onSubmit={event => { event.preventDefault(); sendReason('other'); }}>
            <label htmlFor={`${menuId}-comment`}>Autre raison <span>(facultatif)</span></label>
            <textarea id={`${menuId}-comment`} rows={3} maxLength={1000} disabled={sending} value={comment} onChange={event => setComment(event.target.value)} placeholder="Dites-nous en quelques mots…" />
            <button type="submit" disabled={sending}>Envoyer mon avis</button>
          </form>}
          {sending && <p className="article-feedback-status" role="status">Enregistrement…</p>}
          {error && <p className="article-feedback-error" role="alert">{error}</p>}
        </>}
      </div>}
    </div>
  </div>;
}
