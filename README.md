# Kiosque — presse personnalisée

## Interface lecteur — React connecté au backend

Le projet s’appelle **Kiosque**. L’interface [`frontend/`](frontend/README.md)
affiche les vraies couvertures de l’API : profil local sans compte, génération de
15 à 20 articles, historique, rubriques, liens éditeurs, favoris et retours de lecture.
La génération payante ne démarre que sur le bouton « Générer ma une ».

La une affiche les visuels des articles : métadonnées Open Graph/Twitter en priorité,
puis image structurée JSON-LD ou image principale du texte. Un lien sous le visuel
renvoie vers l’éditeur. Les images indisponibles laissent une carte textuelle ; les
brèves restent compactes. Les éditions déjà enregistrées sont illustrées à leur
ouverture, sans régénérer les résumés.
Le backend sert les images des articles sélectionnés via `/v1/articles/{id}/image`,
avec contrôle des destinations publiques, de la taille et du format raster. Le cache
en mémoire dure six heures (32 Mo/128 entrées au maximum), les échecs cinq minutes.

Avant le premier affichage, **GPT-5.4 nano** contrôle la pertinence visuelle par rapport
au titre et à 1 000 caractères de l'article. Seule une miniature JPEG sans métadonnées,
limitée à **768 pixels et 100 Ko**, est transmise à OpenAI ; le visuel affiché conserve
sa qualité d'origine. Réponse JSON minimale (`keep`, `reject`, `uncertain`), plafond de
32 tokens, raisonnement désactivé, aucun outil ni relance automatique du SDK.
Seul `keep` autorise l'image : les doutes, refus, erreurs, formats invalides et animations
laissent la carte textuelle. Une erreur ne peut être réessayée qu'après 24 h.

La table `image_reviews` conserve les verdicts et les coûts déclarés, partagés entre
éditions et utilisateurs, même après redémarrage. La clé inclut l'article, son contexte,
les pixels compressés, le modèle et la version du contrôle. Une réservation atomique
évite les appels simultanés identiques. Sans clé API, les images non vérifiées sont masquées.
`IMAGE_REVIEW_ENABLED=true` et `IMAGE_REVIEW_MODEL=gpt-5.4-nano` sont les défauts ;
désactiver le contrôle rétablit l'affichage sans validation sémantique.
Ce contrôle est facturé au premier chargement d'un nouveau visuel. Son coût figure dans
`image_reviews`, séparément du coût de génération enregistré dans la couverture.

```powershell
cd frontend
pnpm install
pnpm dev
```

Prérequis : Node.js 22.12+ et pnpm 11. Ouvrir <http://127.0.0.1:5173/>.
Le backend doit tourner sur le port 8010 avec PostgreSQL. Vite relaie les appels à
l’API ; aucune clé n’est envoyée au navigateur. Après `pnpm build`, FastAPI peut
aussi servir le lecteur sur <http://127.0.0.1:8010/reader/> (redémarrer le backend).

## Backend agentique (package `broadwai`)

Première implémentation de la collecte d'articles et de la création d'une couverture personnalisée.
Python 3.12+, FastAPI, PostgreSQL, SDK OpenAI Responses. Aucun appel LLM payant au démarrage.

Pour reprendre le travail avec un autre agent : [contexte et passation du projet](PROJECT_HANDOFF.md).

## Un journal de 15 à 20 articles

`POST /v1/covers` demande désormais **18 articles par défaut** (champ `size`, maximum 20).
Le quota par source vaut trois par défaut (au moins six domaines pour 18 articles).
Le profil se règle dans le frontend. Celui-ci présente la une par rubriques, avec les titres
originaux des éditeurs, sans traduction, même pour les éditions déjà enregistrées. Les titres et
images ouvrent directement l'article dans un nouvel onglet. Les résumés restent consultables
dans `/admin/covers`. L’inspecteur ouvre la couverture sélectionnée dans le
frontend via `/reader/?cover={id}`.

La préparation se déroule ainsi :

1. Interprétation des notes en besoins prioritaires, puis classement lexical tenant compte de
   ces besoins et des notes. Pool diversifié de 96 titres/extraits maximum, avec une place pour
   les articles récents que les mots-clés bilingues peuvent manquer.
2. Un appel au rédacteur définit les rubriques et choisit les articles prometteurs. Son score
   éditorial est une appréciation du modèle, pas une probabilité. Sous 70/100, pas de résumé.
3. Extraction et fiches structurées du modèle économique, réutilisables entre utilisateurs ;
   jusqu'à trois préparations simultanées. Le rédacteur reçoit le résumé et les réserves,
   sans répéter les points clés ni transmettre tous les textes complets.
