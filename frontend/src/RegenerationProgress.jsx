import { useEffect, useState } from 'react';
import { regenerationProgress } from './regeneration.js';

export default function RegenerationProgress({ status }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    setNow(Date.now());
    if (status?.status !== 'running') return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [status]);
  const progress = regenerationProgress(status, now);
  return <section className="regeneration-progress" aria-label="Préparation de votre nouvelle une">
    <div className="regeneration-progress-heading"><strong>{status?.status === 'completed' ? 'Une prête' : 'Préparation de votre nouvelle une'}</strong><span>{progress.percent} %</span></div>
    <progress max="100" value={progress.percent} aria-label="Progression estimée de la régénération" aria-valuetext={`${progress.percent} %. ${progress.label}`} />
    <p>{progress.label}</p>
  </section>;
}
