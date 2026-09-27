# Kiosque — title card

Séquence de 8 secondes, 1920 × 1080, 60 images/seconde.

Le nom apparaît lettre par lettre, le point terracotta vient ponctuer la marque,
puis la typographie se repositionne pour révéler « Moins de bruit. Plus de découvertes. ».
Le dernier plan reste lisible environ trois secondes. Fond crème uniforme, police
Libre Caslon Display et couleurs de l’interface Kiosque.

- `Kiosque-title-card-8s.mp4` : version avec une signature sonore originale, sans voix.
- `Kiosque-title-card-8s-sans-son.mp4` : version silencieuse pour intégration à un montage.
- `Kiosque-title-card-apercu.png` : dernier plan, en pleine résolution.
- `storyboard.jpg` : six étapes de l’animation.
- `render.py` : source de rendu, nécessite Python, Pillow, NumPy, FFmpeg et Arial sur macOS.

La police Libre Caslon Display est fournie sous licence SIL Open Font License,
reproduite dans `assets/OFL.txt`. Le son est synthétisé dans le script, sans sample externe.

Reproduire les fichiers : `python render.py`.