4. L'agent évalue les fiches et les manques, puis choisit une recherche catalogue ou web,
   une lecture approfondie, une proposition de source, ou la finalisation. Une recherche vide
   appelle un changement de requête ; un domaine en échec répété est évité pendant ce run.
5. Application des quotas aux choix du modèle, en conservant leur ordre éditorial et en traçant
   les retraits ; validation des identifiants, du nombre et des doublons. Pour une
   sélection d'au moins 15 articles directs : 3 à 5 rubriques, au moins deux articles chacune.
   Si la sélection directe manque, une rubrique **Exploration** complète les places libres
   avec des thèmes connexes mais différents et un lien explicite avec les intérêts.
   Une sélection courte est refusée s'il reste des moyens de chercher. Après épuisement,
   le résultat reste explicitement partiel plutôt que de promettre un remplissage pertinent.

Les défauts conservent 24 nouveaux résumés, 6 décisions, 2 passes de recherche web et ajoutent
une interprétation des notes si présentes, une planification et au plus 4 filtres de recherche.
Les besoins interprétés doivent citer le profil, puis alimentent le classement avant le plan.
Le filtre a un prompt autonome et un seuil cohérent avec `MIN_EDITORIAL_SCORE`. Le rédacteur utilise
le raisonnement `low` sur GPT-5 ; le modèle de résumé conserve son réglage économique.
Les téléchargements de présélection sont limités à 24, les imports web à 20 tentatives.
Les actualités privilégient les dernières 24–72 heures ; celles de plus de 7 jours
(`MAX_ARTICLE_AGE_DAYS`) ou sans date sont écartées, quelle que soit leur provenance. Les essais,
analyses et autres lectures de fond n'ont **aucune limite d'âge**, y compris plusieurs décennies,
si leur contenu reste valable. L'ancien réglage `MAX_EVERGREEN_AGE_DAYS` est ignoré.
Une fiche évalue la temporalité et cite le texte : durable, sensible au temps, périmé ou incertain.
Les contenus périmés ou dont la validité est incertaine sont écartés ; l'âge seul ne suffit pas.
Cette évaluation éditoriale n'est pas une vérification externe exhaustive des faits.
Les résultats scientifiques ont une fenêtre distincte (`MAX_RESEARCH_AGE_DAYS`, 365 par défaut).
Le lecteur distingue « Lecture de fond », « Recherche » et « Actualité », sans inventer de date.
Le contexte explicite des notes doit être respecté avant résumé, même pour un score élevé.
Les réserves d'exploration sont proposées par le filtre éditorial, avec le même seuil de qualité.
Elles sont préparées uniquement en cas de manque, après une première recherche directe si la
découverte web est demandée. Les recherches suivantes peuvent élargir les thèmes, sans relâcher
les exclusions, les langues, les contraintes des notes, les quotas ni les limites d'âge.
Le lecteur affiche « Exploration » et la raison de ce détour. Les règles temporelles s'appliquent
aussi à ces découvertes. Les budgets restent inchangés ; une édition peut rester partielle
si aucun complément de qualité n'est trouvé.
Ces plafonds restent configurables. `usage.cost` estime le montant en USD à partir des tokens
déclarés, du cache et des appels web, uniquement pour les modèles tarifés dans `pricing.py`.
Ce n'est pas une facture ni un plafond monétaire garanti. Les tarifs standard mini/nano ont été
vérifiés le 26 septembre 2026 ; hors taxes, éventuels suppléments et appels sans usage retourné.

Le budget réconcilie chaque réservation avec l'usage déclaré, même pour les appels simultanés.
Sans usage retourné, il garde l'estimation par prudence. `FINAL_TOKEN_RESERVE` protège la rédaction
finale : l'exploration s'arrête avant d'entamer cette enveloppe et une édition partielle peut être
composée. Les propositions de sources sont différées si la couverture est encore incomplète.
`usage.reserved_token_estimate` conserve le cumul historique ; `unsettled_token_reservations`
désigne les réservations non réconciliées et `remaining_tokens` le budget réellement disponible.

Les recherches ciblent un besoin à la fois et conservent l'historique et les motifs de rejet.
Un article écarté ne repasse pas dans les filtres à chaque reformulation. Les finalisations sont
contrôlées aussi en mode partiel : rubriques connues, besoin cité, preuve dans la fiche, titre,
rôle éditorial et absence de reprise du même événement sans angle distinct. Le lecteur respecte les
rôles (sujet principal, secondaire, brève, lecture), avec compatibilité pour les éditions anciennes.
Les fiches `brief-v6` comprennent validité et titre. Le titre affiché et celui des nouvelles
sélections reprennent toujours l'original, même si une fiche en cache contient une ancienne
traduction. Les anciennes éditions restent consultables.

