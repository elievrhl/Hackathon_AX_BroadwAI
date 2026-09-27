# Kiosque — écran du laptop net

- `Kiosque-video-ecran-net.mp4` : version améliorée avec l'écran remplacé et le léger rapprochement de caméra de la version précédente.
- `Kiosque-laptop-net-cadrage-original.mp4` : même incrustation, cadrage fixe.
- `apercu-ecran-net.png` : aperçu complet.
- `comparaison-ecran.png` : écran avant / après pour contrôle.
- `kiosque-capture-nette.png` : capture réelle du journal utilisée dans l'écran.

Le contenu flou du laptop a été remplacé par une capture nette de Kiosque, issue de l'environnement local de démonstration, en thème Minimal sombre. Il s'agit d'une **incrustation d'écran**, pas d'une récupération des détails perdus de la vidéo WhatsApp. La disposition et la sélection d'articles de cette capture peuvent différer de la page filmée.

L'incrustation se limite à la surface active de l'écran. Elle suit les faibles déplacements de caméra par corrélation, est projetée en perspective et ajustée en luminosité. Le personnage, le décor, le cadre du laptop, son clavier, les paroles et la durée d'environ 5,43 secondes sont conservés. La piste sonore améliorée est copiée sans réencodage.

Les petits textes restent limités par la taille physique du laptop dans le plan large. Aucun visage ni texte d'article n'est généré par IA.

Sources : la vidéo améliorée du dossier voisin `kiosque-video-amelioree`, le frontend de démonstration existant et son édition déjà enregistrée `f9d9e52822dc49ab8b1226a79e9a4b26`.

`composite.py` contient le suivi et le montage ; `suivi-ecran.json` conserve les positions. `capture_server.py` sert une copie de démonstration, sans modifier les comptes ni l'application en cours. La capture PNG suffit à reproduire le montage, sans relancer ce serveur.
