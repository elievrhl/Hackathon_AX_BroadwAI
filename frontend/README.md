# Kiosque — interface lecteur connectée

React 19 / Vite 7, API FastAPI et PostgreSQL. Comptes côté serveur avec connexion uniquement
par e-mail et mot de passe, sessions par cookie et préférences synchronisées.
Voir [la configuration de l’authentification](../AUTHENTICATION.md).

## Lancer

Démarrer PostgreSQL et le backend sur le port 8010 depuis la racine du projet :

```powershell
.\.venv\Scripts\python.exe -m uvicorn broadwai.api:app --host 127.0.0.1 --port 8010
```

Puis dans un autre terminal (Node.js 22.12+ et pnpm 11) :

```powershell
cd frontend
pnpm install
pnpm dev
```

Ouvrir <http://127.0.0.1:5173/>. Le proxy Vite relaie `/v1`, `/health` et `/admin`
vers `http://127.0.0.1:8010`, avec un délai compatible avec les cinq minutes du backend.
La clé OpenAI, `SUMMARY_MODEL` et `EDITOR_MODEL` restent dans le `.env` du backend.
**Ne jamais mettre une clé dans une variable `VITE_*` ou dans le code du lecteur.**

```powershell
pnpm test
pnpm build
pnpm preview
```

Le build est dans `frontend/dist/`. Après compilation, redémarrer FastAPI permet de
servir aussi <http://127.0.0.1:8010/reader/>. `pnpm preview` utilise le port 4173 et
le même proxy. Définir `AUTH_PUBLIC_URL` sur l’adresse exacte utilisée pour le lecteur.
Les comptes sont partagés entre appareils qui se connectent au même serveur.

## Parcours

1. Créer son compte ou se connecter : Kiosque ouvre directement la dernière une.
   Un nouveau compte commence avec une sélection généraliste ; « Mes préférences »
   permet de choisir ses sujets et son contexte.
2. Les intérêts, notes, langues et taille sont synchronisés via
   `PUT /v1/readers/{user_id}/daily-edition`. Si le compte n’a aucune édition,
   le serveur lance immédiatement sa première préparation, sans la répéter lors d’une reconnexion.
3. Le serveur prépare une édition chaque jour à 4 h, même page fermée. Le lecteur
   affiche le statut et ouvre la dernière édition disponible. Un onglet ouvert
   vérifie les nouveautés chaque minute et lors du retour à la page, toutes les
   2,5 secondes pendant la première préparation, puis affiche la une dès qu’elle est prête.
   **Refaire ma une** propose un commentaire facultatif avant de préparer une nouvelle sélection.
   S’il est renseigné, le motif guide aussi les sept jours suivants. Une tentative par jour civil (Paris), remise
   à disposition à minuit, y compris après un échec. La limite est persistée côté serveur et
   affichée après rechargement. Le bouton concerne l’édition actuelle ; les archives restent
   intactes. Fermer la fenêtre pendant la préparation n’annule pas la demande.
   Une barre affiche la progression estimée et le temps restant approximatif, également
   visibles dans le journal après fermeture de la fenêtre ou rechargement. Seule la fin
   confirmée par le serveur permet d’atteindre 100 %. L’administrateur peut redonner une
   tentative avec **Réinitialiser « Refaire ma une »** dans **Éditions & planification**.
4. Cliquer sur un titre ou une image pour lire directement l’article chez son éditeur,
   dans un nouvel onglet. Le bouton **Fiche & avis** donne accès au résumé, à la raison
   de sélection et aux retours, sans quitter le journal.
5. **Archives** (icône de boîte dans la barre du haut) retrouve toutes les éditions du compte, conservées
   automatiquement avec leurs couvertures et leur vue en tranches. Une couverture
   ouvre l’édition existante, sans nouvelle génération. Le bouton **Retour** ramène à
   l’édition courante, qui reste mémorisée pendant la consultation des archives,
   y compris après un rechargement de la page. **Mon journal** permet aussi de la retrouver.
