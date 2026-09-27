# Kiosque — Curiosité

Composition instrumentale originale créée pour accompagner le pitch marketing de Kiosque. Clavier électrique doux, accords étendus, notes cristallines espacées, basse ronde et percussions légères. Tous les sons sont synthétisés localement ; aucun extrait musical ni sample externe n’est utilisé.

## Fichiers

- `Kiosque-musique-fond.mp3` : musique seule, prête à écouter et à partager.
- `Kiosque-musique-fond.wav` : musique seule pour le montage, stéréo, 48 kHz, PCM 24 bits.
- `Kiosque-pitch-avec-musique.mp3` : aperçu avec la voix Valentin de Gradium, générée précédemment pour le script fourni.
- `Kiosque-pitch-avec-musique.wav` : le même mix en WAV pour le montage.

Durée : **1 min 03,84 s**, identique à la narration existante. Tempo : **96 BPM**, mesure à quatre temps. Tonalité : sol majeur. La piste musicale seule est réglée à **−18 LUFS**.

## Construction

- **0–10 s** : installation du clavier, de la nappe et du motif.
- **10–20 s** : arrivée d’une pulsation légère.
- **20–50 s** : arrangement complet, petites variations de motif et de rythme.
- **50–60 s** : allègement progressif pour la conclusion.
- **60–63,84 s** : résolution harmonique et extinction douce.

La musique laisse de l’espace à la parole. Dans le mix fourni, son volume est réduit et s’abaisse légèrement lorsque la voix parle. La narration conserve son texte et ses positions temporelles ; ses fichiers d’origine ne sont pas modifiés.

`compose.py` contient les notes, l’arrangement, la synthèse et le mixage. Il utilise NumPy et FFmpeg. `sources/` conserve les rendus de travail. `verification.json` contient les mesures de durée et de niveau sonore. Les contrôles effectués sont techniques ; le choix final de l’ambiance reste à apprécier à l’écoute.
