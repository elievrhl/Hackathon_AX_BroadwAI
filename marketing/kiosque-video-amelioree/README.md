# Vidéo Kiosque — amélioration de la prise existante

Source : `WhatsApp Video 2026-09-27 at 19.12.44.mp4`, copiée sans modification dans `source.mp4`. L'original sur le Bureau n'est pas modifié.

## Livrables

- `Kiosque-video-amelioree-dynamique.mp4` : correction d'image, traitement de voix et léger rapprochement progressif de 3,5 %.
- `Kiosque-video-amelioree-cadrage-original.mp4` : même correction et même traitement de voix, avec le cadrage et les horodatages vidéo d'origine.

Le plan, les paroles, l'ordre temporel et la durée d'environ 5,43 secondes sont conservés. Aucun ajout de musique, de sous-titres, d'images générées ni de voix de remplacement. Les gestes et expressions restent ceux de la prise originale. La variante dynamique est exportée à 30 images/seconde, sans interpolation optique ; son arrondi de durée est inférieur à une image.

## Image

Réduction modérée du bruit de compression, légère neutralisation de la dominante colorée, contraste et saturation mesurés, accentuation douce des contours. Export 1920 × 1080 H.264 à faible perte.

La source WhatsApp ne contient que 1024 × 576 pixels. L'export en 1080p est une mise à l'échelle de qualité ; il ne recrée pas les détails perdus dans la compression et n'utilise aucune reconstruction générative du visage.

## Son

Voix originale conservée : coupe-bas à 75 Hz, atténuation légère du souffle, réduction des basses fréquences sourdes, présence vocale renforcée, compression douce et normalisation en deux passes vers −16 LUFS, avec plafond de crête cible de −1,5 dBTP. Export AAC 192 kbit/s, 48 kHz.

Le fichier `mesures-source.json` conserve les mesures et les chaînes de traitement. Le script `enhance.py` permet de reproduire les deux exports avec Python et FFmpeg.

Le délai de 25 ms introduit par le débruitage a été mesuré par corrélation avec la piste d'origine, puis compensé pour préserver la synchronisation labiale.
