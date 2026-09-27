# Kiosque — presse personnalisée

## Interface lecteur — React connecté au backend

Le projet s’appelle **Kiosque**. L’interface [`frontend/`](frontend/README.md)
affiche les vraies couvertures de l’API : profil local sans compte, génération de
15 à 20 articles, historique, rubriques, liens éditeurs, favoris et retours de lecture.
Les éditions sont préparées automatiquement chaque jour à 4 h, heure de Paris,
pour les profils enregistrés côté serveur. Le bouton **Refaire ma une** permet de demander
une nouvelle sélection lorsque l’édition actuelle ne convient pas. Un commentaire facultatif
permet d’expliquer le motif avant de lancer la préparation ; s’il est renseigné, il guide cette sélection et celles des
**sept jours suivants**, sans modifier les notes saisies dans les préférences.

La régénération est limitée à **une tentative par utilisateur et par jour civil, heure de Paris**,
avec remise à disposition à minuit. La réservation et le motif sont enregistrés ensemble dans
PostgreSQL (`edition_regenerations`) avant les appels aux modèles. La contrainte unique empêche
les doubles clics et demandes simultanées sur plusieurs processus ; recharger la page ou
redémarrer le serveur ne réinitialise pas le quota. Une tentative échouée reste consommée,
mais le motif est conservé pour les éditions suivantes. Les erreurs de validation, l’absence
de modèle ou une préparation déjà en cours ne consomment pas la tentative.

La nouvelle sélection écarte les articles de l’édition remplacée, conservée dans les archives.
Les motifs récents et les titres de l’édition concernée sont fournis au rédacteur comme contexte ;
l’interprétation des besoins utilise le motif comme une demande explicite, avec priorité aux
motifs récents lorsqu’ils se contredisent. Les titres ne deviennent pas des préférences implicites.
Le résultat reste soumis à la qualité et à la disponibilité du catalogue : il peut être partiel.
Les motifs expirent du contexte de génération après sept jours. L’API dédiée expose
`GET /v1/readers/{user_id}/regeneration` (disponibilité) et
`POST /v1/readers/{user_id}/regeneration` (`cover_id`, `reason` facultatif, 2 à 1 000 caractères
si renseigné). Un commentaire absent ou vide ne crée pas de préférence de lecture ; la limite
quotidienne s’applique aussi aux régénérations sans commentaire.
Les générations automatiques à 4 h et les outils de génération administrateur restent distincts.

Dans **Administration → Éditions & planification**, choisir un lecteur puis cliquer sur
**Réinitialiser « Refaire ma une »** redonne une tentative pour le jour courant, sans appel
aux modèles. L’action est bloquée pendant une régénération active ; une tentative abandonnée
depuis plus de dix minutes peut être débloquée. L’historique des tentatives, les commentaires
et les éditions sont conservés. La réinitialisation marque la tentative comme libérée et
l’index unique maintient une seule tentative non réinitialisée par lecteur et par jour.
API : `POST /v1/admin/readers/{user_id}/regeneration/reset`.

Pendant la régénération, le lecteur affiche une **barre de progression estimée** et un temps
restant approximatif, dans la fenêtre et dans le journal. L’estimation utilise la médiane des
20 dernières régénérations réussies de ce lecteur (entre 30 secondes et 5 minutes), ou 2 minutes
sans historique exploitable. Elle est enregistrée au départ avec l’heure de lancement et
se retrouve après rechargement. Le statut est actualisé toutes les 2,5 secondes pendant la
préparation. La barre reste plafonnée à 95 % tant que le serveur n’a pas confirmé la fin ;
si l’estimation est dépassée, le message indique que la préparation se poursuit.

