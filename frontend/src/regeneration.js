export const validRegenerationReason = reason => reason.length <= 1000 && (!reason.trim() || (reason.trim().length >= 2 && /[\p{L}\p{N}]/u.test(reason)));

export function regenerationProgress(status, now = Date.now()) {
  const estimate = Math.max(1, Number(status?.estimated_seconds) || 120);
  // elapsed_seconds comes from the server, so a reader's clock cannot skew the ETA.
  const sinceUpdate = Math.max(0, (now - (status?.receivedAt ?? now)) / 1000);
  const elapsed = Math.max(0, Number(status?.elapsed_seconds) || 0) + (status?.status === 'running' ? sinceUpdate : 0);
  const completed = status?.status === 'completed';
  const remaining = Math.max(0, Math.ceil((estimate - elapsed) / 10) * 10);
  const minutes = Math.floor(remaining / 60), seconds = remaining % 60;
  const time = minutes ? `${minutes} min${seconds ? ` ${seconds} s` : ''}` : `${seconds} s`;
  return {
    percent: completed ? 100 : Math.min(95, Math.floor(elapsed / estimate * 95)),
    label: completed ? 'Votre nouvelle une est prête.' : remaining > 0 ? `Temps restant estimé : environ ${time}` : 'La préparation prend plus de temps que prévu. Elle se poursuit…',
    elapsed: Math.floor(elapsed),
  };
}

export function regenerationMessage(state) {
  if (!state) return 'Vérification de la régénération…';
  if (state.status === 'unavailable') return 'La régénération est momentanément indisponible.';
  if (state.status === 'running') return 'Votre nouvelle une se prépare. Elle apparaîtra ici automatiquement.';
  if (state.status === 'failed') return 'La régénération n’a pas abouti. Votre dernière édition reste disponible. Nouvelle tentative possible demain.';
  if (!state.available) return 'Régénération du jour utilisée. Disponible demain à partir de minuit, heure de Paris.';
  return '';
}