6. Le marque-page sauvegarde immédiatement un article, sans fenêtre intermédiaire.
   **Articles sauvegardés** (icône marque-page dans la barre du haut) rassemble ces lectures. Le menu **… → Ajouter
   à une collection** permet un classement facultatif ; un article peut appartenir à
   plusieurs collections. Classer un article le sauvegarde aussi automatiquement.
   Retirer un article d’une collection ou supprimer cette collection conserve sa sauvegarde.
   Désactiver le marque-page retire l’article des sauvegardes et de toutes ses collections,
   sans modifier les éditions archivées.

Un lien `/reader/?cover=<identifiant>` ouvre directement une édition, notamment depuis
l’inspecteur. Le paramètre de l’URL est prioritaire sur la dernière édition du navigateur.

La une privilégie les titres, les visuels et les sources : les bandeaux décoratifs,
slogans, numéros de rubrique et appels à l’action redondants ont été retirés. La sauvegarde
et le Courrier du lecteur restent disponibles dans une barre d’actions compacte.

La mise en page s’adapte aux éditions courtes et aux images manquantes : le sujet principal
utilise la largeur disponible, puis les rubriques se suivent avec une à trois colonnes
selon leur nombre d’articles et la largeur de l’écran. Les cartes coulent de haut en bas
dans chaque colonne, sans lignes de hauteur imposée. Un visuel en attente, rejeté ou en
erreur ne réserve aucun emplacement vide. Les éditions enregistrées bénéficient aussi
de cette composition, sans nouvelle génération.

Les cartes et fiches affichent le temps de lecture estimé à 200 mots par minute,
arrondi à la minute supérieure, à partir du texte extrait de l’article. Si seul un
extrait est disponible, aucune durée n’est affichée. Les éditions
enregistrées avant cet ajout sont enrichies depuis le catalogue lors de leur ouverture.

Les visuels sont servis par le backend après un contrôle Nano de leur pertinence.
Cette analyse est facturée une seule fois par article/contexte/image/version, puis
conservée en PostgreSQL pour toutes les éditions. Un doute de pertinence (`uncertain`)
ne masque plus une illustration explicitement déclarée par l’éditeur sur la page de
l’article ; les rejets explicites et les erreurs restent exclus. Si une candidate échoue,
le backend en essaie d’autres, jusqu’à cinq URLs distinctes, y compris `picture`, `srcset`
et les images à chargement différé. Les brèves affichent également leur illustration.
Le paramètre `?v=images-4` renouvelle le cache du navigateur. Même un article autrefois
marqué sans image consulte le backend : son cache négatif de cinq minutes borne les
nouvelles tentatives, sans bloquer définitivement les anciennes éditions.

Les nouvelles éditions privilégient les actualités des dernières 24–72 heures (7 jours maximum)
et acceptent les lectures de fond durables jusqu'à un an. Ces catégories sont consultables dans
les fiches. Si les articles directement liés aux sujets ne suffisent pas, une rubrique
**Exploration** complète l'édition avec des thèmes connexes mais différents. Chaque découverte
explique son lien avec les intérêts du lecteur dans sa fiche ; elle reste accessible par les filtres et favoris.
Les éditions déjà enregistrées conservent leur sélection.

Les préférences permettent de choisir 15, 18 ou 20 articles et les langues français
ou français/anglais. Le premier sujet reçoit davantage de poids. Enregistrer des
préférences ne lance pas de génération. `discover_web` et `discover_sources` sont
activés ; le rédacteur choisit ses actions et les propositions de sources restent à
approuver dans l’administration.

