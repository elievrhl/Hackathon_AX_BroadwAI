export function initialEditionId(linkedId, history, previousId) {
  return linkedId || history[0]?.id || previousId;
}

export function dailyEditionMessage(daily) {
  if (!daily) return 'Votre une sera bientôt disponible.';
  if (!daily.enabled) return 'La préparation quotidienne est momentanément indisponible.';
  if (daily.status === 'running') return 'Votre une du jour se prépare. Elle apparaîtra ici automatiquement.';
  if (daily.status === 'failed') return 'La une du jour n’a pas pu être préparée. La dernière édition reste disponible ; prochaine préparation à 4 h.';
  return 'Votre une est préparée automatiquement chaque jour à 4 h, heure de Paris.';
}