La une affiche les visuels des articles, y compris les brèves : métadonnées Open Graph/Twitter
en priorité, puis images structurées JSON-LD ou images du texte. La récupération prend aussi
en charge `picture`, `srcset` et les attributs de chargement différé. Jusqu’à cinq URLs
distinctes sont essayées si une image échoue au téléchargement ou au contrôle ; la première
image utilisable est conservée pour les prochaines lectures. Un clic sur le titre ou le visuel
ouvre directement l’article chez l’éditeur dans l’onglet courant. Le bouton « Fiche & avis »
conserve l’accès au résumé et aux retours. Les images indisponibles laissent une carte textuelle ; les
brèves gardent une présentation compacte. Les éditions déjà enregistrées sont illustrées à leur
ouverture, sans régénérer les résumés.
Le backend sert les images des articles sélectionnés via `/v1/articles/{id}/image`,
avec contrôle des destinations publiques, de la taille et du format raster. Le cache
en mémoire dure six heures (32 Mo/128 entrées au maximum), les échecs cinq minutes.

Avant le premier affichage, **GPT-5.4 nano** contrôle la pertinence visuelle par rapport
au titre et à 1 000 caractères de l'article. Seule une miniature JPEG sans métadonnées,
limitée à **768 pixels et 100 Ko**, est transmise à OpenAI ; le visuel affiché conserve
sa qualité d'origine. Réponse JSON minimale (`keep`, `reject`, `uncertain`), plafond de
32 tokens, raisonnement désactivé, aucun outil ni relance automatique du SDK.
`keep` autorise l’image. Un verdict `uncertain` l’autorise aussi si la page de l’article
confirme explicitement le choix de l’éditeur dans ses métadonnées Open Graph, Twitter,
JSON-LD ou `image_src`. Cette règle conserve les illustrations symboliques sans exiger une
correspondance photographique littérale avec le texte. Une image trouvée uniquement dans le
corps reste soumise à `keep`. Les refus explicites, erreurs, formats invalides et animations
sont toujours exclus. Une erreur de contrôle ne peut être réessayée qu’après 24 h.
Les anciens verdicts sont réutilisés : cette nouvelle règle ne déclenche pas de réévaluation
payante des images déjà contrôlées. Les anciennes absences d’image ne bloquent plus une
nouvelle recherche après expiration du cache négatif de cinq minutes.

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

## Feedback et préférences de lecture

Le bouton **Écrire à Kiosque** (anciennement « Orienter mes lectures ») ouvre le
« Courrier du lecteur » : un message libre envoyé au chatbot et une fiche lecteur
consultable à la demande via **Ma fiche**.
Kiosque interprète la demande avec le modèle économique, répond et met à jour les
préférences réellement utilisées par la génération. Le lecteur peut demander de découvrir,
favoriser, réduire ou exclure un contenu, corriger une envie ou demander de l'oublier.
La durée et les nuances sont déduites du message ; une ambiguïté appelle une question.
Les réglages de prénom, langue et taille de l'édition restent dans les préférences.

Les échanges et changements sont enregistrés ensemble dans PostgreSQL. La fiche n'affiche
une confirmation qu'après enregistrement ; les changements sont atomiques, bornés à
12 préférences actives et protégés contre les corrections concurrentes. Renvoyer le même
identifiant de message restitue la réponse enregistrée sans réappliquer les changements.
Les 30 derniers échanges restent consultables ; les 6 derniers sont fournis au chatbot.
Chaque nouveau message utilise un appel IA payant, sans relance automatique, avec 2 500
tokens de sortie maximum. Aucun article ni édition n'est généré par ce parcours.

Dans une fiche, **Expliquer ou préciser pour la suite** enregistre le motif et un texte
libre. Par défaut, l'avis porte uniquement sur cet article. La case **Ajuster aussi mes
prochaines lectures** permet de définir explicitement une préférence associée. Les avis
et leurs explications sont rechargés à l'ouverture de l'édition.

Effet lors de la génération suivante :

- `diversify` : quelques places partagées entre toutes les demandes de découverte,
  au maximum `ceil(size / 6)` (3 pour 18 articles), en complément des intérêts habituels.
- `more` : priorité renforcée mais bornée dans la sélection, sans supprimer les autres intérêts.
- `less` : priorité réduite et au maximum `max(1, floor(size / 6))` articles correspondants
  par règle (3 pour 18 articles).
- `exclude` : rejet obligatoire, y compris en Exploration et dans la sélection de secours.

