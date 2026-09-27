export const THEME_STORAGE_KEY = 'kiosque.theme.v1';
export const DEFAULT_THEME = 'editorial';

export const THEMES = [
  { id: 'editorial', name: 'Éditorial', mood: 'Le plaisir du papier', description: 'Crème, empattements et colonnes de journal. Le Kiosque original.' },
  { id: 'tech', name: 'Tech', mood: 'Après la prochaine idée', description: 'Fond nuit, accents menthe et caractères nets. Un esprit numérique.' },
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
