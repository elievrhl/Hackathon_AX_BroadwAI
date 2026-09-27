export function initialEditionId(linkedId, history, previousId) {
  return linkedId || history[0]?.id || previousId;
}

export function dailyEditionRefreshMs(daily, hasCover = true) {
  return ['queued', 'running'].includes(daily?.status) || (!hasCover && daily?.status === 'ready') ? 2_500 : 60_000;
}

export function dailyEditionMessage(daily, hasCover = false) {
  if (!daily) return hasCover ? '' : 'Préparation de votre une…';
  if (!daily.enabled) return hasCover ? '' : 'La préparation de votre une est momentanément indisponible.';
  if (daily.status === 'queued') return hasCover ? '' : 'Préparation de votre première une… Elle apparaîtra ici automatiquement.';
  if (daily.status === 'running') return 'Votre une du jour se prépare. Elle apparaîtra ici automatiquement.';
  if (daily.status === 'failed') return hasCover
    ? 'La une du jour n’a pas pu être préparée. Votre dernière édition reste disponible.'
    : 'Votre une n’a pas pu être préparée. Veuillez revenir un peu plus tard.';
  return hasCover ? '' : 'Préparation de votre une…';
}
