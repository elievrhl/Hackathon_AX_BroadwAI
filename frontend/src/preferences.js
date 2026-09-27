export const ACTIONS = { diversify: 'Découvrir aussi', more: 'Davantage de', less: 'Moins de', exclude: 'Ne plus proposer' };
export const TARGETS = { topic: 'Un sujet', treatment: 'Un style ou un angle', source: 'Une source', content_type: 'Un format', level: 'Un niveau' };
export const FORMATS = { news: 'Actualités', analysis: 'Analyses', tutorial: 'Tutoriels', opinion: 'Tribunes et opinions', research: 'Recherche', other: 'Autres formats' };
export const LEVELS = { beginner: 'Initiation', intermediate: 'Intermédiaire', expert: 'Expert' };
export const EMPTY_PREFERENCE = { action: 'diversify', target_kind: 'topic', target: '', explanation: '', scope: 'persistent' };
export const REASONS = { source: 'Je n’aime pas la source', topic: 'Le sujet ne m’intéresse pas', too_technical: 'Trop technique', too_basic: 'Trop simple', style: 'Je n’aime pas le style', other: 'Autre…' };
export function preferenceValue(value) {
  return Object.fromEntries(Object.keys(EMPTY_PREFERENCE).map(key => [key, value[key]]));
}
export function preferenceSummary(value) {
  const target = value.target_kind === 'content_type' ? FORMATS[value.target] : value.target_kind === 'level' ? LEVELS[value.target] : value.target;
  return `${ACTIONS[value.action]} : ${target || 'à préciser'}`;
}
export function impactText(action, size = 18) {
  const slots = Math.max(1, Math.ceil(size / 6));
  return {
    diversify: `Jusqu’à ${slots} places au total pour vos demandes de découverte, en conservant vos sujets habituels.`,
    more: 'Ces lectures seront favorisées, en conservant les autres intérêts et les critères de qualité.',
    less: `Ces lectures seront moins prioritaires et limitées à ${Math.max(1, Math.floor(size / 6))} articles par édition.`,
    exclude: 'Cette cible sera exclue, y compris des découvertes. Précisez les exceptions ci-dessous.',
  }[action];
}