`examples/sources-economy.json` propose dix flux économiques supplémentaires ; huit ont été
validés et collectés lors de l'essai local (les flux en erreur sont ignorés par le script).
La diversification prépare désormais une fois les caractéristiques et actualise les similarités
à chaque choix : mesurée à 346 ms avec le classement sur 548 articles, contre 134 secondes
pour l'ancienne diversification. Pas d'appel LLM nécessaire à cette étape.

## Démarrer

Prérequis : [uv](https://docs.astral.sh/uv/) et Docker Compose (ou PostgreSQL existant).

```powershell
Copy-Item .env.example .env
docker compose up -d postgres
uv sync --python 3.12
```

Dans `.env`, renseigner `OPENAI_API_KEY`, `SUMMARY_MODEL` et `EDITOR_MODEL` avec des modèles
disponibles sur votre compte et compatibles avec Responses / Structured Outputs. Utiliser un modèle
économique pour les fiches et un modèle capable de décider des actions pour le rédacteur.
`WEB_SEARCH_ENABLED=true` active la recherche web hébergée chez OpenAI avec la même clé API.
Aucun Assistant, agent enregistré, base vectorielle ou fournisseur de recherche supplémentaire
n'est nécessaire. Créer une clé API dans un projet OpenAI avec facturation active et accès aux
modèles choisis. Ne pas publier `.env`.

```powershell
uv run uvicorn broadwai.api:app --host 127.0.0.1 --port 8000
```

API interactive : <http://127.0.0.1:8000/docs>. Le schéma PostgreSQL initial est créé au démarrage.
`DATABASE_URL` permet d'utiliser une autre instance. Les identifiants de Compose sont réservés au
développement local. Le volume `postgres_data` conserve les données entre les redémarrages.

## Administration simple

Ouvrir <http://127.0.0.1:8000/admin> (également accessible depuis `/`). Aucun build frontend requis.

- Ajouter, modifier, mettre en pause ou supprimer des sites web, flux RSS/Atom ou Hacker News.
- Déclencher la collecte d'une source ou de toutes les sources actives, avec la limite configurée.
- Voir la dernière collecte, le nombre d'articles trouvés (y compris déjà connus) et les erreurs.
- Rechercher les articles par titre/domaine, filtrer par source de collecte ou état d'extraction,
  parcourir les pages, ouvrir les métadonnées, extraits, textes et fiches déjà générées.
- Les données JSON complètes sont accessibles dans le détail de chaque article.

Deux tables supplémentaires sont créées de façon additive au redémarrage : `sources` et
`source_articles`. Un même article peut appartenir à plusieurs sources. Supprimer une source
conserve les articles et retire seulement ses associations. Modifier une source conserve son
historique d'articles. Les collectes directes via `/v1/ingest` ne sont pas rattachées rétroactivement.

L'admin n'appelle pas de LLM et ne génère pas de fiches : elle affiche les données disponibles.

### Blogs et journaux sans flux

Dans `/admin`, choisir **Ajouter → Site web (blog ou journal)** et coller l'URL de la page
d'accueil du blog ou d'une rubrique qui liste les articles. Enregistrer, puis cliquer sur **Collecter**.
Les titres, dates et langues disponibles sont récupérés sur les pages d'articles, ainsi que leur
texte accessible. Les articles rejoignent le même catalogue que ceux des flux et peuvent servir
aux couvertures. Cette collecte ne consomme pas de crédits LLM.

Exemple de source via `POST /v1/sources` :

```json
{
  "name": "Mon blog",
  "kind": "website",
  "url": "https://exemple.com/blog/",
  "limit_per_source": 20,
  "enabled": true
}
```

`POST /v1/ingest` accepte aussi `website_urls`, combinable avec `feed_urls` et `hacker_news`.
Voir `examples/ingest-websites.json`. Les liens HTML et les listes structurées JSON-LD sont examinés,
puis chaque page candidate est vérifiée avant import. Les liens restent sur le même domaine
(avec ou sans `www`), les menus et liens utilitaires sont filtrés et les URL sont dédupliquées.
Une collecte visite au plus deux fois la limite demandée, plafonnée à 50 pages candidates, avec
cinq téléchargements simultanés au maximum et un délai de 100 secondes par site. Les erreurs
figurent dans le rapport ; les résultats des lots déjà terminés sont conservés.

Cette version lit le HTML fourni par le serveur : pas d'exécution JavaScript, de parcours récursif,
de pagination ou de sitemap. La reconnaissance des articles reste heuristique. Une rubrique
ciblée donne souvent de meilleurs résultats qu'une page d'accueil généraliste. Les pages bloquées
sont signalées et les paywalls ne sont pas contournés ; un extrait disponible peut être conservé.
Les schémas des sources et propositions sont mis à jour au redémarrage du backend, en conservant
les sources et historiques existants.

### Inspection des couvertures

`/admin/covers` affiche l'historique et le déroulement enregistré de chaque couverture. Le lien
« Couvertures & traces » est disponible dans l'admin. `GET /v1/covers?limit=30&offset=0` liste
les couvertures ; `GET /v1/covers/{id}` contient la trace et le champ `diagnostics`.

Pour les nouvelles générations, le journal conserve le profil/les limites utilisés, les scores
BM25 et leurs composantes, la shortlist après diversification, les demandes d'extraction et de
résumé, les fiches réutilisées/générées, les candidats, décisions, arguments/résultats d'outils,
et les erreurs de validation. Les appels modèles comportent durée, modèle et usage retourné
par le fournisseur, dont les tokens d'entrée mis en cache lorsqu'ils sont disponibles.
Ces tokens sont déjà inclus dans le total entrant ; ils ne sont pas à additionner une seconde fois.
Les scores sont relatifs au corpus, pas des probabilités de pertinence.

Les trois premières couvertures ont une trace ancienne partielle : scores et shortlist n'étaient
pas enregistrés. L'interface indique les données manquantes sans les reconstruire. Le journal
est consultable après la génération terminée, pas en streaming ; il n'est pas conservé si une
requête échoue avant l'enregistrement de la couverture. Les tableaux de classement conservent
les 100 premiers candidats par passage ; les fiches finales présentées au rédacteur sont conservées.
La consultation ne consomme pas de crédits LLM. Les justifications sont les explications publiques
du rédacteur, pas son raisonnement interne. Les secrets de configuration ne sont jamais journalisés.
Les sources proposées par le rédacteur apparaissent dans une section dédiée. « Approuver »
ajoute la source validée aux sources actives, sans déclencher de collecte ; « Refuser » conserve
la décision et empêche une proposition identique de réactiver cette source automatiquement.
Une collecte admin à la fois par processus ; garder un seul worker pour cet usage local.
Cette page utilise l'API locale existante sans authentification : elle n'est pas destinée à une
exposition publique. L'absence de texte ou de fiche est indiquée explicitement.

Routes associées : `GET/POST /v1/sources`, `PUT/DELETE /v1/sources/{id}`,
`POST /v1/sources/collect`, `POST /v1/sources/{id}/collect`,
`GET /v1/admin/articles` (pagination/filtres) et `GET /v1/admin/articles/{id}`.

Le fichier `examples/sources.json` propose 35 flux sélectionnés : IA, développement, infrastructure,
cybersécurité, sciences, économie et actualité générale, en français et en anglais.
Pour ajouter ces sources et collecter jusqu'à 20 articles par nouvelle source via l'API :

```powershell
uv run python -m scripts.seed_sources --collect
# Si le serveur tourne sur un autre port :
uv run python -m scripts.seed_sources --base-url http://127.0.0.1:8010 --collect
```

Le script valide les nouveaux flux avant de les enregistrer, réutilise les sources déjà présentes
sans modifier leurs paramètres et respecte leur mise en pause. `--only-new` permet de ne traiter
que les nouvelles sources ; `--limit 10` change la limite des nouveaux ajouts. Certains flux publient
moins d'articles que la limite demandée. Le rapport est écrit dans `data/sources-import-report.json`.

`uv run python -m scripts.audit_catalog --extract-sample 6` vérifie un échantillon de textes provenant
de domaines distincts et les conserve dans PostgreSQL. Aucun modèle n'est appelé.
Les articles de presse peuvent rester limités à un extrait ; un flux valide ne garantit pas un
accès au texte complet. Les paywalls ne sont pas contournés.

## Premier parcours

```powershell
# Collecte de métadonnées et extraits ; pas de LLM.
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/ingest `
  -ContentType 'application/json' -InFile examples/ingest.json

```

Ouvrir ensuite Kiosque sur <http://127.0.0.1:5173/>, choisir ses sujets et son contexte,
puis cliquer sur **Générer ma une**. Le frontend construit la requête à partir du profil local ;
les thèmes utilisent des mots-clés français et anglais car BM25 ne traduit pas les intérêts.

Pour un premier test réel, renseigner les trois variables LLM dans `.env`, redémarrer le serveur,
puis vérifier que `/health` indique `llm_configured: true`. La recherche web peut être désactivée
avec `WEB_SEARCH_ENABLED=false`.
`POST /v1/covers` renvoie actuellement la couverture à la fin du traitement (maximum 300 secondes),
avec sa trace. Le lecteur affiche le temps écoulé ; il n'y a pas encore de flux d'événements SSE.
Les éditions déjà générées se consultent depuis son historique et leurs traces dans l'inspecteur.

## Fonctionnement

1. Pages web, RSS/Atom et API officielle Hacker News alimentent un catalogue commun. Les URL sont normalisées
   (tracking retiré, paramètres métier conservés). Les réimportations sont idempotentes.
2. Un classement lexical **BM25** combine les intérêts pondérés et la fraîcheur. Les langues connues,
   exclusions et articles consommés sont filtrés. Diversification des titres et sources avant résumé.
3. Les textes des candidats sont extraits avec Trafilatura. Un échec conserve seulement l'extrait
   disponible et cette provenance est indiquée. Un titre seul ne produit pas de résumé.
4. Le petit modèle génère une fiche structurée, indépendante du lecteur. PostgreSQL la met en cache
   par article, hash du contenu et version de prompt/modèle. Une modification invalide son utilisation.
5. Le rédacteur reçoit les fiches, pas les articles complets. À chaque tour, le LLM choisit une action
   JSON validée : `search_catalog`, `search_web`, `read_article`, `propose_source` ou `finalize`.
   Le backend exécute l'action, fournit son résultat au modèle, puis demande la décision suivante.
6. La finalisation vérifie les identifiants, doublons proches, quotas de sources et taille maximale.
   Un résultat invalide revient au modèle pour correction. La couverture garde les liens originaux,
   fiches, justifications publiques, avertissements, actions et consommation de tokens.
7. Les événements de feedback sont stockés séparément. `open`, `useful`, `already_known` et
   `not_interested` retirent cet article des prochaines sélections. Une `impression` seule ne le fait pas.

### Découverte d'articles et de sources

La recherche utilise l'outil hébergé OpenAI `web_search`, via Responses et le modèle rédacteur.
Chaque action demande `max_tool_calls=1` ; l'usage conserve le nombre effectivement retourné
par le fournisseur. Les requêtes sont ouvertes : les restrictions positives `site:` et `domain:`
proposées par l'agent sont retirées et la deuxième passe privilégie blogs, auteurs et revues
indépendantes. Le profil complet accompagne la recherche, y compris le contexte des notes.
Le backend examine les URL citées et celles de `web_search_call.action.sources`, avec au plus
12 candidats par passe et deux par domaine. Il valide les destinations et extrait les pages,
puis filtre leur pertinence avant de payer les résumés.
La prose générée par la recherche n'est jamais utilisée comme texte original d'un article.
Les articles importés portent une provenance (fournisseur, requête, date et justification), visible
dans leurs données JSON. Les liens cités sont conservés dans la trace de couverture.

`propose_source` accepte une URL déjà observée ou la racine d'un site observé. Le backend recherche
un flux RSS/Atom déclaré dans la page et vérifie son contenu. À défaut de flux exploitable, il
vérifie un échantillon des liens d'articles et propose la page comme source de type `website`.
Les URL inventées par le modèle sont refusées. Une page sans flux ni article exploitable est rejetée.
La justification, la page d'origine et la décision admin sont stockées dans `source_proposals`.
Routes : `GET /v1/source-proposals`, `POST /v1/source-proposals/{id}/review` avec `{"approve":true}`
ou `{"approve":false}`. Les approbations sont transactionnelles et idempotentes.

Par couverture, les limites par défaut sont deux recherches, vingt tentatives d'import d'articles
et deux propositions de sources. Les téléchargements de découverte ont leur propre quota : un
par tentative d'import et au plus cinq par proposition de source (page, jusqu'à trois liens de flux,
puis un à trois liens d'articles dans le quota restant).
Les échecs consomment aussi ces quotas. Les tokens de recherche sont inclus dans `usage` et les
appels hébergés sont comptés séparément ; leur facturation outil s'ajoute au coût des modèles.
La réservation de tokens de recherche est estimée, pas un plafond de facture garanti.

Le bouton **Générer ma une** du frontend lance un test réel, facturable, avec le profil local.
Le rédacteur reste libre de ne pas proposer de source si aucune
n'est exploitable. La recherche est exécutée chez OpenAI ; collecte RSS, extraction et stockage
restent sur le serveur Python.
Le champ de requête `discover_web: true` demande au moins une tentative de recherche avant
finalisation quand l'outil est activé ; sa valeur par défaut est `false`. Un échec de recherche
reste explicite dans la trace et n'empêche pas une couverture fondée sur le catalogue disponible.
`discover_sources: true` demande aussi l'examen d'une source observée lorsque les articles sont
suffisants et que les tours le permettent. Cette tâche est secondaire et peut être différée.
Le frontend active `discover_web` et `discover_sources` pour enrichir les propositions de sources
lors des générations. Une requête directe à l'API peut désactiver ces options.
Les pages reconnues comme répertoires RSS sont
conservées parmi les liens de découverte mais ne sont pas importées comme articles.

Le véritable caractère agentique réside dans cette boucle de choix d'actions, pas dans le résumé.
Les tests utilisent des décisions scriptées pour valider la mécanique ; elles ne sont jamais utilisées
comme faux agent en production. Sans configuration LLM, la génération répond HTTP 503.

## Endpoints

| Méthode | Route | Usage |
|---|---|---|
| GET | `/health` | État, capacités configurées et volumes de données |
| POST | `/v1/ingest` | Collecter des sites web, flux RSS/Atom et/ou Hacker News |
| GET | `/v1/articles?limit=50` | Métadonnées du catalogue |
| POST | `/v1/covers` | Créer et persister une couverture à partir d'un profil |
| GET | `/v1/covers/{id}` | Relire une couverture et sa trace |
| POST | `/v1/feedback` | Enregistrer un événement sur un article de la couverture |

Exemple de feedback :

```json
{
  "user_id": "identifiant-local-de-la-couverture",
  "cover_id": "identifiant-retourné",
  "article_id": "identifiant-d-un-article-de-la-couverture",
  "kind": "useful"
}
```

`status=complete` : le modèle a validé le nombre demandé ; `partial` : il en a retenu moins ;
`fallback` : échec ou budget épuisé, sélection déterministe des fiches disponibles. Un fallback vide
reste possible si aucun contenu exploitable n'est disponible. Ce statut ne prouve pas la qualité
éditoriale : elle doit être évaluée auprès de lecteurs.

## Limites et budgets

Les fiches de lecture se terminent par `cited_sources` : jusqu'à huit sources citées que le
modèle juge pertinentes pour approfondir le sujet ou découvrir de futures lectures. Chaque piste
contient un nom, un motif de pertinence, un passage du texte qui justifie l'attribution et une URL
uniquement si elle est disponible dans le contenu fourni. Une simple mention ou un lien anecdotique
ne suffit pas ; la liste reste vide si aucune source ne convient. Les liens du corps de l'article
sont conservés lors des nouvelles extractions pour aider cette identification.
Les citations sans passage justificatif sont écartées ; les URL non observées sont retirées.
Ces pistes figurent à la fin des fiches dans `/admin` et dans la section « Sources citées pertinentes »
de `/admin/covers`, avec leur article d'origine, y compris pour les fiches réutilisées depuis le cache.
Elles sont enregistrées dans le journal sans déclencher de collecte ni d'ajout automatique de source.
Le cache des résumés est versionné (`brief-v6`) ; les anciennes éditions restent consultables.
Pour les articles déjà extraits sans liens, le modèle peut encore relever des sources nommées,
mais la récupération des liens nécessite une nouvelle collecte du contenu HTML.

- Une génération à la fois par processus API, délai global de 300 secondes. Pas encore de file de jobs.
- Nombre de tours, résumés, recherches web et téléchargements borné dans `.env`.
- `MAX_TOKEN_BUDGET` borne une **réservation estimée conservatrice** (octets UTF-8 du texte/schema +
  sortie maximale) avant chaque appel. Ce n'est ni un prix en euros ni un décompte exact du fournisseur.
  Les tokens réels retournés sont enregistrés dans `usage`. Les tentatives LLM ne sont pas réessayées
  automatiquement. Un appel en échec peut quand même avoir été facturé par le fournisseur.
- Les téléchargements refusent réseaux privés/locaux, ports non standard et identifiants d'URL.
  La résolution DNS validée est celle utilisée pour la connexion ; chaque redirection est revalidée.
  Taille décompressée et délais sont limités. Les paywalls ne sont pas contournés.
- Les articles sont traités comme des données non fiables dans les prompts. Les outils n'offrent
  aucun accès aux fichiers locaux ou à des actions arbitraires. Cela ne garantit pas l'immunité du LLM
  aux manipulations éditoriales du contenu.
- Les extraits et textes très longs sont signalés comme incomplets. Les résumés doivent encore être
  évalués pour leur fidélité ; il n'y a pas de vérification factuelle automatique.
- La récupération initiale reste lexicale ; la présélection LLM comprend les intérêts dans les deux
  langues, sans garantie exhaustive sur le corpus. Le regroupement est basé sur les titres et le
  jugement du rédacteur, pas une détection fiable des
  événements. `pgvector`, embeddings et reranker sont des étapes suivantes à mesurer contre ce socle.
- Le catalogue en mémoire est limité aux derniers `MAX_CATALOG_ARTICLES` collectés. À plus grande
  échelle, déplacer la récupération des candidats vers des requêtes/index PostgreSQL.
- Le cache est partagé et versionné ; pas encore de verrou distribué pour éviter deux résumés
  simultanés du même article dans plusieurs processus. Les sources ne sont pas encore planifiées.
- Le profil est fourni à chaque requête. La mémoire inférée et les préférences apprises ne sont pas
  encore implémentées. Un article présenté n'est pas considéré comme lu sans événement explicite.
- API de développement locale, **sans authentification** : `user_id` n'est pas une preuve d'identité.
  Ajouter auth, quotas globaux et traitement des données personnelles avant une exposition publique.

## Tests

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
# Avec PostgreSQL démarré : tests réels du repository et du pipeline persistant.
$env:TEST_DATABASE_URL = 'postgresql://broadwai:broadwai@localhost:5432/broadwai'
uv run pytest tests/test_postgres.py -q
```

Les tests PostgreSQL créent puis suppriment leur propre schéma unique. Sans `TEST_DATABASE_URL`,
ils sont marqués ignorés. La CI fournit un service PostgreSQL et exécute toute la suite sans clé LLM.
Les autres tests n'ont besoin ni de réseau ni de crédits : recherche, appels LLM et collecte sont
doublés aux frontières pour vérifier décisions, refus de finalisation, erreurs, budgets et cache.

Vérification réseau facultative, sans base ni LLM : `uv run python -m scripts.smoke_retrieval`.
Elle lit un flux réel et tente d'extraire un de ses articles ; son résultat dépend des sites.

Pour tester une collecte HTML sans base ni LLM :
`uv run python -m scripts.smoke_website https://simonwillison.net/ --limit 2`.
`--save-pages data/website-smoke` conserve le HTML téléchargé pour examiner les erreurs de détection.

## Évaluation sur quatre profils nouveaux

`examples/evaluation-profiles.json` contient quatre profils indépendants des anciens essais :
cuisine, création de jeux indépendants, jardinage urbain en français, musique et prise de son.

```powershell
uv run python -m scripts.evaluate_covers --output data/evaluation/mon-essai
# Une seule génération ciblée :
uv run python -m scripts.evaluate_covers --only cuisine --output data/evaluation/cuisine
```

Cette commande effectue de vrais appels payants avec la configuration locale. Elle appelle
directement la pipeline, persiste les éditions et fiches dans PostgreSQL et partage le catalogue
et le cache. Lancer un seul évaluateur et éviter une génération simultanée dans le lecteur.
Chaque dossier contient les requêtes, empreintes du code, métriques, résultats complets et
diagnostics même en cas d'échec. Aucun réessai automatique ; un dossier existant n'est pas écrasé.
La cible est de 18 articles, avec les budgets habituels. Un résultat partiel ou vide reste un
échec de complétude, même si les quotas et langues sont respectés.

Les vérifications automatiques portent sur les identifiants, langues, quotas et dates des
actualités ; elles ne mesurent pas à elles seules la pertinence ou la fiabilité des articles.
Les comparaisons successives ne sont pas des tests A/B isolés : catalogue et cache évoluent.

Les corrections issues de ces essais conservent les besoins correctement cités lorsqu'un autre
élément de l'interprétation est invalide. Une classification temporelle provisoire défavorable
peut être réexaminée sur un texte intégral déjà disponible ; la fiche doit ensuite satisfaire
les mêmes règles de validité et de date. Les variations normales d'une méthode relèvent des
réserves, sans être automatiquement assimilées à une obsolescence. Le cache `brief-v6` évite de
réutiliser les jugements des anciens prompts. Le modèle peut encore mal classer la temporalité.
Les noms de langues et variantes régionales sont normalisés pour les filtres (français/fr-FR → fr,
English/en-US → en). Si tous les appels modèles échouent sans aucun article disponible, l'API
renvoie HTTP 502 plutôt que d'enregistrer une couverture vide comme succès technique.

## Fichiers principaux

- `broadwai/pipeline.py` : orchestration et validation de la couverture.
- `broadwai/retrieval.py`, `website.py`, `network.py` : collecte, extraction et accès réseau.
- `broadwai/llm.py` : prompts, modèles structurés, budget et adaptateur OpenAI.
- `broadwai/ranking.py` : présélection BM25 et diversification.
- `broadwai/store.py`, `schema.sql` : persistance PostgreSQL.
- `broadwai/api.py` : API et cycle de vie.

Références d'intégration : [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
[Hacker News API](https://github.com/HackerNews/API),
[OpenAI Web Search](https://developers.openai.com/api/docs/guides/tools-web-search),
[Trafilatura](https://trafilatura.readthedocs.io/en/latest/usage-python.html),
[Psycopg](https://www.psycopg.org/psycopg3/docs/basic/usage.html).

## Comptes de démonstration et bibliothèque

L’interface propose une création de compte et une connexion par e-mail et mot de passe
**fictif**. Aucun e-mail n’est envoyé ; le mot de passe reste dans le formulaire et n’est
ni conservé, ni transmis, ni vérifié. Le compte (identifiant, prénom, e-mail) et la session
sont locaux au navigateur. Ce prototype n’est pas une authentification : les identifiants
de compte dans l’API sont déclaratifs, et l’administration reste sans contrôle d’accès.
Un autre navigateur ou appareil ne retrouve donc pas automatiquement le même compte.

Le premier compte créé reprend l’identité et les préférences de l’ancien lecteur anonyme.
Les comptes suivants ont chacun leurs préférences, likes, historique et bibliothèques séparés.
« Ma bibliothèque » organise les articles en collections nommées, comme des playlists.
Le marque-page d’un article ouvre un sélecteur : cochez une ou plusieurs bibliothèques,
ou créez-en une sur le moment. Chaque bibliothèque peut être renommée, décrite ou supprimée.
Retirer un article d’une bibliothèque conserve ses autres classements et l’article d’origine.
Les titres ouvrent directement la page de l’éditeur, dans leur langue d’origine.

Les collections et leurs articles sont persistés dans PostgreSQL (`article_collections`,
`collection_articles`), avec une copie des métadonnées pour conserver les sauvegardes même
si le catalogue évolue. Les anciennes revues sauvegardées sont converties en bibliothèques
une seule fois au démarrage ; les anciens favoris locaux sont importés dans « À lire ».
La déconnexion et le redémarrage du serveur ne suppriment pas ces collections.

`GET` et `POST /v1/collections?user_id=…` listent ou créent les bibliothèques.
`GET`, `PATCH` et `DELETE /v1/collections/{id}?user_id=…` les consultent ou les modifient.
`PUT` et `DELETE /v1/collections/{id}/articles/{article_id}?user_id=…` gèrent leur contenu.
Un éventuel `cover_id` dans l’ajout doit appartenir au compte déclaré et contenir l’article.
Les anciennes routes `/v1/library` restent disponibles pour compatibilité.
Le montage de couverture réutilise jusqu’à trois images des articles via le proxy existant,
avec titre, date, rubriques et palette stable. La tranche reprend titre et nombre d’articles. Aucune image
n’est générée par IA ; si les images sont absentes ou indisponibles, une composition
typographique les remplace. Les visuels restent dépendants des images accessibles des sources.

## Likes et profil de lecture appris

Un petit cœur en tête de chaque article permet d’aimer ou de retirer un like.
Les favoris restent séparés. Les likes sont persistés par profil local dans PostgreSQL
(`article_likes`), sans fenêtre, questionnaire ou appel modèle au clic.
`GET/PUT /v1/likes` lit ou modifie ce choix ; seuls les articles d’une édition du profil
fourni sont acceptés. Comme le reste de l’API locale, ceci ne remplace pas une authentification.

Les 100 derniers articles aimés composent automatiquement une mémoire de lecture :
sujets précis pondérés par le nombre d’articles, formats, niveaux de profondeur et exemples
avec titres/résumés. Les doublons ne renforcent pas un thème. Retirer un like retire aussi
son influence. La mémoire est recalculée depuis les likes, sans profil obsolète en cache.
Lors de la prochaine génération, le serveur ajoute cette mémoire au profil : elle contribue
au classement et à l’interprétation des besoins par le rédacteur, après les préférences
explicites. Aucun attribut personnel sensible ou accord avec les opinions des articles
ne doit en être déduit. Le détail apparaît dans le profil de la trace de génération.
Les anciennes affinités du nuage ne sont plus utilisées.

### Préserver une une généraliste

Chaque rubrique explicitement choisie reste dans le profil éditorial, même lorsque les notes
ou les likes précisent surtout un autre sujet. Le pool de présélection réserve de la place aux
différents intérêts et les fiches sont préparées en alternant les rubriques. Le modèle rattache
chaque candidat à une rubrique générale (`interest_id`) selon son sujet central ; les sous-thèmes
et les rubriques de mise en page ne créent pas de quotas supplémentaires.

Pour plusieurs intérêts, une rubrique reçoit au maximum la moitié des places si deux intérêts
sont choisis, un tiers à partir de trois (arrondi supérieur). La cible minimale est de deux
articles par intérêt lorsque la taille de la une le permet. Les recherches privilégient les
rubriques manquantes. Ces contrôles s'appliquent aussi à la sélection de secours ; une pénurie
reste signalée dans les avertissements et la trace plutôt que comblée par un seul thème.
La classification sémantique des articles repose sur le modèle ; les quotas sont appliqués en code.
