# Sources de Kiosque

Sélection et contrôles du **27 septembre 2026**, couvrant les **20 sujets proposés à l’inscription**, en français et en anglais.

## Consulter les sources sans lire de JSON

Ouvrir [l’annuaire dans le site](http://127.0.0.1:8010/admin/assets/sources.html) ou le fichier autonome [sources.html](sources.html), utilisable hors ligne. Le journal propose aussi un lien **Nos sources** dans son pied de page.

Recherche par nom ou sujet, filtres de langue, format, éditeur et état d’import ; cartes ou tableau, pagination et export CSV de la sélection affichée. Chaque fiche explique le choix éditorial, les limites, la provenance et la date du contrôle. Les compteurs de contenus se mettent à jour à l’ouverture quand le serveur est disponible.

## Bilan de la sélection

- **1 019 sources retenues  importées et avec du contenu**  dont **8 chaînes YouTube** et **6 émissions de podcasts**.
- **508 domaines éditeurs** ; les sous-domaines sont comptés séparément, les variantes `www` regroupées. Ce nombre ne représente pas des groupes de presse indépendants.
- **285 sources françaises et 734 anglaises**.
- **1389 candidats examinés** : 303 échecs techniques, 53 flux anciens, 13 doublons et une identité incorrecte restent documentés et sont exclus de l’export.
- Site local : **1031 sources au total**, dont 12 autres sources préexistantes ; **819 sources ajoutées dans cette seconde phase**.
- **6361 contenus distincts**, contre 2 873 avant l’extension, soit **3488 nouveaux contenus**. Les 342 fiches et 30 couvertures existantes sont inchangées par l’import.

Une source signifie ici un flux, une rubrique, une émission ou une chaîne. Plusieurs rubriques d’un même journal comptent séparément et peuvent partager des articles. La déduplication du collecteur se fait par URL d’article. Le compteur ne prétend donc pas représenter 1 019 médias indépendants.

## D’où viennent les podcasts ?

Les six émissions ont été sélectionnées manuellement dans le catalogue **Radio France**. Pour chacune, la page officielle contient un lien RSS qui correspond exactement à l’adresse finale du flux collecté. La preuve et la date sont conservées dans `provenance_verification`. Les titres, descriptions et liens audio viennent de ce flux. Aucun podcast n’a été inventé ou généré et aucun fichier audio n’a été téléchargé pour cette sélection.

| Émission | Producteur | Page de provenance |
|---|---|---|
| Le Cours de l'histoire — France Culture | Radio France · France Culture | [Page officielle](https://www.radiofrance.fr/franceculture/podcasts/le-cours-de-l-histoire) |
| Avec philosophie — France Culture | Radio France · France Culture | [Page officielle](https://www.radiofrance.fr/franceculture/podcasts/avec-philosophie) |
| La Science CQFD — France Culture | Radio France · France Culture | [Page officielle](https://www.radiofrance.fr/franceculture/podcasts/la-science-cqfd) |
| Les Pieds sur terre — France Culture | Radio France · France Culture | [Page officielle](https://www.radiofrance.fr/franceculture/podcasts/les-pieds-sur-terre) |
| On va déguster — France Inter | Radio France · France Inter | [Page officielle](https://www.radiofrance.fr/franceinter/podcasts/on-va-deguster) |
| Le Masque et la Plume — France Inter | Radio France · France Inter | [Page officielle](https://www.radiofrance.fr/franceinter/podcasts/le-masque-et-la-plume) |

## Les huit chaînes YouTube

Sélection fondée sur l’identité des auteurs ou producteurs, leur démarche pédagogique et les références consultables. La présentation officielle et deux descriptions récentes ont été examinées pour chaque chaîne ; les vidéos n’ont pas été visionnées intégralement. Les fiches détaillent les limites, notamment lorsque les descriptions ne donnent pas de bibliographie directe.

| Chaîne | Langue | Motif de sélection | Provenance |
|---|---|---|---|
| [Science Étonnante](https://www.youtube.com/channel/UCaNlbnghtwlsGF-KzAFThqA) | FR | David Louapre explique les mécanismes scientifiques avec des démonstrations progressives, des compléments écrits et du code consultable. | [Présentation officielle](https://scienceetonnante.com/) |
| [Le Réveilleur](https://www.youtube.com/channel/UC1EacOJoqsKaYxaDomTCTEQ) | FR | Analyses approfondies de l’énergie et du climat par Rodolphe Meyer, avec une démarche explicitement appuyée sur les travaux scientifiques. | [Présentation officielle](https://lereveilleur.com/qui-suis-je/) |
| [3Blue1Brown](https://www.youtube.com/channel/UCYO_jab_esuFRV4b17AJtAw) | EN | Les animations de Grant Sanderson rendent les raisonnements mathématiques vérifiables pas à pas ; le site propose aussi des leçons écrites et interactives. | [Présentation officielle](https://www.3blue1brown.com/about/) |
| [PBS Space Time](https://www.youtube.com/channel/UC7_gcs09iThXybpVgjHZ_7g) | EN | Physique et cosmologie en profondeur, dans une émission scientifique identifiée de PBS présentée par Matt O’Dowd. | [Présentation officielle](https://www.pbsspacetime.com/) |
| [Collège de France](https://www.youtube.com/channel/UCzZiy3EANVAx7h2XYqXsVbw) | FR | Cours et conférences donnés par des chercheurs, diffusés directement par le Collège de France : une porte d’entrée vers les travaux et leurs auteurs. | [Présentation officielle](https://www.college-de-france.fr/fr/le-college/diffusion-numerique-des-savoirs) |
| [Monsieur Phi](https://www.youtube.com/channel/UCqA8H22FwgBVcF3GJpp0MQw) | FR | Thibaut Giraud développe des arguments philosophiques et logiques, avec des compléments et références sur son blog. | [Présentation officielle](https://monsieurphi.com/a-propos/) |
| [Computerphile](https://www.youtube.com/channel/UC9-y-6csu5WGm29I7JiwpnA) | EN | Explications de concepts informatiques avec des intervenants identifiés, des exemples techniques et des démonstrations. | [Présentation officielle](https://www.bradyharanblog.com/projects) |
| [Le Vortex — ARTE](https://www.youtube.com/channel/UCZxLew-WXWm5dhRZBgEFl-Q) | FR | Une production de vulgarisation d’ARTE qui fait dialoguer plusieurs disciplines, avec une identité éditoriale et une production documentées. | [Présentation officielle](https://www.arte.tv/digitalproductions/le-vortex/) |

Kiosque collecte les titres et descriptions du flux YouTube et les liens vers les vidéos. Une description n’est pas une transcription. Les références académiques, prépublications, opinions, parrainages et passages de fiction doivent être distingués.

## Couverture des sujets

Une source transversale apparaît dans plusieurs lignes, tout en ne comptant qu’une fois dans les 1 019 sources.

| Sujet | Sources | Français | Anglais |
|---|---:|---:|---:|
| Tech & IA | 128 | 19 | 109 |
| Économie | 55 | 20 | 35 |
| Monde & société | 147 | 55 | 92 |
| Sciences | 135 | 21 | 114 |
| Climat & vivant | 75 | 21 | 54 |
| Culture & idées | 42 | 15 | 27 |
| Histoire | 53 | 21 | 32 |
| Philosophie | 38 | 17 | 21 |
| Livres & littérature | 58 | 19 | 39 |
| Cinéma & séries | 34 | 14 | 20 |
| Musique | 40 | 17 | 23 |
| Art & design | 56 | 15 | 41 |
| Santé & psychologie | 89 | 14 | 75 |
| Sport | 63 | 23 | 40 |
| Cuisine & gastronomie | 35 | 10 | 25 |
| Voyages & découvertes | 26 | 9 | 17 |
| Entrepreneuriat | 48 | 8 | 40 |
| Éducation | 41 | 18 | 23 |
| Jeux vidéo | 28 | 7 | 21 |
| Espace & astronomie | 35 | 10 | 25 |

## Fichiers et maintenance

| Fichier | Rôle |
|---|---|
| `sources.html` | Annuaire autonome lisible, avec tous les filtres et fiches. |
| `sources-all-topics.json` | Liste compatible avec `SourceInput` et `POST /v1/sources`, un objet par requête. Uniquement les entrées actives et vérifiées. |
| `source-catalog.json` | Catalogue éditorial et audit complet, y compris les candidats écartés. |
| `sources.json`, `sources-economy.json` | Anciens jeux de sources, conservés pour compatibilité. |

Les métadonnées de sujets, langues, éditeurs et provenance servent à l’annuaire. La base existante reçoit les champs d’import de `source` ; les articles collectés deviennent disponibles pour la sélection personnalisée du site.

### Importer sur une autre installation

Depuis la racine du dépôt, avec le serveur lancé :

```powershell
.\.venv\Scripts\python.exe -m scripts.import_source_catalog --base-url http://127.0.0.1:8010 --collect
```

Retirer `--collect` pour enregistrer uniquement les sources. Le script ne prend que les entrées déjà vérifiées. Les nouvelles sources utilisent leur limite documentée (cinq contenus pour les ajouts de cette extension). Les sources déjà remplies et les sources en pause sont conservées sans recollecte. Un nouvel appel reprend les sources enregistrées mais restées sans contenu. Aucun modèle n’est appelé.

Rapport progressif : `data/catalog-import.jsonl`. État final : `data/catalog-import.snapshot.json`. Bilan de cette installation : `data/sources-1000-summary.json`. Le dossier `data/` est local et ignoré par Git.

### Vérifier et reconstruire

```powershell
# Nouveaux candidats : verification.status = "pending".
.\.venv\Scripts\python.exe -m scripts.validate_source_catalog --pending-only
# Réessayer les échecs techniques et les flux anciens.
.\.venv\Scripts\python.exe -m scripts.validate_source_catalog --failed-only
# Refaire tous les contrôles techniques, puis le dédoublonnage.
.\.venv\Scripts\python.exe -m scripts.validate_source_catalog
# Export thématique, sans requête réseau.
.\.venv\Scripts\python.exe -m scripts.validate_source_catalog --export-only --topic history --topic philosophy --export data/sources-humanites.json
# Mettre à jour l’annuaire du site et sa copie HTML autonome.
.\.venv\Scripts\python.exe -m scripts.build_source_directory --base-url http://127.0.0.1:8010
```

Le contrôle utilise le téléchargeur et le parseur de production : TLS, restrictions réseau publiques, taille et durée bornées. Il relève le titre du flux, sa langue déclarée, des URL d’exemple et la dernière date observée. Les flux sans publication depuis plus de 365 jours, sans contenu exploitable ou dont l’identité change sont exclus. Pour un site HTML, au moins un article doit pouvoir être extrait.

Les redirections identiques, identités de flux identiques et échantillons de publications identiques permettent de repérer les alias. Ce contrôle ne garantit pas l’absence de recouvrement partiel entre rubriques. Les descriptions et langues sont éditoriales : certains flux déclarent une langue erronée ou servent plusieurs types de contenus. Une modification d’identité nécessite une revue avant réintégration.

Les annuaires publics de flux ont servi à découvrir des candidats, notamment [Awesome RSS Feeds](https://github.com/plenaryapp/awesome-rss-feeds). Ils ne sont pas des labels de qualité. Les preuves techniques proviennent des flux des éditeurs eux-mêmes ; les justifications et liens de provenance sont conservés dans chaque fiche.

L’accès au flux ne garantit pas l’accès au texte intégral. La sélection ne constitue pas une vérification factuelle de chaque publication. Les droits restent chez les éditeurs.