Les seuils sont des choix initiaux du produit à évaluer auprès de lecteurs. Les règles
ne dispensent jamais de la pertinence, des quotas de sources ou des contrôles de validité.
Une édition peut rester partielle. Le bilan **Vos demandes dans cette édition** affiche
le nombre d'articles correspondants et les demandes non couvertes ; la trace conserve
les règles et versions réellement appliquées, ainsi que les évaluations et les retraits.

Sources non qualifiées et formats/niveaux connus ont des contrôles déterministes. Les
sujets, angles et nuances sont évalués à partir des fiches, par le modèle économique,
avec des citations vérifiées dans les données fournies. Ce jugement sémantique reste
faillible. Une évaluation manquante, ambiguë ou en erreur ne permet pas de contourner
une exclusion. Les autres demandes peuvent être partiellement satisfaites et le bilan
le signale. Au plus 12 règles sont actives ; les évaluations sont regroupées (8 articles
et 24 paires article/règle maximum par appel), limitées à 10 appels, dans le budget de
tokens existant. Les avis sur un article et les routes de préférences structurées ne
déclenchent pas d'appel LLM ; les messages du Courrier du lecteur, eux, sont lus par l'IA.

La migration PostgreSQL est additive au démarrage : table `reader_preferences` et champs
`reason`, `comment`, `preference_id` de `feedback`. Les règles et éditions persistent
côté serveur sous l'identité locale existante. Les corrections utilisent une révision
pour refuser les écrasements concurrents (HTTP 409). La génération prend un instantané ;
une correction pendant son exécution reste disponible pour la suivante. Une demande
ponctuelle est marquée appliquée avec l'enregistrement atomique d'une édition non vide,
même partielle ; un échec ou une édition vide ne la consomme pas.

API : `GET/POST /v1/readers/{user_id}/preferences`,
`GET/POST /v1/readers/{user_id}/messages`,
`PUT/DELETE /v1/readers/{user_id}/preferences/{id}` (révision obligatoire),
`GET /v1/readers/{user_id}/feedback/{cover_id}` et `POST /v1/feedback` enrichi.
L'identité locale reste sans authentification : ces routes sont destinées au serveur
local de confiance, comme le reste de l'API.

Pour tester le parcours dans un environnement isolé, compiler le frontend puis lancer
`python -m tests.serve_feedback_fixture` et ouvrir `http://127.0.0.1:8012/reader/`.
Cette fixture utilise seulement les données simulées des tests, sans base ni modèle payant.

## Backend agentique (package `broadwai`)

Première implémentation de la collecte d'articles et de la création d'une couverture personnalisée.
Python 3.12+, FastAPI, PostgreSQL, SDK OpenAI Responses. Aucun appel LLM payant au démarrage.

Pour reprendre le travail avec un autre agent : [contexte et passation du projet](PROJECT_HANDOFF.md).

## Un journal de 15 à 20 articles

`POST /v1/covers` demande désormais **18 articles par défaut** (champ `size`, maximum 20).
Le quota par source vaut trois par défaut (au moins six domaines pour 18 articles).
Le profil se règle dans le frontend. Celui-ci présente la une par rubriques, avec les titres
originaux des éditeurs, sans traduction, même pour les éditions déjà enregistrées. Les titres et
images ouvrent directement l'article dans un nouvel onglet. Le bouton « Fiche & avis »
ouvre les détails et les retours ; les résumés sont aussi consultables dans `/admin/covers`.
L’inspecteur ouvre la couverture sélectionnée dans le
frontend via `/reader/?cover={id}`.

La préparation se déroule ainsi :

1. Interprétation des notes en besoins prioritaires, puis classement lexical tenant compte de
   ces besoins et des notes. Pool diversifié de 96 titres/extraits maximum, avec une place pour
   les articles récents que les mots-clés bilingues peuvent manquer.
2. Avant cet appel, récupération des textes manquants sur ce pool : trois téléchargements
   simultanés, quota `MAX_FETCHES`, délai par lot `PREFETCH_TIMEOUT` (30 secondes par défaut).
   Les textes déjà extraits sont réutilisés. Les pages inexploitables sans extrait suffisant
   sont retirées ; les extraits restants sont explicitement signalés au modèle. Un échec de
   téléchargement n'est pas retenté automatiquement lors du résumé dans la même génération.
   Un appel au rédacteur définit les rubriques et choisit les articles prometteurs. Son score
   éditorial est une appréciation du modèle, pas une probabilité. Sous 70/100, pas de résumé.
