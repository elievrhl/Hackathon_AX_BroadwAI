import { useEffect, useId, useRef, useState } from 'react';
import { Bookmark, FolderPlus, MoreHorizontal } from 'lucide-react';

export default function ArticleSaveActions({ article, saved, busy, onSave, onOrganize, labelled = false }) {
  const [open, setOpen] = useState(false);
  const root = useRef(null);
  const trigger = useRef(null);
  const menuId = useId();
  useEffect(() => {
    if (!open) return;
    const outside = event => { if (!root.current?.contains(event.target)) setOpen(false); };
    document.addEventListener('pointerdown', outside);
    return () => document.removeEventListener('pointerdown', outside);
  }, [open]);
  const saveLabel = saved ? 'Retirer des articles sauvegardés et des collections' : 'Sauvegarder l’article';
  return <div className={`article-save-actions${labelled ? ' labelled' : ''}`}>
    <button type="button" className={`save-button ${saved ? 'is-saved' : ''} ${labelled ? 'save-labelled' : ''}`} disabled={busy}
      aria-label={`${saveLabel} : ${article.title}`} aria-pressed={saved} title={saveLabel} onClick={() => onSave(article)}>
      <Bookmark size={17} fill={saved ? 'currentColor' : 'none'} strokeWidth={1.5} aria-hidden="true" />
      {labelled && <span>{saved ? 'Sauvegardé' : 'Sauvegarder'}</span>}
    </button>
    <div className="article-more" ref={root} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }} onKeyDown={event => {
      if (event.key === 'Escape' && open) { event.preventDefault(); setOpen(false); trigger.current?.focus(); }
    }}>
      <button type="button" className="article-more-trigger" ref={trigger} disabled={busy} aria-expanded={open} aria-controls={menuId}
        aria-label={`Options de sauvegarde : ${article.title}`} title="Ajouter à une collection" onClick={() => setOpen(value => !value)}><MoreHorizontal size={19} aria-hidden="true" /></button>
      {open && <div className="article-more-menu" id={menuId}><button type="button" disabled={busy} onClick={() => { setOpen(false); trigger.current?.focus(); onOrganize(article); }}><FolderPlus size={16} aria-hidden="true" />Ajouter à une collection…</button></div>}
    </div>
  </div>;
}
