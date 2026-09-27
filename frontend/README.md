# Kiosque — interface lecteur connectée

React 19 / Vite 7, API FastAPI et PostgreSQL. Comptes de démonstration locaux au navigateur,
sans vérification du mot de passe ni authentification serveur.

## Rubrique Événements

L’onglet **Événements** et l’aperçu en bas de la une proposent des sorties à Paris,
des émissions et des podcasts issus d’un catalogue préparé de 17 références.
La sélection suit les sujets cochés, filtre les dates et varie les formats, sans
appel IA. Les filtres Sortir / Regarder / Écouter sont disponibles avant toute
génération d’articles. Voir [la pipeline, les sources et l’entretien du catalogue](EVENTS.md).

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
le même proxy. Le stockage du navigateur est séparé pour chaque origine/port :
utiliser la même adresse pour retrouver son profil local.

## Parcours

1. Ouvrir un compte de démonstration, puis choisir ses sujets et un contexte facultatif.
2. Cliquer sur **Générer ma une** pour envoyer les intérêts, notes, langues et taille
   à `POST /v1/covers`. Ce clic utilise les crédits OpenAI du serveur.
3. Pendant la préparation, un temps écoulé est affiché, sans inventer des étapes de
   progression. Les doubles clics sont bloqués ; l’ancienne édition reste lisible.
4. Cliquer sur un titre ou une image pour lire directement l’article chez son éditeur,
   dans un nouvel onglet. Le bouton **Fiche & avis** donne accès au résumé, à la raison
   de sélection et aux retours, sans quitter le journal.
5. **Archives** (icône de boîte dans la barre du haut) retrouve toutes les éditions du compte, conservées
   automatiquement avec leurs couvertures et leur vue en tranches. Une couverture
   ouvre l’édition existante, sans nouvelle génération.
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
remplacent. Après une fermeture pendant la génération, actualiser l’historique :
le traitement côté serveur peut encore se terminer. Il n’y a pas encore de suivi de
tâche asynchrone ni de reprise automatique d’une requête interrompue.

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

- `kiosque.accounts.v1`, `kiosque.session.v1` : comptes de démonstration et session locale.
- Les clés `kiosque.reader.v1`, `kiosque.lastCover` et `kiosque.pending` sont suffixées
  par l’identifiant du compte pour isoler le profil, la dernière édition et une génération en cours.
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

L’historique affiche les 100 dernières éditions du compte déclaré. Les éditions, bibliothèques
et retours vérifient cet identifiant côté API. Ce mécanisme n’est pas une authentification ; le prototype
reste destiné à un serveur local de confiance. Reconfigurer le profil conserve les
éditions, l’identité locale et les favoris. Si `localStorage` est inaccessible, l’usage
reste possible pour la visite en cours.

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