3. Fiches structurées du modèle économique à partir des textes récupérés, réutilisables entre utilisateurs ;
   jusqu'à trois préparations simultanées. Le rédacteur reçoit le résumé et les réserves,
   sans répéter les points clés ni transmettre tous les textes complets.
4. L'agent évalue les fiches et les manques, puis choisit une recherche catalogue, web ou de sources,
   une lecture approfondie, une proposition de source, ou la finalisation. Une recherche vide
   appelle un changement de requête ; un domaine en échec répété est évité pendant ce run.
5. Application des quotas aux choix du modèle, en conservant leur ordre éditorial et en traçant
   les retraits ; validation des identifiants, du nombre et des doublons. Pour une
   sélection d'au moins 15 articles directs : 3 à 5 rubriques, au moins deux articles chacune.
   Si la sélection directe manque, une rubrique **Exploration** complète les places libres
   avec des thèmes connexes mais différents et un lien explicite avec les intérêts.
   Une sélection courte est refusée s'il reste des moyens de chercher. Après épuisement,
   le résultat reste explicitement partiel plutôt que de promettre un remplissage pertinent.

Les défauts permettent 48 nouveaux résumés, 10 décisions, 4 passes de recherche web et ajoutent
une interprétation des notes si présentes, une planification et au plus 4 filtres de recherche.
Les besoins interprétés doivent citer le profil, puis alimentent le classement avant le plan.
Le filtre a un prompt autonome et un seuil cohérent avec `MIN_EDITORIAL_SCORE`. Le rédacteur utilise
le raisonnement `low` sur GPT-5 ; le modèle de résumé conserve son réglage économique.
Les téléchargements préalables sont limités à 40, les imports web à 20 tentatives.
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
composée. La proposition isolée de sources reste secondaire ; une recherche de sources peut
en revanche fournir des articles pour combler une couverture incomplète.
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

### Administration des éditions

Les commandes techniques sont accessibles dans `/admin/covers` depuis **Éditions &
planification** : modèles configurés, préparation en cours, profils synchronisés, échéance
quotidienne, génération manuelle et historique filtré. **Actualiser** ne génère rien.
`GET /v1/admin/editions?limit=100&offset=0` fournit ce tableau de bord, sans clé API.
`POST /v1/admin/readers/{user_id}/covers` prépare une édition à partir du profil enregistré,
avec les quotas et verrouillages habituels, sans décaler sa préparation quotidienne.

Le lecteur conserve ses archives, mais ne présente plus le bloc « Mes éditions », les
liens admin, les coûts, les diagnostics de sélection ou les messages de configuration.
Quand le build est installé, la racine du backend ouvre le lecteur ; l’administration
reste accessible explicitement par `/admin`.

### Inspection des couvertures

L’inspecteur présente d’abord le résultat (articles retenus/demandés, sources, durée et coût),
puis cinq étapes expliquées : profil et catalogue, examen des titres/extraits, préparation
des fiches, recherches et arbitrages, édition enregistrée. Chaque étape est dépliable.
Le tableau « Que sont devenus les articles ? » permet de chercher par titre, source ou motif,
de filtrer le résultat et d’ouvrir le parcours individuel avec les événements et la fiche.
Les anciennes « présélections » sont nommées « files de préparation » : leurs membres ne sont
pas forcément préparés, validés ou publiés. Les compteurs dédupliquent les articles entre
passages, les retraits restent rattachés à leur tentative et les données absentes ne sont
pas reconstruites. La page affiche un bilan après génération, sans suivi en direct.

`/admin/covers` affiche l'historique et le déroulement enregistré de chaque couverture. Le lien
« Éditions & planification » est disponible dans l'admin. `GET /v1/covers?limit=30&offset=0` liste
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

