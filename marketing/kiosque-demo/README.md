# Kiosque — démo marketing

Vidéo en français de **120 secondes**, format **1920 × 1080**, 24 images/seconde.
Voix de synthèse française (Thomas, macOS), sous-titres incrustés et fond musical original discret.

## Livrables

- `Kiosque-demo-marketing-2min.mp4` : vidéo H.264/AAC prête à présenter.
- `apercu.jpg` : visuel d’aperçu.
- `script-voix-off.md` : narration et déroulé minuté.
- `sous-titres.srt` : sous-titres séparés.
- `voix-off.wav` : narration seule, sans musique.
- `storyboard.jpg` : vue d’ensemble du montage.

## Captures et périmètre

Les captures montrent l’interface React du dépôt, compilée le 27 septembre 2026 et servie dans un environnement de tournage local isolé. L’édition complète utilisée est une édition réellement enregistrée : « Jeux vidéo, climat, monde : une sélection de design, de crises et d’idées », identifiant `f9d9e52822dc49ab8b1226a79e9a4b26`, 16 articles et 2 vidéos.

La vidéo est un montage animé de captures, avec gros plans et changements de vue. Elle ne présente pas une génération en temps réel : la mention « Édition déjà préparée » apparaît dans le montage. Le message du Courrier du lecteur est montré comme un exemple de demande, à l’état de brouillon ; aucune réponse n’est simulée. La sauvegarde est jouée dans une mémoire de démonstration distincte des comptes réels. Aucune nouvelle édition ou conversation IA n’a été générée pour ce tournage.

Les fichiers applicatifs n’ont pas été modifiés par la réalisation de cette vidéo. Les articles, titres et visuels restent ceux de leurs éditeurs respectifs.

## Reproduire le montage

`build_video.py` utilise Pillow, NumPy, FFmpeg et la commande macOS `say` avec la voix Thomas. `scenes.json` contient les textes et durées ; `assets/` contient les captures. Les fichiers de travail sont placés dans `/private/tmp/kiosque-marketing/render`.

```sh
python3 build_video.py --audio
python3 build_video.py --preview --render
```

Après une modification de la narration, supprimer le fichier `voice-XX-YY.wav` correspondant dans le dossier de travail avant de relancer `--audio`, afin de renouveler ce segment vocal.
