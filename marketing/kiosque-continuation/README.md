# Kiosque — suite animée de 10 secondes

- `Kiosque-suite-animee-10s.mp4` : séquence autonome, 1920 × 1080, 30 images/seconde, H.264/AAC, avec ambiance sonore originale.
- `Kiosque-suite-animee-10s-sans-son.mp4` : même montage, sans piste audio, pour intégration au projet d'origine.
- `apercu.jpg` : aperçu du téléphone à 3 secondes.

À ajouter après la vidéo originale de 15 secondes. Le fichier `IMG_2833.MOV` ayant disparu de son ancien emplacement, cette livraison contient uniquement les 10 secondes supplémentaires.

## Nature des images

Montage de trois images photoréalistes avec travelling simulé, fondu d'ouverture de l'application, raccord vers le sourire puis title card animée. Les gestes et l'expression faciale ne sont pas animés comme dans un film. La ressemblance du personnage est reconstruite à partir des images conservées du clip ; elle n'est pas une reproduction garantie.

L'écran du téléphone est une adaptation illustrative générée à partir de la capture réelle de Kiosque. Le titre « Explorer le monde, à votre rythme. » est du texte publicitaire, pas un titre d'article réellement présent dans le produit.

Les images ont été créées avec le **générateur d'images intégré**, sans Runway ni API externe configurée par l'utilisateur. Les prompts exacts figurent dans `prompts-images.json`.

## Sources modifiables

- `plan-telephone-ouverture.png`
- `plan-telephone-journal.png`
- `plan-reaction.png`
- `render.py` : montage vidéo et son synthétisé, avec FFmpeg et Python/NumPy.
- La title card réutilise `../kiosque-title-card/Kiosque-title-card-8s-sans-son.mp4`, accélérée pour ce montage.

## Découpage

- 0–0,5 s : noir.
- 0,5–4,7 s : rapprochement sur le téléphone ; passage de l'écran d'ouverture au journal.
- 4,5–7,2 s : fondu vers le visage émerveillé, puis léger rapprochement.
- 6,9–10 s : transition vers la signature Kiosque et la promesse « Moins de bruit. Plus de découvertes. ».
