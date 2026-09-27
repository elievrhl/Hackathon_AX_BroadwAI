import { useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Modal } from './components.jsx';
import { regenerationMessage, validRegenerationReason } from './regeneration.js';
import RegenerationProgress from './RegenerationProgress.jsx';
import './regeneration.css';

export default function RegenerateEdition({ busy, status, error, onSubmit, onClose }) {
  const [reason, setReason] = useState('');
  const preparing = busy || status?.status === 'running';
  return <Modal className="regeneration-dialog" labelId="regeneration-title" onClose={onClose}>
    <p className="eyebrow">UNE UNE QUI VOUS RESSEMBLE</p>
    <h2 id="regeneration-title">{preparing ? 'Votre une se prépare' : 'Refaire ma une'}</h2>
    <p className="regeneration-intro">{preparing ? 'Nous préparons une nouvelle sélection de lectures pour vous.' : 'Vous pouvez préciser ce qui vous manque pour guider cette nouvelle sélection et vos éditions des sept prochains jours, ou régénérer directement.'}</p>
    <form onSubmit={event => { event.preventDefault(); if (!busy && status?.available && validRegenerationReason(reason)) onSubmit(reason); }}>
      {!preparing && <><label className="field" htmlFor="regeneration-reason">Pourquoi souhaitez-vous une nouvelle une ? <span className="optional">Facultatif</span>
        <textarea id="regeneration-reason" autoFocus maxLength={1000} rows={5} value={reason} disabled={busy || !status?.available} onChange={event => setReason(event.target.value)} placeholder="Par exemple : trop d’articles sur l’IA, j’aimerais davantage de sciences et des analyses plus approfondies…" aria-describedby="regeneration-help" />
      </label>
      <p id="regeneration-help" className="field-help">Une seule tentative par jour, jusqu’à minuit (heure de Paris), même si la préparation échoue. Votre édition actuelle reste dans les archives.</p></>}
      {error && <p className="reader-error" role="alert">{error}</p>}
      {preparing ? <><RegenerationProgress status={status} /><p className="regeneration-status">Vous pouvez fermer cette fenêtre pendant la préparation.</p></> : !status?.available && <p className="regeneration-status" role="status">{regenerationMessage(status)}</p>}
      <div className="regeneration-actions">
        <button type="button" className="secondary-button" onClick={onClose}>{busy || !status?.available ? 'Fermer' : 'Annuler'}</button>
        <button type="submit" className="primary-button" disabled={busy || !status?.available || !validRegenerationReason(reason)}><RefreshCw size={16} aria-hidden="true" /> {busy ? 'Préparation…' : 'Régénérer ma une'}</button>
      </div>
    </form>
  </Modal>;
}
