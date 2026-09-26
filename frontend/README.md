# Kiosque — interface lecteur connectée

React 19 / Vite 7, API FastAPI et PostgreSQL. Aucun compte à créer pour l’usage local.

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

1. Choisir un prénom et des sujets, avec un contexte facultatif. Aucun e-mail requis.
2. Cliquer sur **Générer ma une** pour envoyer les intérêts, notes, langues et taille
   à `POST /v1/covers`. Ce clic utilise les crédits OpenAI du serveur.
3. Pendant la préparation, un temps écoulé est affiché, sans inventer des étapes de
   progression. Les doubles clics sont bloqués ; l’ancienne édition reste lisible.
4. Lire les titres et rubriques du rédacteur ; ouvrir un article pour accéder au site
   éditeur, à la fiche de lecture repliée et à la raison de sélection.
5. Retrouver les éditions enregistrées dans l’historique, sans nouvelle génération.
   L’inspecteur fournit la sélection, les scores, résumés, outils et coût après génération.

Un lien `/reader/?cover=<identifiant>` ouvre directement une édition, notamment depuis
l’inspecteur. Le paramètre de l’URL est prioritaire sur la dernière édition du navigateur.

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

- `kiosque.reader.v1` : prénom et préférences ; migration du précédent prototype.
- `kiosque.user` : identifiant aléatoire `local-<uuid>`, conservé entre les visites.
- `kiosque.lastCover`, `kiosque.saved` : dernière édition et marque-pages.
- `kiosque.pending` : indication locale d’une génération potentiellement interrompue.

Les couvertures, résumés et événements sont enregistrés par le backend dans PostgreSQL.
Le clic vers l’éditeur envoie `open` ; les boutons d’avis envoient `useful`,
`already_known` ou `not_interested` à `/v1/feedback`. Les articles concernés sont
écartés des prochaines sélections de cet identifiant par le backend existant.
Il n’y a pas encore de mise à jour automatique des notes de profil à partir des avis.

L’historique affiche les 100 dernières éditions de **tous les profils du serveur local**,
notamment les anciens essais. Les retours sont désactivés sur les éditions d’un autre
identifiant. Ce filtrage côté interface n’est pas une authentification ; le prototype
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