Le catalogue complet `examples/sources-all-topics.json` propose **1 019 sources vérifiées** pour les
**20 sujets de l'inscription**, sur 508 domaines éditeurs (285 francophones et 734 anglophones).
Chaque sujet dispose de 26 à 147 sources. La sélection associe institutions, recherche, rédactions,
praticiens, **huit chaînes YouTube** et **six émissions Radio France**, avec leur provenance officielle.
Une source est un flux ou une rubrique : ce chiffre ne représente pas 1 019 médias indépendants.

L'[annuaire lisible](http://127.0.0.1:8010/admin/assets/sources.html), accessible depuis **Nos sources**
dans le journal, offre recherche, filtres, cartes, tableau, fiches de provenance et export CSV.
La copie autonome [`examples/sources.html`](examples/sources.html) fonctionne aussi hors ligne.

`examples/source-catalog.json` conserve les thèmes, langues, raisons de sélection, limites d'accès
et résultats datés des vérifications, y compris les candidats écartés. Le guide
[`examples/SOURCES.md`](examples/SOURCES.md) donne la couverture détaillée et les commandes pour
exporter un seul sujet ou revérifier les flux. Les anciens fichiers `sources.json` et
`sources-economy.json` restent utilisables.

Pour ajouter les sources vérifiées et collecter leurs premiers contenus via l'API :

```powershell
uv run python -m scripts.import_source_catalog --base-url http://127.0.0.1:8010 --collect
uv run python -m scripts.build_source_directory --base-url http://127.0.0.1:8010
```

Le script importe uniquement les entrées actives au statut `ok`, conserve les sources déjà remplies
et respecte leur mise en pause. Il reprend les sources enregistrées mais restées sans contenu après
une interruption. Les ajouts de cette extension collectent jusqu'à cinq contenus par source.
Le rapport progressif est écrit dans `data/catalog-import.jsonl`. Pour ajouter des candidats,
exécuter d'abord `scripts.validate_source_catalog --pending-only`, puis revoir les résultats.
L'ancien `scripts.seed_sources` reste compatible avec les listes JSON simples.

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
le profil est alors synchronisé pour la préparation quotidienne de 4 h. Le frontend construit la requête à partir du profil local ;
les thèmes utilisent des mots-clés français et anglais car BM25 ne traduit pas les intérêts.

Pour un premier test réel, renseigner les trois variables LLM dans `.env`, redémarrer le serveur,
puis vérifier que `/health` indique `llm_configured: true`. La recherche web peut être désactivée
avec `WEB_SEARCH_ENABLED=false`.
`POST /v1/covers` renvoie actuellement la couverture à la fin du traitement (maximum 300 secondes),
avec sa trace. Cette API manuelle reste disponible pour les outils de développement ; le lecteur
suit désormais la préparation automatique sans maintenir une requête ouverte.
Les éditions déjà générées se consultent depuis son historique et leurs traces dans l'inspecteur.

## Éditions quotidiennes à 4 h

Le backend FastAPI prépare une édition par profil chaque jour à **4 h, Europe/Paris**,
y compris lors des changements d’heure. Les sujets, langues, niveau, contexte et format
sont synchronisés via `PUT /v1/readers/{user_id}/daily-edition`. Les profils existants
sont inscrits lors de leur prochaine visite ; une première inscription programme le
prochain 4 h, sans appel payant immédiat. Les modifications suivantes gardent cette échéance.
Les likes et les demandes du Courrier du lecteur sont relus lors de la préparation.

PostgreSQL conserve les profils et une tentative unique par compte et date, même avec
plusieurs serveurs. Le planificateur vérifie les échéances toutes les 30 secondes ; les
éditions sont mises en file et peuvent se terminer après 4 h. Le backend et PostgreSQL
doivent rester actifs ; en local, l’ordinateur doit être allumé et éveillé. Après un arrêt,
seule la dernière échéance manquée est rattrapée, sans produire tout un historique.
Une tentative échouée ou interrompue n’est pas refacturée automatiquement le même jour ;
l’édition précédente reste lisible et le statut signale l’échec.