Une édition partielle ou de secours est signalée. Les erreurs réseau, 429, 503 et 504
restent visibles ; aucun contenu fictif et aucune relance payante automatique ne les
remplacent. Après une fermeture pendant la génération, la dernière édition est retrouvée à la réouverture :
le traitement côté serveur continue. Le statut quotidien est persistant et les tentatives
sont uniques par compte et date. Un serveur arrêté rattrape la dernière échéance manquée
à son redémarrage, sans rejouer les tentatives déjà lancées. Le serveur doit rester actif
pour démarrer à 4 h ; `DAILY_EDITIONS_ENABLED=false` suspend cette préparation.

## Commandes réservées à l’administration

Le lecteur n’affiche plus « Mes éditions », le sélecteur d’historique technique, les
coûts, les états internes de sélection, le bilan des préférences ni les liens vers
l’administration. Les anciennes éditions restent disponibles dans **Archives**.
Les erreurs d’infrastructure sont reformulées sans clés, configuration ou traces.
Les préférences, sauvegardes, likes, avis et la provenance des résumés restent visibles.

`/admin/covers` rassemble le suivi des préparations de 4 h, la disponibilité des modèles,
le choix d’un profil, **Générer une une maintenant**, **Actualiser**, l’historique filtré
et les diagnostics détaillés. Consulter ou actualiser l’administration ne déclenche aucun
appel payant ; seule la commande explicite de génération en déclenche un.
Le profil utilisé est celui enregistré côté serveur ; une génération manuelle ne décale
pas la prochaine préparation quotidienne.

## Stockage et retours

Le bouton **Thèmes**, accessible dès l’accueil puis dans la navigation du lecteur,
ouvre six aperçus : **Éditorial** (apparence d’origine), **Tech** (accents menthe),
**Finance** (saumon, bleu encre, dense), **Atelier** (ivoire et bleu, grands titres),
**Minimal** (blanc, noir, aéré) et **Playful** (lavande, cartes arrondies).
Le choix s’applique immédiatement au journal, à la bibliothèque et aux fenêtres du
lecteur. Il change les couleurs, les typographies et la mise en page, sans modifier
les sujets ni générer une édition. Les flèches du clavier parcourent les choix et
Échap ferme le sélecteur.

`kiosque.theme.v1` conserve l’apparence pour ce navigateur, indépendamment du compte.
Les autres onglets de la même origine se synchronisent. Si le stockage est indisponible,
le thème s’applique pour la visite en cours ; une valeur inconnue rétablit Éditorial.
Les palettes et variantes sont dans `src/themes.css`, leur catalogue et le stockage
dans `src/themes.js`, le sélecteur dans `src/ThemePicker.jsx`.

Dans cette même fenêtre, **Apparence** propose **Clair**, **Sombre** et **Auto**,
indépendamment du thème. Les six ambiances et leurs aperçus ont une palette claire
et sombre. **Auto**, le réglage initial, suit `prefers-color-scheme` et réagit aux
changements du système sans rechargement. Un choix explicite Clair ou Sombre reste
fixe. `kiosque.colorMode.v1` mémorise ce réglage et le synchronise entre onglets ;
une valeur absente, invalide ou inaccessible revient à Auto. L’apparence est appliquée
avant le premier rendu React pour éviter un éclair de la mauvaise palette.

- Les comptes et profils de lecture sont en base (`accounts`) ; la connexion utilise
  un cookie `HttpOnly` et une session révocable dans `account_sessions`.
- `kiosque.lastCover`, suffixée par l’identifiant du compte, mémorise seulement la
  dernière édition sur l’appareil. Les anciennes clés de compte local sont ignorées.
- Les profils de préparation et les tentatives quotidiennes sont persistés dans PostgreSQL
  (`daily_edition_profiles` et `daily_edition_runs`).
- Les archives lisent toutes les éditions du compte via `/v1/archives`.
- Les articles sauvegardés sont persistés dans PostgreSQL via `/v1/saved-articles`,
  indépendamment de leur classement facultatif via `/v1/collections`. Les articles
  des collections existantes sont repris une seule fois, sans réapparaître après retrait.
  Les anciens marque-pages locaux (`kiosque.saved`) sont repris dans « À lire ».

