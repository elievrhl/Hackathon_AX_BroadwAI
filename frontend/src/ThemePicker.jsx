import { createContext, useContext, useEffect, useRef, useState } from 'react';
import { Check, Palette } from 'lucide-react';
import { Modal } from './components.jsx';
import { THEMES, THEME_STORAGE_KEY, readTheme, saveTheme, applyTheme } from './themes.js';

const ThemeContext = createContext(null);

export function ThemeButton() {
  const { theme, openPicker } = useContext(ThemeContext);
  return <button type="button" className="theme-button" onClick={openPicker} aria-haspopup="dialog" aria-label={`Changer de thème, thème actuel : ${THEMES.find(item => item.id === theme).name}`}>
    <Palette size={16} aria-hidden="true" /><span>Thèmes</span><span className="theme-current-dot" aria-hidden="true" />
  </button>;
}

function ThemePreview({ theme }) {
  return <span className="theme-preview" data-preview={theme.id} aria-hidden="true">
    <span className="theme-preview-masthead">Kiosque<span>.</span><i>01 / LE JOURNAL</i></span>
    <span className="theme-preview-columns"><span><strong>{theme.mood}</strong><span className="theme-preview-lines" /></span><span className="theme-preview-art"><i /><i /></span></span>
    <span className="theme-preview-bottom"><i /><i /><i /></span>
  </span>;
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(readTheme);
  const [open, setOpen] = useState(false);
  const [persisted, setPersisted] = useState(true);
  const opener = useRef(null);
  useEffect(() => {
    if (!open && opener.current) {
      opener.current.focus();
      opener.current = null;
    }
  }, [open]);
  useEffect(() => {
    function sync(event) {
      if (event.key !== THEME_STORAGE_KEY && event.key !== null) return;
      const next = readTheme();
      applyTheme(next);
      setTheme(next);
      setPersisted(true);
    }
    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, []);

  function choose(next) {
    applyTheme(next);
    setTheme(next);
    setPersisted(saveTheme(next));
  }

  return <ThemeContext.Provider value={{ theme, openPicker: event => { opener.current = event.currentTarget; setOpen(true); } }}>
    {children}
    {open && <Modal className="theme-dialog" labelId="theme-title" onClose={() => setOpen(false)}>
      <div className="theme-heading"><p className="eyebrow"><Palette size={15} aria-hidden="true" /> À CHACUN SON KIOSQUE</p><h2 id="theme-title">Changez de décor.</h2><p>Six ambiances pour lire à votre façon. Choisissez, le journal s’habille aussitôt.</p></div>
      <fieldset className="theme-options"><legend className="sr-only">Choisir l’apparence de Kiosque</legend>
        {THEMES.map(item => <label className={`theme-option${theme === item.id ? ' is-selected' : ''}`} key={item.id}>
          <input className="sr-only" type="radio" name="kiosque-theme" value={item.id} checked={theme === item.id} onChange={() => choose(item.id)} aria-label={item.name} aria-describedby={`theme-description-${item.id}`} />
          <ThemePreview theme={item} />
          <span className="theme-option-name"><strong>{item.name}</strong><span className="theme-option-check" aria-hidden="true">{theme === item.id && <Check size={14} />}</span></span>
          <span className="theme-option-description" id={`theme-description-${item.id}`}>{item.description}</span>
        </label>)}
      </fieldset>
      <div className="theme-picker-footer"><p role="status">{persisted ? <><strong>{THEMES.find(item => item.id === theme).name}</strong> · Choix conservé dans ce navigateur.</> : 'Thème appliqué pour cette visite. Le navigateur ne permet pas de mémoriser votre choix.'}</p><button type="button" className="primary-button" onClick={() => setOpen(false)}>C’est mon style <Check size={16} aria-hidden="true" /></button></div>
    </Modal>}
  </ThemeContext.Provider>;
}
