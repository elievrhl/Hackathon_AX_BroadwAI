# Kiosque — scroll de la page principale

Plan de **8 secondes**, horizontal **1920 × 1080 à 60 images/s** : départ sur la une, courte accélération douce, puis défilement vertical continu. Le plan se coupe pendant le mouvement, sans jamais montrer le bas du fil ni le pied de page.

## Livrables

- `Kiosque-main-page-scroll-8s.mp4` : vidéo sans son, prête à insérer dans le montage.
- `Kiosque-main-page-scroll-8s-avec-musique.mp4` : le même plan avec la composition Kiosque créée précédemment.
- `apercu.png` : première image du plan.
- `storyboard.jpg` : quatre étapes du défilement.

## Interface et contenu

La capture utilise une compilation du **vrai frontend Kiosque**, dans son thème Éditorial clair. L’application et les comptes existants ne sont pas modifiés. Un serveur de démonstration isolé fournit 24 contenus fictifs : économie, sciences, culture, climat, technologies et voyages, présentés en articles, vidéos et podcasts. Les titres et les noms de programmes sont des exemples pour la vidéo, pas des publications vérifiées.

Les illustrations réutilisent les visuels générés pour le plan de couvertures précédent. Aucun site de presse n’est contacté. La police Libre Caslon Display est chargée localement ; la pile de remplacement du produit est utilisée pour les textes sans empattements.

La page réelle est capturée entièrement dans un navigateur temporaire. Le mouvement est ensuite rendu à 60 images/s avec une translation précise de cette capture, ce qui évite les saccades d’un enregistrement en temps réel. Aucun élément visible de l’interface n’a besoin de rester fixe lors du scroll. Un curseur discret accompagne le geste dans la marge droite.

`capture-metadata.json` et `scroll-verification.json` documentent la hauteur réelle de la page et la marge de contenu restant sous la dernière image. Le pied de page reste à plus de 300 pixels CSS sous l’écran à tout instant. Il n’y a ni chargement infini ajouté au produit, ni modification de son comportement de fin de fil.

Sources : `prepare.py`, `edition-demo.json`, `server.py`, `capture.mjs`, `render.py`. Le dossier `site/` contient la compilation utilisée pour le tournage, et `page-complete.png` conserve la capture nécessaire à la reproduction du rendu.
