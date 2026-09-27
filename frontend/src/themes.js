export const THEME_STORAGE_KEY = 'kiosque.theme.v1';
export const DEFAULT_THEME = 'editorial';
export const COLOR_MODE_STORAGE_KEY = 'kiosque.colorMode.v1';
export const DEFAULT_COLOR_MODE = 'auto';
export const SYSTEM_DARK_QUERY = '(prefers-color-scheme: dark)';
export const COLOR_MODES = [
  { id: 'light', name: 'Clair' },
  { id: 'dark', name: 'Sombre' },
  { id: 'auto', name: 'Auto' },
];

export const THEMES = [
  { id: 'editorial', name: 'Éditorial', mood: 'Le plaisir du papier', description: 'Crème, empattements et colonnes de journal. Le Kiosque original.' },
  { id: 'tech', name: 'Tech', mood: 'Après la prochaine idée', description: 'Accents menthe et caractères nets. Un esprit numérique.' },
  { id: 'finance', name: 'Finance', mood: 'Une longueur d’avance', description: 'Papier saumon, bleu encre et mise en page dense. Sobre et précis.' },
  { id: 'atelier', name: 'Atelier', mood: 'Un autre regard', description: 'Ivoire, bleu Klein et titres expressifs. Une composition de magazine.' },
  { id: 'minimal', name: 'Minimal', mood: 'L’essentiel, simplement', description: 'Blanc, noir et beaucoup d’espace. Une lecture calme et épurée.' },
  { id: 'playful', name: 'Playful', mood: 'La curiosité en couleurs', description: 'Lavande, violet et formes arrondies. Un journal à l’humeur légère.' },
];

export function normalizeTheme(value) {
  return THEMES.some(theme => theme.id === value) ? value : DEFAULT_THEME;
}

export function readTheme() {
  try { return normalizeTheme(JSON.parse(localStorage.getItem(THEME_STORAGE_KEY))); }
  catch { return DEFAULT_THEME; }
}

export function saveTheme(value) {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, JSON.stringify(normalizeTheme(value)));
    return true;
  } catch { return false; }
}

export function applyTheme(value) {
  document.documentElement.dataset.theme = normalizeTheme(value);
}

export function normalizeColorMode(value) {
  return COLOR_MODES.some(mode => mode.id === value) ? value : DEFAULT_COLOR_MODE;
}

export function readColorMode() {
  try { return normalizeColorMode(JSON.parse(localStorage.getItem(COLOR_MODE_STORAGE_KEY))); }
  catch { return DEFAULT_COLOR_MODE; }
}

export function saveColorMode(value) {
  try {
    localStorage.setItem(COLOR_MODE_STORAGE_KEY, JSON.stringify(normalizeColorMode(value)));
    return true;
  } catch { return false; }
}

export function resolveColorMode(value, systemDark) {
  const mode = normalizeColorMode(value);
  if (mode !== 'auto') return mode;
  return (systemDark ?? window.matchMedia(SYSTEM_DARK_QUERY).matches) ? 'dark' : 'light';
}

export function applyColorMode(value, systemDark) {
  const mode = normalizeColorMode(value);
  const resolved = resolveColorMode(mode, systemDark);
  document.documentElement.dataset.colorMode = mode;
  document.documentElement.dataset.colorScheme = resolved;
  return resolved;
}

export function watchColorMode(value, onChange) {
  const mode = normalizeColorMode(value);
  const media = mode === 'auto' ? window.matchMedia(SYSTEM_DARK_QUERY) : null;
  const update = () => onChange(applyColorMode(mode, media?.matches));
  update();
  media?.addEventListener('change', update);
  return () => media?.removeEventListener('change', update);
}