Les couvertures, résumés et événements sont enregistrés par le backend dans PostgreSQL.
Le clic vers l’éditeur envoie `open` ; les boutons d’avis envoient `useful`,
`already_known` ou `not_interested` à `/v1/feedback`. Les articles concernés sont
écartés des prochaines sélections de cet identifiant par le backend existant.
Les notes du profil ne sont pas réécrites automatiquement. **Expliquer ou préciser pour
la suite** ajoute un motif et un commentaire à l'avis ; la case **Ajuster aussi mes prochaines
lectures** permet de définir une préférence avec une cible, un effet et une durée explicites.

**Écrire à Kiosque**, qui remplace « Orienter mes lectures », ouvre le Courrier du lecteur.
Un message libre suffit : Kiosque le lit, répond et met à jour la fiche accessible via
**Ma fiche**. Des suggestions remplissent le brouillon sans l'envoyer. Entrée envoie,
Maj + Entrée ajoute une ligne. Le message apparaît pendant la lecture, puis la réponse
confirme l'enregistrement ; le détail des ajustements se déplie à la demande. La fiche
souligne les préférences modifiées. Elle s'ouvre à côté de la conversation sur grand écran
et dans une vue dédiée sur petit écran, avec retour au brouillon conservé.

Les échanges persistent sur le serveur ; fermer la fenêtre pendant l'envoi ne perd pas
le résultat. Une erreur conserve le brouillon, et un renvoi utilise le même identifiant
pour éviter les doublons. Un message ambigu peut donner lieu à une question sans modifier
la fiche. Chaque nouveau message utilise un appel au modèle économique, sans relance
automatique. Aucune génération d'édition n'est déclenchée par le chat.

Pour 18 articles, la diversification occupe au maximum 3 places au total ; chaque règle
« moins de » limite sa cible à 3 articles. Une exclusion est appliquée aussi aux découvertes.
Les contraintes peuvent produire une édition plus courte, sans les relâcher silencieusement.

Une règle vaut pour les prochaines générations, ou uniquement pour la prochaine édition
non vide enregistrée, même partielle. Une édition en cours conserve ses règles initiales.
Les demandes ponctuelles appliquées restent consultables avec le lien de l'édition.
Le bilan **Vos demandes dans cette édition** indique les articles correspondants et les
demandes non satisfaites. La lecture de ce bilan est gratuite ; la conversation utilise
le modèle économique, comme l'évaluation sémantique lors de la prochaine génération.
Les avis et explications se rechargent après actualisation. Les conflits de correction
(409) sont signalés et la liste peut être actualisée. Les anciennes éditions restent lisibles.

L’historique affiche les 100 dernières éditions du compte connecté. La session côté serveur
et les contrôles d’appartenance protègent ses lectures. Reconfigurer les sujets conserve
les éditions et les favoris. Le stockage local ne contient pas de preuve de connexion.

## Structure et validation sans crédits

- `src/api.js` : appels HTTP et erreurs, sans retry de génération.
- `src/reader.js` : profil, requête et adaptation des vraies couvertures.
- `src/App.jsx`, `Newspaper.jsx`, `components.jsx` : parcours et rendu.
- `src/reader.test.js` : contrat des appels, erreurs, sécurité des liens, aucune perte
  ou duplication d’articles pour des éditions de 0 à 20 éléments.
- Les doublures HTTP de ces tests restent limitées aux fichiers de test ; le lecteur
  n’embarque aucun corpus fictif ni service de démonstration.

Les tests automatisés ne consomment pas de crédits :

```powershell
# Depuis frontend/
pnpm test
# Depuis la racine
.\.venv\Scripts\python.exe -m pytest
```

La vérification manuelle se fait dans le lecteur connecté au backend réel. Consulter une
édition existante est gratuit ; lancer une nouvelle génération utilise les modèles configurés.
