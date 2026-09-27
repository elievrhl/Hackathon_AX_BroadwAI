# Kiosque — interface lecteur connectée

React 19 / Vite 7, API FastAPI et PostgreSQL. Comptes de démonstration locaux au navigateur,
sans vérification du mot de passe ni authentification serveur.

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
5. Retrouver les éditions enregistrées dans l’historique, sans nouvelle génération.
   L’inspecteur fournit la sélection, les scores, résumés, outils et coût après génération.
6. Utiliser le marque-page pour ranger un article dans une ou plusieurs bibliothèques,
   ou en créer une sur le moment. **Ma bibliothèque** conserve les vues couvertures et
   tranches et permet de renommer les collections et d’en retirer des articles.

Un lien `/reader/?cover=<identifiant>` ouvre directement une édition, notamment depuis
l’inspecteur. Le paramètre de l’URL est prioritaire sur la dernière édition du navigateur.

La une privilégie les titres, les visuels et les sources : les bandeaux décoratifs,
slogans, numéros de rubrique et appels à l’action redondants ont été retirés. La sauvegarde
et le Courrier du lecteur restent disponibles dans une barre d’actions compacte.

Les cartes et fiches affichent le temps de lecture estimé à 200 mots par minute,
arrondi à la minute supérieure, à partir du texte extrait de l’article. Si seul un
extrait est disponible, aucune durée n’est affichée. Les éditions
enregistrées avant cet ajout sont enrichies depuis le catalogue lors de leur ouverture.

Les visuels sont servis par le backend après un contrôle Nano de leur pertinence.
Cette analyse est facturée une seule fois par article/contexte/image/version, puis
conservée en PostgreSQL pour toutes les éditions. Les images rejetées, douteuses ou
non vérifiables disparaissent au profit d'une carte textuelle. Le paramètre
`?v=review-1` renouvelle le cache du navigateur pour les anciennes images non contrôlées.

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

- `kiosque.accounts.v1`, `kiosque.session.v1` : comptes de démonstration et session locale.
- Les clés `kiosque.reader.v1`, `kiosque.lastCover` et `kiosque.pending` sont suffixées
  par l’identifiant du compte pour isoler le profil, la dernière édition et une génération en cours.
- Les bibliothèques et leurs articles sont enregistrés dans PostgreSQL via `/v1/collections`.
  Les anciennes revues sauvegardées sont migrées une fois ; les anciens marque-pages locaux
  (`kiosque.saved`) sont repris dans « À lire ».

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
