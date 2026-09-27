# Sources de Kiosque

Sélection et contrôles du **27 septembre 2026**, couvrant les **20 sujets proposés à l’inscription**, en français et en anglais.

## Consulter les sources sans lire de JSON

Ouvrir [l’annuaire dans le site](http://127.0.0.1:8010/admin/assets/sources.html) ou le fichier autonome [sources.html](sources.html), utilisable hors ligne. Le journal propose aussi un lien **Nos sources** dans son pied de page.

Recherche par nom ou sujet, filtres de langue, format, éditeur et état d’import ; cartes ou tableau, pagination et export CSV de la sélection affichée. Chaque fiche explique le choix éditorial, les limites, la provenance et la date du contrôle. Les compteurs de contenus se mettent à jour à l’ouverture quand le serveur est disponible.

## Bilan de la sélection

- **1 211 sources retenues, importées et avec du contenu**, dont **200 chaînes YouTube** et **6 émissions de podcasts**.
- **508 domaines éditeurs** ; les sous-domaines sont comptés séparément, les variantes `www` regroupées. Ce nombre ne représente pas des groupes de presse indépendants.
- **350 sources avec des contenus en français et 867 en anglais**, dont 6 bilingues.
- **1583 candidats dans le catalogue** : 303 échecs techniques, 55 flux anciens, 13 doublons et une identité incorrecte restent documentés et sont exclus de l’export.
- Site local : **1223 sources au total**, dont 12 autres sources préexistantes.
- Dernière extension : **172 chaînes YouTube ajoutées**, avec cinq publications collectées pour chacune, sans erreur de collecte. Elles sont issues de **344 pistes YouTube examinées**, conservées séparément dans `youtube-research-audit.json`.
- La sélection YouTube compte **70 chaînes avec du français et 136 avec de l’anglais**, dont 6 bilingues.
- **7 429 contenus distincts** présents au moment du relevé ; ce compteur peut évoluer avec les autres collectes du site.

Une source signifie ici un flux, une rubrique, une émission ou une chaîne. Plusieurs rubriques d’un même journal comptent séparément et peuvent partager des articles. La déduplication du collecteur se fait par URL d’article. Le compteur ne prétend donc pas représenter 1 211 médias indépendants.

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

## Les 200 chaînes YouTube

[Consulter les 200 chaînes dans l’annuaire](http://127.0.0.1:8010/admin/assets/sources.html?format=youtube) ou [lire la liste complète avec sujets et motifs de sélection](YOUTUBE.md).

La sélection privilégie cours universitaires, organismes de recherche, musées, rédactions spécialisées et créateurs documentant leur démarche. Pour chacun des 172 nouveaux ajouts, le site officiel renvoie à la chaîne ; son identifiant, son titre de flux, ses dates et ses descriptions sont contrôlés. Les pistes dont l’identité ne correspond pas, les doublons et les flux inactifs ne sont pas ajoutés pour atteindre le quota.

La revue documentaire porte sur la présentation officielle, les titres et des extraits de descriptions, avec deux exemples par chaîne. **Les vidéos n’ont pas été visionnées intégralement et toutes les références citées n’ont pas été auditées.** L’annuaire montre désormais ce périmètre dans les fiches, avec les raisons de sélection et les limites.

Deux archives supplémentaires restent consultables avec le filtre **Sources écartées** : Le Mock, pour la littérature (dernière publication du flux : novembre 2021), et Hygiène Mentale, pour l’esprit critique (mai 2025). Elles ne comptent pas dans les 200 chaînes actives.

Certaines chaînes relèvent du même organisme : NASA et NASA Goddard, par exemple. Heu?reka et Stupid Economics diffusent des émissions communes d’Argent Magique. Compter des chaînes ne revient pas à compter autant de producteurs ou d’analyses indépendants. David Bennett Piano apparaît sous son nom actuel **David Bennett Music Theory** ; iBiology est diffusé sur la chaîne **Science Communication Lab**.

Kiosque collecte les titres et descriptions du flux YouTube et les liens vers les vidéos. Une description n’est pas une transcription. Les références académiques, prépublications, opinions, parrainages et passages de fiction doivent être distingués.

## Couverture des sujets

Une source transversale apparaît dans plusieurs lignes, tout en ne comptant qu’une fois dans les 1 211 sources. Les colonnes de langue se recouvrent pour les chaînes bilingues.

| Sujet | Sources | Français | Anglais |
|---|---:|---:|---:|
| Tech & IA | 170 | 25 | 146 |
| Économie | 85 | 32 | 54 |
| Monde & société | 182 | 75 | 109 |
| Sciences | 236 | 55 | 186 |
| Climat & vivant | 108 | 33 | 75 |
| Culture & idées | 79 | 34 | 45 |
| Histoire | 100 | 43 | 58 |
| Philosophie | 48 | 20 | 29 |
| Livres & littérature | 62 | 22 | 40 |
| Cinéma & séries | 41 | 16 | 25 |
| Musique | 56 | 21 | 35 |
| Art & design | 80 | 22 | 58 |
| Santé & psychologie | 100 | 21 | 79 |
| Sport | 64 | 24 | 40 |
| Cuisine & gastronomie | 40 | 11 | 29 |
| Voyages & découvertes | 31 | 9 | 22 |
| Entrepreneuriat | 52 | 8 | 44 |
| Éducation | 98 | 36 | 67 |
| Jeux vidéo | 34 | 7 | 27 |
| Espace & astronomie | 49 | 11 | 38 |


## Fichiers et maintenance

| Fichier | Rôle |
|---|---|
| `sources.html` | Annuaire autonome lisible, avec tous les filtres et fiches. |
| `sources-all-topics.json` | Liste compatible avec `SourceInput` et `POST /v1/sources`, un objet par requête. Uniquement les entrées actives et vérifiées. |
| `sources-youtube.json` | Les 200 chaînes actives, au même format d’import API. |
| `YOUTUBE.md` | Liste lisible des 200 chaînes, avec sujets, motifs et provenance. |
| `youtube-research-audit.json` | Les 344 pistes examinées pour cette extension et leur décision de sélection. |
| `source-catalog.json` | Catalogue éditorial et audit complet, y compris les candidats écartés. |
| `sources.json`, `sources-economy.json` | Anciens jeux de sources, conservés pour compatibilité. |

Les métadonnées de sujets, langues, éditeurs et provenance servent à l’annuaire. La base existante reçoit les champs d’import de `source` ; les articles collectés deviennent disponibles pour la sélection personnalisée du site.

### Importer sur une autre installation

Depuis la racine du dépôt, avec le serveur lancé :

```powershell
.\.venv\Scripts\python.exe -m scripts.import_source_catalog --base-url http://127.0.0.1:8010 --collect
```

Retirer `--collect` pour enregistrer uniquement les sources. Le script ne prend que les entrées déjà vérifiées. Les nouvelles sources visent 50 contenus par collecte, selon les disponibilités du flux ou du site, y compris les chaînes vidéo. Les sources déjà remplies et les sources en pause sont conservées sans recollecte. Un nouvel appel reprend les sources enregistrées mais restées sans contenu. Aucun modèle n’est appelé.

Rapport progressif : `data/catalog-import.jsonl`. État final : `data/catalog-import.snapshot.json`. Bilan de cette installation : `data/sources-1000-summary.json`. Extension vers 200 chaînes : `data/youtube200/summary.json` et `data/youtube200/import.jsonl`. Le précédent relevé à 28 chaînes reste dans `data/youtube-expansion-summary.json`. Le dossier `data/` est local et ignoré par Git.

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
