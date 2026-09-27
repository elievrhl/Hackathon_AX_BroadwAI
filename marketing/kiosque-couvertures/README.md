# Kiosque — diversité des sujets

Plan de motion design de dix secondes : six couvertures illustrées défilent en carrousel, avec un bref arrêt sur chaque thème.

Thèmes : économie, sciences, culture, planète, technologies, voyage. Les illustrations sont créées avec l’outil intégré de génération d’images. La typographie et l’animation reprennent l’identité Kiosque : ivoire, Libre Caslon Display, accents terracotta.

Il s’agit de couvertures promotionnelles illustratives, pas d’une capture du fil réel ni d’articles publiés. Les prompts et les paramètres d’animation sont conservés avec les sources.

## Livrables

- `Kiosque-couvertures-10s.mp4` : plan de **10 secondes**, sans son, prêt à insérer dans le montage.
- `Kiosque-couvertures-10s-avec-musique.mp4` : même vidéo avec un extrait de la composition originale Kiosque créée précédemment.
- `apercu.png` : aperçu du plan.
- `storyboard.jpg` : les six temps du défilement.
- `couvertures/` : les six couvertures mises en page en PNG.
- `assets/` : les six illustrations générées, enregistrées dans ce projet.
- [prompts.json](prompts.json) : prompts finaux de génération, un par illustration. Outil utilisé : **image_gen intégré**, sans CLI.
- `generation-manifest.json` : correspondance entre les sorties générées et les fichiers du projet.
- `render.py` : animation et composition typographique reproductibles avec Pillow, NumPy et FFmpeg.

Format : horizontal **1920 × 1080, 60 images/s**, H.264, couleurs YUV 4:2:0. Le carrousel ralentit devant chaque couverture et s’arrête sur la dernière ; aucune image noire ni titre de fin n’est ajouté, pour faciliter l’insertion entre deux plans.
