# Kiosque — motion design de 12 secondes

Vidéo autonome, conçue dans la continuité de la title card Kiosque : papier crème, Libre Caslon Display, accents terre cuite et mouvements souples.

- **Kiosque-motion-design-12s.mp4** — 1920 × 1080, 60 images/seconde, H.264/AAC, avec ambiance sonore originale.
- **Kiosque-motion-design-12s-sans-son.mp4** — même animation sans audio, pour montage.
- **apercu.png** — image du téléphone en suspension.
- **storyboard.jpg** — neuf points de contrôle de la séquence.
- **render.py** — source modifiable et reproductible avec Pillow, NumPy et FFmpeg.

## Déroulé

1. 0–4,6 s : les cartes d'articles arrivent, tournent et s'alignent dans une page de journal. « Vos curiosités. Votre journal. »
2. 4,05–8,88 s : téléphone en suspension, rotation en perspective, déplacement vertical léger et défilement de sa sélection. « Votre journal. À votre rythme. »
3. 8,5–12 s : signature Kiosque, puis « Moins de bruit. Plus de découvertes. »

Les chevauchements indiquent les transitions. Le son est synthétisé pour cette vidéo, sans échantillon musical externe.

## Sources visuelles

Les trois images éditoriales viennent de la capture existante `../kiosque-demo/assets/03-une.png`. La mise en page du journal, l'interface mobile et les titres courts sont des compositions promotionnelles illustratives, pas un enregistrement de navigation dans le produit. Le téléphone, les textes et toutes les animations sont dessinés et calculés localement ; aucun service de génération vidéo n'est nécessaire.

La séquence finale réutilise le code de la title card existante dans `../kiosque-title-card/render.py`, avec un rythme adapté. La police Libre Caslon Display et sa licence OFL restent dans le dossier de cette title card.

## Reproduction

Avec Python contenant Pillow et NumPy, et FFmpeg dans le PATH :

```sh
python render.py --preview
python render.py
```

Les anciens livrables de démonstration et de title card ne sont pas modifiés.
