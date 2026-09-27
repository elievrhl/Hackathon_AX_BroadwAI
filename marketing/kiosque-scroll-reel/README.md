# Kiosque — scroll avec les vrais articles

Plan de 8 secondes, 1920 × 1080, 60 images/s. Courte pause sur la une, accélération douce, puis défilement continu. Le plan coupe pendant le mouvement, bien avant le pied de page.

- `Kiosque-vrais-articles-scroll-8s.mp4` : version sans son pour le montage.
- `Kiosque-vrais-articles-scroll-8s-avec-musique.mp4` : même plan avec la musique Kiosque composée précédemment.
- `storyboard.jpg` et `apercu.png` : aperçus.

Le plan utilise la véritable interface Kiosque, en thème Éditorial clair, et une sélection de 24 contenus réels provenant d'éditions déjà présentes dans la base locale : 20 articles, une vidéo et trois podcasts. Les titres, les liens, les sources et les images proviennent de ces enregistrements. Les rubriques et l'ordre de présentation sont préparés pour le tournage afin de montrer six thèmes : sciences, économie, culture, climat, tech et jeux vidéo. Le titre de l'édition est une accroche de présentation.

Chaque contenu a son propre visuel, récupéré à l'URL enregistrée par Kiosque ou dans le cache local précédent lorsque l'URL correspondait. Les six couvertures générées ne sont pas utilisées. `images-reelles.json` conserve la provenance, le format et les dimensions de chaque image. Les illustrations restent celles des publications, sans retouche. Certains articles sont en anglais, comme sur le site.

Le serveur de tournage utilise un compte de démonstration isolé et une copie du frontend compilé. Aucun compte réel ni aucune donnée du produit n'est modifié. Le navigateur temporaire ne contacte que ce serveur local. Les polices utilisent Libre Caslon Display localement et la pile de remplacement sans empattements du produit.

Le mouvement est rendu par translation à précision sous-pixel de la capture complète de la vraie page. Les images sont chargées avant la capture ; le défilement final est comparé avec une capture du navigateur réellement défilé. Un curseur discret reste dans la marge. Le fil conserve sa fin normale, qui reste hors champ.

Sources de production : `prepare.py`, `server.py`, `capture.mjs`, `render.py`. Les fichiers `capture-metadata.json`, `scroll-verification.json` et `verification-export.json` documentent les vérifications du rendu.