`GET /v1/readers/{user_id}/daily-edition` expose l’état et la prochaine échéance.
`DAILY_EDITIONS_ENABLED=false` suspend le planificateur sans perdre les profils.
À l’ouverture du journal, la dernière édition est chargée ; un onglet ouvert vérifie les
nouveautés chaque minute et lors du retour à la page. Un lien explicite vers une archive
reste sur l’édition choisie. Aucun appel payant n’est déclenché par ces consultations.

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
   JSON validée : `search_catalog`, `search_web`, `search_sources`, `read_article`,
   `propose_source` ou `finalize`.
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

`search_sources` permet aussi de chercher directement des blogs d'auteurs ou de chercheurs,
des revues et des sites spécialisés sur un besoin mal couvert, sans auteur ou domaine prédéfini.
Contrairement à la recherche d'articles, elle accepte les pages d'accueil, de rubrique et les flux,
uniquement à partir des références retournées par le fournisseur. Le backend valide chaque source,
repère jusqu'à trois articles réels et les soumet à l'extraction puis au filtre éditorial et aux
mêmes contrôles que les autres candidats. Ils peuvent alimenter la couverture en cours.
Si au moins un article reste candidat après les contrôles, le site/flux est proposé dans l'admin
pour les collectes futures ; aucune activation automatique. Les pages récupérées lors de la
validation sont réutilisées, et les domaines exclus sont filtrés avant téléchargement.

Par couverture, les limites par défaut sont quatre recherches partagées entre articles et sources,
vingt tentatives d'import d'articles et deux tentatives de validation/proposition de sources.
Les téléchargements de découverte ont leur propre quota : un
par tentative d'import et au plus cinq par proposition de source (page, jusqu'à trois liens de flux,
puis un à trois liens d'articles dans le quota restant).
Les échecs consomment aussi ces quotas. Les tokens de recherche sont inclus dans `usage` et les
appels hébergés sont comptés séparément ; leur facturation outil s'ajoute au coût des modèles.
La réservation de tokens de recherche est estimée, pas un plafond de facture garanti.

La préparation quotidienne utilise les crédits des modèles configurés, avec les mêmes quotas
que la génération manuelle via `POST /v1/covers`.
Le rédacteur reste libre de ne pas proposer de source si aucune
n'est exploitable. La recherche est exécutée chez OpenAI ; collecte RSS, extraction et stockage
restent sur le serveur Python.
Le champ de requête `discover_web: true` ne force plus de recherche. Si les candidats suffisent
après quotas et couvrent les besoins et rubriques, le rédacteur peut finaliser directement ;
les actions web inutiles sont bloquées avant facturation. La recherche reste disponible pour
combler un manque ou remplacer une sélection refusée. Un échec reste explicite dans la trace.
`discover_sources: true` ouvre également la recherche de sources lorsque le catalogue est trop
pauvre pour un besoin. Le rédacteur voit les manques et les domaines déjà disponibles par besoin,
et choisit entre recherche d'articles et recherche de sources. Aucune des deux n'est obligatoire.
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
- Le profil est fourni à chaque requête, complété par les préférences explicites enregistrées.
  L'apprentissage implicite à partir de clics répétés n'est pas activé : un avis isolé ne change
  pas les goûts. Un article présenté n'est pas considéré comme lu sans événement explicite.
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

## Profils sur cet appareil et bibliothèque

L’interface permet de créer ou retrouver un profil sur cet appareil à partir du prénom
et de l’e-mail. Le faux champ de mot de passe et le texte de démonstration ont été retirés.
Aucun e-mail n’est envoyé. L’identité et la session restent locales au navigateur.
Cela ne constitue pas une authentification serveur : les identifiants de compte dans
l’API sont déclaratifs, et l’administration reste sans contrôle d’accès. La séparation
visuelle lecteur/admin doit être complétée par une authentification et des autorisations
avant une ouverture publique. Un autre appareil ne retrouve pas automatiquement ce profil.

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

## Vidéos YouTube dans la une

Le lecteur demande désormais une édition mixte : articles et jusqu’à trois vidéos,
sélectionnés ensemble selon le profil, les langues, les exclusions et les likes.
Les vidéos pertinentes rejoignent les rubriques existantes ; le seuil éditorial reste
inchangé et aucune vidéo n’est imposée lorsque l’offre est insuffisante.

