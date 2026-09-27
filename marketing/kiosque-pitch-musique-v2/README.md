# Kiosque — Impulse

Composition instrumentale originale conçue pour le pitch `WhatsApp Video 2026-09-27 at 22.55.49.mp4`. Ambiance pop/funk légère et entraînante : basse syncopée, batterie électronique, claps, shakers, clavier électrique et cordes pincées synthétiques. Les sons et les motifs sont créés localement, sans sample musical externe.

## Fichiers

- `Kiosque-pitch-avec-musique.mp4` : vidéo complète avec la voix existante et la nouvelle musique mixée.
- `Kiosque-musique-calee-14s.wav` : piste musicale seule, déjà calée, avec 14 secondes de silence au début. Importer au début de la timeline, sans décalage supplémentaire. Durée : 74,48 secondes, stéréo, 48 kHz, PCM 24 bits.
- `Kiosque-musique-calee-14s.mp3` : même piste pour l'écoute ou le partage.
- `Kiosque-Impulse-musique-seule.wav` et `.mp3` : composition seule sans silence initial, d'une durée de 60,48 secondes. Si cette version est utilisée au montage, la placer à 14 secondes et régler son niveau sous la voix.

## Synchronisation

La musique entre à **14,00 s**, après le fondu au noir du clip initial et au début de la présentation face caméra. Son premier arrangement léger s'étoffe à **20,07 s**, au début de la narration du produit. Le tempo d'environ **118,63 BPM** fait arriver la carte finale à **66,60 s** sur une nouvelle mesure. La musique remonte alors doucement, puis se résout autour de la signature sonore E/B/E déjà présente, avant de s'éteindre en fin de vidéo.

La piste calée est abaissée pendant la parole par une compression commandée par la voix, avec une réduction supplémentaire de 2,5 dB autour du passage moins fort sur la bibliothèque (51–57 s). Les fréquences médiums du fond musical sont légèrement atténuées. Le niveau du son original est réduit de 3,5 dB pour laisser de la marge au mixage. Les paroles, leur rythme et leurs positions sont conservés. Les bruitages existants restent présents.

La piste vidéo est copiée sans réencodage : aucun changement d'image ou de montage. Les pistes musicales et le mix audio durent 74,48 secondes, comme le flux d'images. Les horodatages du flux vidéo original sont conservés. Le fichier original reste intact.

`composition.json` et `mixage.json` contiennent les mesures de niveau. `verification.json` vérifie le silence musical jusqu'à 14 secondes, l'identité du flux vidéo et le décodage complet. Les contrôles sont techniques ; la transcription automatique locale sert seulement à repérer la voix et n'est pas utilisée pour remplacer ou réécrire le son.

Production reproductible avec `compose.py`, `mix.py` et `verify.py` (NumPy et FFmpeg).
