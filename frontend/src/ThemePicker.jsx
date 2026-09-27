import { createContext, useContext, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Check, Palette, Sun, Moon, Monitor } from 'lucide-react';
import { Modal } from './components.jsx';
import { THEMES, THEME_STORAGE_KEY, readTheme, saveTheme, applyTheme, COLOR_MODES, COLOR_MODE_STORAGE_KEY, readColorMode, saveColorMode, resolveColorMode, watchColorMode } from './themes.js';

const ThemeContext = createContext(null);
const MODE_ICONS = { light: Sun, dark: Moon, auto: Monitor };

export function ThemeButton() {
  const { theme, openPicker } = useContext(ThemeContext);
  return <button type="button" className="theme-button" onClick={openPicker} aria-haspopup="dialog" aria-label={`Changer de thème, thème actuel : ${THEMES.find(item => item.id === theme).name}`}>
    <Palette size={16} aria-hidden="true" /><span>Thèmes</span><span className="theme-current-dot" aria-hidden="true" />
  </button>;
}

function ThemePreview({ theme, colorScheme }) {
  return <span className="theme-preview" data-preview={theme.id} data-color-scheme={colorScheme} aria-hidden="true">
    <span className="theme-preview-masthead">Kiosque<span>.</span><i>01 / LE JOURNAL</i></span>
    <span className="theme-preview-columns"><span><strong>{theme.mood}</strong><span className="theme-preview-lines" /></span><span className="theme-preview-art"><i /><i /></span></span>
    <span className="theme-preview-bottom"><i /><i /><i /></span>
  </span>;
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(readTheme);
  const [colorMode, setColorMode] = useState(readColorMode);
  const [colorScheme, setColorScheme] = useState(() => resolveColorMode(colorMode));
  const [open, setOpen] = useState(false);
  const [persisted, setPersisted] = useState(true);
  const [modePersisted, setModePersisted] = useState(true);
  const opener = useRef(null);
  useLayoutEffect(() => watchColorMode(colorMode, setColorScheme), [colorMode]);
  useEffect(() => {
    if (!open && opener.current) {
      opener.current.focus();
      opener.current = null;
    }
  }, [open]);
  useEffect(() => {
    function sync(event) {
      if (event.key === THEME_STORAGE_KEY || event.key === null) {
        const next = readTheme();
        applyTheme(next);
        setTheme(next);
        setPersisted(true);
      }
      if (event.key === COLOR_MODE_STORAGE_KEY || event.key === null) {
        setColorMode(readColorMode());
        setModePersisted(true);
      }
    }
    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, []);

  function choose(next) {
    applyTheme(next);
    setTheme(next);
    setPersisted(saveTheme(next));
  }

  function chooseColorMode(next) {
    setColorMode(next);
    setModePersisted(saveColorMode(next));
  }

  return <ThemeContext.Provider value={{ theme, openPicker: event => { opener.current = event.currentTarget; setOpen(true); } }}>
    {children}
    {open && <Modal className="theme-dialog" labelId="theme-title" onClose={() => setOpen(false)}>
      <div className="theme-heading"><p className="eyebrow"><Palette size={15} aria-hidden="true" /> À CHACUN SON KIOSQUE</p><h2 id="theme-title">Changez de décor.</h2><p>Six ambiances pour lire à votre façon. Choisissez, le journal s’habille aussitôt.</p></div>
      <div className="color-mode-settings">
        <div><h3>Apparence</h3><p id="color-mode-help" role="status">{colorMode === 'auto' ? `Suit votre système · actuellement ${colorScheme === 'dark' ? 'sombre' : 'clair'}.` : 'S’applique à tous les thèmes.'}</p></div>
        <fieldset className="color-mode-options" aria-describedby="color-mode-help"><legend className="sr-only">Mode d’affichage</legend>
          {COLOR_MODES.map(mode => {
            const Icon = MODE_ICONS[mode.id];
            return <label key={mode.id} className={`color-mode-option${colorMode === mode.id ? ' is-selected' : ''}`}>
              <input className="sr-only" type="radio" name="kiosque-color-mode" value={mode.id} checked={colorMode === mode.id} onChange={() => chooseColorMode(mode.id)} />
              <Icon size={16} aria-hidden="true" /><span>{mode.name}</span>
            </label>;
          })}
        </fieldset>
      </div>
      <fieldset className="theme-options"><legend className="sr-only">Choisir l’apparence de Kiosque</legend>
        {THEMES.map(item => <label className={`theme-option${theme === item.id ? ' is-selected' : ''}`} key={item.id}>
          <input className="sr-only" type="radio" name="kiosque-theme" value={item.id} checked={theme === item.id} onChange={() => choose(item.id)} aria-label={item.name} aria-describedby={`theme-description-${item.id}`} />
          <ThemePreview theme={item} colorScheme={colorScheme} />
          <span className="theme-option-name"><strong>{item.name}</strong><span className="theme-option-check" aria-hidden="true">{theme === item.id && <Check size={14} />}</span></span>
          <span className="theme-option-description" id={`theme-description-${item.id}`}>{item.description}</span>
        </label>)}
      </fieldset>
      <div className="theme-picker-footer"><p role="status">{persisted && modePersisted ? <><strong>{THEMES.find(item => item.id === theme).name}</strong> · Choix conservés dans ce navigateur.</> : 'Apparence appliquée pour cette visite. Le navigateur ne permet pas de mémoriser tous vos choix.'}</p><button type="button" className="primary-button" onClick={() => setOpen(false)}>C’est mon style <Check size={16} aria-hidden="true" /></button></div>
    </Modal>}
  </ThemeContext.Provider>;
}