Les trois chaînes YouTube de `examples/sources.json` (ARTE, Le Monde, Veritasium)
se gèrent comme des sources RSS dans l’administration. L’import habituel des exemples
les ajoute. On peut aussi ajouter une URL `https://www.youtube.com/channel/UC…` :
elle est convertie en flux Atom. Les liens `@pseudo` ne sont pas résolus automatiquement ;
utiliser l’identifiant de chaîne ou son flux `feeds/videos.xml?channel_id=UC…`.
Les chaînes activées sont actualisées lors de la génération, au plus une fois par heure,
avec quatre requêtes simultanées, au plus huit flux par génération. Une chaîne indisponible n’empêche pas de composer la une.

Aucune clé YouTube ou Supadata n’est nécessaire. Les flux fournissent le titre original,
la description, la chaîne, la date et la miniature. La collecte récupère la durée dans
les métadonnées publiques de la page YouTube, avec quatre requêtes simultanées au maximum,
un délai de trois secondes par vidéo et réutilisation des durées déjà connues.
Seules les vidéos dont `media.duration_seconds` est strictement supérieur à 300 secondes
sont proposées dans les nouvelles éditions, quel que soit leur fournisseur. Une durée
absente ou invalide exclut la vidéo ; exactement cinq minutes est également exclu.
Les pages YouTube ne servent jamais de transcription : l’IA décrit seulement le sujet
annoncé et la fiche signale cette limite.
Les miniatures viennent de l’identifiant de la vidéo, passent par le proxy d’images borné
et ne déclenchent pas la vérification photographique payante. Le titre et la miniature
ouvrent directement YouTube. Likes, bibliothèques et mémoire de lecture acceptent ce format.

L’API `/v1/covers` accepte `discover_videos: true` pour actualiser les chaînes et
`max_videos` entre 0 et 3 (3 par défaut ; 0 exclut les vidéos même déjà collectées).
La taille demandée reste le total articles + vidéos. Les anciennes éditions restent lisibles.


## Podcasts dans la une

Les épisodes rejoignent les mêmes rubriques que les articles et les vidéos, avec
une pochette, la durée lorsqu’elle est fournie, le nom de l’émission et un badge casque
« Podcast » toujours visible. Le clic ouvre la page précise de l’épisode ; lorsqu’un
éditeur fournit seulement une page d’émission commune, il ouvre le lien audio public
propre à cet épisode. Likes et bibliothèques fonctionnent sur chaque épisode.

La découverte part des **émissions enregistrées dans les sources**, via leurs flux RSS
publics. Cette version ne recherche pas dans tout Spotify/Apple Podcasts et ne requiert
aucune clé d’annuaire. `examples/sources.json` propose La Science CQFD, Les Pieds sur terre
et Chaleur humaine. Pour ajouter une émission, choisir **Podcast (flux RSS)** dans
l’administration, saisir son flux et lancer sa collecte. On peut la mettre en pause.
Un flux RSS ordinaire contenant des pièces jointes audio est également reconnu à la
collecte ; le type Podcast active son actualisation lors de la génération des unes.

Les flux activés sont actualisés au plus une fois par heure, avec quatre requêtes
simultanées et au plus huit flux vidéo/podcast par génération. La sélection compare
le sujet de chaque épisode aux intérêts, langues, exclusions et likes du lecteur.
L’API `/v1/covers` accepte `discover_podcasts: true` et `max_podcasts: 0..2` (2 par défaut).
La taille de l’édition reste le total des trois formats ; les articles restent majoritaires
avec les réglages du lecteur. Un manque de podcasts pertinents ne force pas leur ajout.

La collecte ne télécharge ni ne transcrit l’audio. Les fiches reposent sur les descriptions
publiées et signalent l’absence de transcription. Les épisodes annoncés dans le futur
et les bandes-annonces identifiées sont ignorés. La pochette de l’épisode, ou celle de
l’émission à défaut, passe par le proxy d’images public et borné, sans contrôle photographique
payant. Les URL audio et les pochettes restent des métadonnées non fiables, jamais des
instructions données au modèle. Une panne de flux n’empêche pas la génération à partir
du catalogue disponible.
