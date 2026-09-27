## 27 septembre 2026 — Feedback explicite et préférences contrôlables

Le parcours de feedback est maintenant intégré : motif/commentaire par article, demande
indépendante « J’aimerais lire… », et liste « Ce que Kiosque retient » pour corriger,
réexpliquer et supprimer chaque préférence. Les anciennes notes ne sont pas modifiées.
Aucune préférence n’est inférée d’un clic seul. Le lecteur précise action, cible, nuances
et durée (prochaine édition non vide ou durable). Une nouvelle règle sur la même cible
remplace l’ancienne ; suppressions et remplacements conservent une marque inactive et
aucun traitement ne relit les vieux événements pour recréer ces préférences.

`preferences.py` applique trois mécanismes : diversification plafonnée à ceil(size/6)
places au total, classement borné pour more/less et plafond floor(size/6) pour less,
exclusions obligatoires. Les règles sont chargées avant la recherche et transmises au
rédacteur, aux filtres et aux recherches. Une évaluation groupée des fiches par le modèle
économique vérifie les correspondances sémantiques, avec citations et IDs contrôlés.
Les exclusions incertaines restent bloquantes, y compris en secours. Les jugements de
sujet/angle restent faillibles ; les seuils devront être évalués avec de vrais lecteurs.
Limites : 12 règles actives, 8 articles et 24 paires par appel, 10 appels maximum dans le
budget existant. Aucun appel au modèle sur les routes de feedback ou de préférences.

`preference_store.py` et migration additive dans `schema.sql` : règles par lecteur,
révisions pour les conflits, créations idempotentes, avis enrichis et consommation atomique
avec l’édition. Une correction concurrente reste active pour la génération suivante.
Le bilan de chaque édition conserve les règles appliquées et compte leurs correspondances.
Les endpoints restent locaux et sans authentification ; user_id n’est pas une identité vérifiée.

UI : `FeedbackForms.jsx`, `preferences.js`, App et fiches de lecture. Les retours se
rechargent depuis le serveur. La fixture isolée `python -m tests.serve_feedback_fixture`
sert le build sur 8012 sans PostgreSQL ni appel payant, uniquement avec les doublures de test.
Validation : 238 tests Python (PostgreSQL inclus), 13 tests JavaScript, Ruff et build Vite réussis. Parcours navigateur vérifié avec persistance des avis après rechargement et largeur mobile de 390 px. Le serveur habituel sur 8010 a été redémarré et les nouvelles routes répondent HTTP 200. Aucun appel modèle payant pour ces vérifications.

# Kiosque — contexte et passation aux agents

## Nettoyage des visuels incertains — 27 septembre 2026

À la demande de l'utilisateur, suppression des références d'images des 7 articles dont le
dernier verdict est `uncertain` : 6 références retirées, celle de Fowler était déjà absente.
Le cache mémoire a été vidé par redémarrage du serveur et le lecteur actualisé. Les 28
verdicts Nano, dont 18 `keep`, restent enregistrés pour éviter de repayer les mêmes analyses.
Textes, couvertures enregistrées et métadonnées des autres articles inchangés, vérifiés par
empreintes avant/après. Les 7 routes image répondent 404 ; la couverture courante conserve
ses 18 articles avec les 2 visuels concernés absents. Aucun nouvel appel modèle.
Audit et sauvegarde des seules métadonnées retirées :
`data/uncertain-image-cache-purge-20260926T222837Z.json`.

## Correctif logo Martin Fowler — 27 septembre 2026

Dans l'édition de 18 articles `f1fc111f9f8d42b78a6d949bfd0a812e`, l'article
`d9fbb5d07fdb6b984bd11410` avait pour visuel `https://martinfowler.com/logo-sq.png`
(144 x 144). Le site le déclare en Open Graph et l'article ne contient pas d'illustration.
La carte l'agrandissait et le recadrait. À la vérification, Nano l'a classé `uncertain`.
Le collecteur exclut désormais les chemins explicitement nommés logo/favicon/avatar,
y compris dans les métadonnées. Le service réexamine les anciennes références de ce type
pour trouver une vraie image ou enregistrer son absence, sans appeler Nano sur le logo.
L'article reste affiché sans illustration ; texte et cache de résumé préservés.
91 tests ciblés passent. Diagnostic : `data/fowler-image-diagnostic.json`.

## Visuels des articles et contrôle Nano — 26 septembre 2026

Le lecteur affiche les images éditeurs sur la une et les fiches de lecture, avec attribution
et repli textuel si indisponibles. Extraction dans `images.py` : Open Graph/Twitter, JSON-LD
correspondant à la page, puis image substantielle du corps. Les collectes enregistrent les
métadonnées ; les anciennes éditions les découvrent à l'ouverture.
`/v1/articles/{id}/image` sert les formats raster vérifiés via `PublicFetcher` et un cache
borné (6 h, 32 Mo/128 entrées, échecs 5 min, 4 téléchargements concurrents).
L'enrichissement JSONB est atomique et ne change pas l'empreinte de contenu ni le cache des fiches.

Avant affichage, `image_review.py` compare les pixels au titre et aux 1 000 premiers caractères
du texte avec `gpt-5.4-nano`. JPEG <=768 px et <=100 Ko avant encodage base64, métadonnées
retirées, 32 tokens de sortie maximum, raisonnement `none`, réponse JSON limitée au verdict.
La qualité du visuel affiché reste celle de l'original. Seul `keep` autorise l'affichage ;
`reject`, `uncertain`, erreurs et animations restent masqués. Le texte alternatif n'est pas
envoyé au modèle pour éviter qu'une légende erronée influence l'analyse des pixels.

Cache persistant `image_reviews` : article, contexte envoyé, miniature, modèle, version.
Réservation atomique entre workers, pas de retry SDK ; erreur réessayable après 24 h,
réservation interrompue après 10 min. Les usages/coûts et tentatives précédentes sont conservés.
Contrôle activé par défaut avec `IMAGE_REVIEW_ENABLED=true`, uniquement pour les articles
présents dans une couverture. Sans clé, pas d'image non vérifiée. Sa facturation à la première
consultation est indiquée dans le lecteur ; elle est séparée du coût de génération des éditions.
L'URL frontend `?v=review-1` invalide les anciens caches navigateur sans contrôle sémantique.

Test réel : 17 articles, 16 appels Nano, 10 `keep`, 1 `reject`, 5 `uncertain`, aucune erreur.
L'image de sushi de `nellie.food` (`df75c9c550f8b2fa702c66b5`) est désormais rejetée
automatiquement : sa référence est rétablie dans le catalogue pour utiliser le vrai contrôle.
Coût estimé à partir de l'usage API : 0,003002 USD. Miniatures : 724 089 octets contre
6 500 560 octets d'originaux, maximum 83 181 octets ; sorties <=16 tokens, aucun raisonnement.
Audit : `data/image-review-audit.json`. Les 5 cas incertains sont des abstentions du modèle,
pas une preuve que les photos sont fausses. Le test ne mesure pas un taux global de fiabilité.
203 tests backend, 10 tests frontend et 2 tests PostgreSQL ciblés passent ; build Vite,
Ruff et vérification du lock passent. Nouvelle dépendance : Pillow, verrouillée dans `uv.lock`.

## Évaluation de quatre profils nouveaux — 26 septembre 2026

Demande utilisateur : tester des profils nouveaux choisis librement, sans reprendre les anciens
essais. Profils reproductibles dans `examples/evaluation-profiles.json` : cuisine, création de jeux
indépendants, jardinage urbain (français uniquement), musique et prise de son.
Commande payante : `python -m scripts.evaluate_covers --output data/evaluation/mon-essai` ;
`--only cuisine` limite à un profil. Les éditions sont réellement persistées dans PostgreSQL.
Le script conserve requêtes, empreintes du code, métriques et diagnostics, même sur expiration.

Rapport local : `data/evaluation-profils-2026-09-26/RAPPORT.md`, traces `live/`, `improved/`, `final/`.
Dernières éditions retenues :

- Cuisine : `8b7c86763c7243d3b1a99387f4d4acac`, 5/18, partielle (brief-v6).
- Jeux indépendants : `292257f2141846e4b98028294cf9064a`, 5/18, partielle, contre 1 initialement.
- Jardinage : `4108cb5d8b624e8abd1d7f50d4f03723`, 1/18, partielle, contre 0 initialement.
- Musique : `beecb45356b1477fbba22330ebca49df`, 6/18, secours pour citations finales invalides,
  contre 1 initialement. Les trois dernières sont en brief-v5.

Le catalogue s'est enrichi entre les passes : ce n'est pas un A/B isolé. Aucune édition complète
de 18 articles. Les rejets temporels excessifs, citations recomposées et extractions web limitées
restent les principales pertes ; ne pas présenter l'amélioration de quantité comme une validation
globale de pertinence. Sous-total connu des essais et du diagnostic : 1,146855 USD, avec deux appels
sans métrique complète. Le passage initial sans accès réseau est exclu de la comparaison ; ses
quatre éditions vides et traces sont conservées dans `baseline/`. Une première cuisine a expiré.

Corrections : conserver les besoins du profil correctement cités si un autre élément est invalide ;
réexaminer sur texte intégral déjà disponible une temporalité mal évaluée sur titre/extrait ;
préciser la distinction méthode durable/actualité/recherche et réserves/validité ; conserver les
ArticleLink typés à l'extraction web ; normaliser langues et codes régionaux sur les trois modèles ;
renvoyer HTTP 502 sans persistance si tous les appels modèles ont échoué et la sélection est vide.
Les contrôles finaux d'âge et de validité restent actifs. Cache courant : **brief-v6**.
161 tests backend passent sur le code final ; 7 tests PostgreSQL isolés ont aussi passé pendant
la session. Ruff et format passent. Le backend a été relancé sur le port 8010 avec le code final ;
les quatre éditions, le lecteur et l'inspecteur répondent HTTP 200. Les langues des éditions
relues sont normalisées ; `api-readback.json` conserve cette vérification sans appel payant.

## Mise à jour : qualité éditoriale après audit des cinq dernières couvertures

Cette section remplace les anciennes limites temporelles décrites plus bas. Les actualités
restent limitées à 7 jours, les résultats scientifiques datés à `MAX_RESEARCH_AGE_DAYS=365`.
Les lectures de fond durables n'ont **aucun plafond d'âge**, même plusieurs décennies.
`MAX_EVERGREEN_AGE_DAYS` est supprimé des réglages ; une ancienne valeur dans `.env` est ignorée.
La fiche classe le contenu (`news`, `research`, `evergreen`, `event`) et sa validité, avec
un passage du texte à l'appui. Les contenus jugés périmés ou incertains sont exclus. C'est un
jugement sur le document, pas une vérification indépendante de l'état actuel des connaissances.
Les dates d'origine sont conservées ; aucune ancienne actualité n'est rajeunie.

Un appel initial extrait les besoins précis des notes, leurs priorités et niveaux, et les
contraintes explicitement exprimées. Les citations sont contrôlées dans le profil. Le classement
utilise maintenant ces besoins et les notes ; chaque choix doit citer le titre ou extrait,
puis la fiche à la sélection finale. Plan, filtrage et rédaction ont des consignes distinctes,
sans exemple géographique contaminant. Les requêtes ciblent un besoin à la fois et disposent
d'une mémoire des rejets et recherches improductives. L'inspecteur montre ces informations.

Le budget distingue consommation déclarée et réservations non réconciliées. À réception de
l'usage fournisseur, la réservation est libérée une seule fois. `FINAL_TOKEN_RESERVE=30000`
protège la rédaction ; les actions optionnelles s'arrêtent avant de l'entamer. Une proposition
de source ne peut plus prendre la place d'une recherche quand l'édition est insuffisante.
Le rédacteur donne des rôles de mise en page et une clé de sujet pour limiter les reprises,
avec une exception motivée pour un angle complémentaire. Le secours garde les titres français
des fiches et le classement éditorial. Le cache passe à `brief-v3` ; pas de migration SQL.
L'exploration et les durées de lecture précédemment ajoutées sont conservées.

Le lecteur respecte les rôles explicites et reste compatible avec les anciennes couvertures.
La gestion des éditions est repliée lorsqu'une édition existe ; l'en-tête est réduit sur grand
écran. Vérification visuelle sur l'ancienne édition sciences : premiers titres désormais visibles
dès le premier écran. Les anciennes sélections ne sont pas réécrites.

Audit local : `data/audit-couvertures-2026-09-26.md`. Les essais réels utilisent le catalogue
PostgreSQL en lecture seule et une mémoire isolée pour les écritures. Ils ne créent ni éditions
ni fiches dans la base utilisateur. Les premières tentatives ont révélé une requête nulle et
des citations assemblées ou entourées de guillemets : correction, tests de régression et
consignes imposant un passage court contigu dans la langue du texte. Les diagnostics conservent
désormais l'intention produite et les évaluations de validité, même en cas de rejet.

Validation finale : 147 tests backend sans base, 7 tests PostgreSQL isolés et 9 tests lecteur
réussis ; Ruff, format, build Vite et `git diff --check` passent. Le 147e test couvre un cas réel :
quatre brèves faisaient refuser toute la rédaction. Les rôles en surplus passent désormais en
lecture, sans changer l'ordre ni supprimer d'article. Le secours priorise aussi les besoins des notes.
Les deux derniers essais complets (avant ce dernier ajustement de mise en page) donnent seulement
3/15 articles en histoire (partiel) et 7/18 en sciences (secours pour quatre brèves). Le rejeu
des validations sur leurs fiches/métadonnées passe avec la correction, sans nouvel appel payant.
**Aucun gain global de pertinence n'est démontré** : la recherche récupère encore trop peu de
textes directement liés aux priorités, et le modèle reste irrégulier sur la validité et la profondeur.
Rapport et traces : `data/editorial-validation-2026-09-26/RESULTATS.md` et `204512/`.
Les deux dernières générations seules coûtent environ 0,289357 USD selon l'usage retourné ;
les itérations de diagnostic sont en supplément et certaines n'ont pas de métrique complète.

## Mise à jour : exploration et deux temporalités

Les nouvelles couvertures préparent d'abord les articles directement pertinents. Le plan peut
proposer des réserves `exploration=true`, avec `exploration_reason` obligatoire pour leur
acceptation et le même seuil éditorial. Après une première découverte directe (si demandée),
un manque ouvre les recherches aux thèmes connexes mais différents. Les réserves ne consomment
des résumés que pour compléter la sélection. L'allocation garde les articles directs prioritaires
et conserve quotas et dédoublonnage ; le secours porte aussi les marqueurs d'exploration.
`CoverItem.selection_kind` vaut `focused` par défaut ou `exploration`, avec la raison du détour.
Le lecteur place ces compléments dans une rubrique Exploration distincte, avec leur explication.
Les budgets existants ne changent pas. Pas de nouvelle génération payante pour cette modification.

Le plafond des actualités passe de 45 à 7 jours par défaut, avec priorité éditoriale aux dernières
24–72 heures. Toute actualité sans date est exclue, y compris dans le catalogue. Les lectures
de fond explicitement durables gardent le plafond de 365 jours, ou une date inconnue affichée
comme telle. Le contenu classé `news` ne peut bénéficier de l'exception ni porter le badge
« Lecture de fond ». L'âge est revérifié après extraction. Les anciens documents restent lisibles
grâce aux valeurs par défaut ; leur sélection n'est pas réécrite.

## Mise à jour : découverte ouverte et lectures de fond

La couverture culture `ec244a9f39d24d32a5eebdd9d63d1898` ne contient que 5/18 articles,
tous hors du contexte demandé (Singapour / Asie du Sud-Est). Le rédacteur avait lui-même
ajouté une liste de grands médias à ses requêtes. Ce n'était pas une restriction OpenAI.
Les liens web retournés étaient un article britannique et des pages de rubrique ; les notes
étaient traitées comme facultatives, et la limite de fraîcheur excluait les essais plus anciens.

`web_search.py` retire désormais les restrictions positives `site:` / `domain:` des requêtes,
transmet le profil à la recherche et privilégie blogs et publications indépendantes en seconde
passe. Les citations et `web_search_call.action.sources` deviennent des candidats (12 par passe,
deux par domaine), toujours extraits et filtrés avant résumé. Les traces conservent requête
demandée/effective, stratégie et origine de chaque référence. Aucun nouveau domaine autorisé
en dur. Le modèle de recherche peut encore mal chercher : ce changement n'est pas une garantie
de diversité ni de pertinence, à vérifier sur de prochaines éditions réelles.

Les choix éditoriaux comportent `matches_profile` et `evergreen`. Le premier doit être vrai
avant préparation ; le second autorise les lectures durables jusqu'à 365 jours par défaut
(`MAX_EVERGREEN_AGE_DAYS`), voire sans date. Les actualités restent limitées à 45 jours,
et une fiche classée `news` ne peut profiter de l'exception. `CoverItem.reading_kind` permet
le badge « Lecture de fond » ; une date inconnue reste affichée comme inconnue.
Les anciens documents restent lisibles avec les valeurs par défaut.

Budgets actuels : 2 passes web, 20 tentatives d'import (auparavant 12, insuffisant pour une
couverture de 18 sur catalogue vide), toujours 24 résumés et 6 décisions maximum.
Le cache de résumés passe à `brief-v2` pour les consignes anti-contamination par menus/autres
articles ; les anciennes fiches ne sont pas réutilisées par cette version. Pas de migration SQL.
Les propositions de sources restent soumises à l'approbation admin existante.

Vérification de cette mise à jour : 104 tests backend sans base + 7 tests PostgreSQL isolés,
7 tests frontend, build Vite et Ruff réussis. Un scénario sans catalogue prépare 18 articles
avec deux recherches ; les tests couvrent aussi le rejet hors contexte, les essais anciens
et les références consultées non citées. Extraction réelle de deux articles Plural réussie
(pavillon de Singapour à Venise et biennale de Sentul), sans écrire en base ni appeler de LLM.
Aucune nouvelle couverture payante n'a été générée pour cette correction.

## Interface lecteur et nom du projet

Le choix initial et les préférences proposent maintenant 20 centres d'intérêt (contre 6),
définis dans `frontend/src/reader.js`, chacun associé à des termes français et anglais.
Les identifiants des six anciens sujets sont conservés pour les profils locaux existants.

L'extension multimédia est reportée à la demande de l'utilisateur. À reprendre plus tard :
newsletters publiques, projets à découvrir, podcasts Radio France (culture, sciences, économie,
société), vidéos YouTube intégrées. Choix validé : 30 minutes maximum d'audio nouveau par
couverture, cache partagé. La clé Gradium sera branchée plus tard. Aucun code multimédia
partiel n'est activé ; prévoir conversion audio vers un format accepté et budget de transcription.

Le nom produit retenu par l’utilisateur est **Kiosque**. Le package Python `broadwai`
n’a pas été renommé. À la demande de l’utilisateur, `frontend/` (React 19 / Vite 7)
est maintenant connecté à l’API. Aucun compte, e-mail ou mot de passe : profil et
identifiant `local-<uuid>` persistés dans le navigateur. Le premier intérêt reçoit
plus de poids ; les notes et langues sont envoyées à la génération. Les éditions et
retours sont conservés côté PostgreSQL. Le navigateur garde les favoris et le dernier
identifiant de couverture, puis recharge cette couverture par GET au démarrage.

Le lecteur utilise `reader.js` (adaptateur), `api.js` (HTTP), `App.jsx` (parcours),
`Newspaper.jsx` (journal) et `components.jsx` (formulaires et articles).
Les anciens corpus fictifs React, profils JSON et scripts de démonstration ont été retirés.
Les doublures encore utilisées sont limitées aux tests automatisés.
L’inspecteur ouvre désormais le frontend via `/reader/?cover={id}` ; ce paramètre
est prioritaire sur la dernière édition mémorisée. Nettoyage validé par 96 tests backend,
6 tests frontend, build Vite, Ruff et ouverture d’une vraie couverture dans le navigateur.
Les 7 tests PostgreSQL isolés n’ont pas été relancés pour ce nettoyage.
Titres et rubriques viennent du rédacteur ; résumés repliés dans la fiche de lecture,
liens éditeurs, statuts partial/fallback explicites et lien vers l’inspecteur.
Les clics sur « Générer ma une » seuls créent des appels payants : 15/18/20 articles,
`discover_web=true`, `discover_sources=true`. Pas de relance automatique.
Les retours `open/useful/already_known/not_interested` ne sont envoyés que pour les
éditions du profil local courant. L’historique montre les 100 dernières éditions de
tous les profils de ce serveur de développement ; ce n’est pas une authentification.

Développement sur `http://127.0.0.1:5173/` avec proxy `/v1`, `/health`, `/admin` vers
8010. Après `pnpm build`, redémarrer FastAPI pour servir aussi `/reader/` depuis
`frontend/dist` (montage optionnel). Ne jamais ajouter de clé OpenAI au frontend.
Voir `frontend/README.md` pour les commandes et les vérifications sans crédits.

Validation initiale de ce branchement : 10 tests JavaScript, 4 tests API/inspection ciblés,
build Vite et Ruff réussis. Vérification navigateur des 18 vrais articles, filtres,
favoris persistants et liens ; génération complète de 18 articles et feedback 201
sur un serveur de test isolé depuis retiré, plus affichage fallback et viewport 390 px.
Aucun appel OpenAI supplémentaire ni nouvelle couverture dans PostgreSQL pour ces tests.


État de référence : 26 septembre 2026. Ce document décrit le projet et les travaux réalisés ;
les chiffres et l'état du serveur sont un instantané à revérifier. Le code et les réponses de
l'API font foi. Voir [README.md](README.md) pour la documentation d'utilisation.

## État courant : une de journal de 15 à 20 articles

Dernier essai validé : `52f9c28a736b485694c9d6a1da0cf4eb`, 18 articles, 5 rubriques,
8 domaines, statut `complete`, 53,1 secondes. Un plan + une décision finale, 18 résumés nouveaux,
aucune fiche en cache, aucune recherche web nécessaire. Coût standard estimé : 0,050903 USD.
Trois fiches reposent sur les extraits RSS, le texte complet du Monde étant inaccessible ;
les réserves restent affichées dans l'inspecteur. Les titres et rubriques sont visibles sans
résumés dans `/reader/?cover=52f9c28a736b485694c9d6a1da0cf4eb`.

Deux essais intermédiaires de cette correction ont échoué éditorialement (`6b110253...`, fallback
16 articles, et `8a5ac046...`, partial 13 articles) ; ils sont conservés pour audit. Les trois essais
de cette correction totalisent 0,234339 USD estimés. Ne pas confondre ce total de développement
avec le prix de la dernière couverture. `data/live-cover.json` contient le dernier résultat réel.
Validation : 96 tests locaux, 7 tests PostgreSQL dans des schémas isolés, Ruff et vérification
du rendu navigateur. Aucun nouvel appel payant après l'activation de la découverte pour les tests
suivants. La sélection reste perfectible, notamment le chevauchement de sujets énergie/agriculture.

L'utilisateur ne souhaite pas préciser davantage son profil. Le produit doit présenter une une
de journal organisée en quelques rubriques ; les résumés restent un outil interne du rédacteur.
`CoverRequest.size` vaut maintenant 18 par défaut. Le profil se configure dans le frontend.
À la demande de l'utilisateur, il active `discover_web=true` et `discover_sources=true` afin
d'enrichir les propositions de sources. Leur approbation dans l'admin reste nécessaire.

Ajouts : `editorial.py`, plan LLM structuré (titres/extraits de 96 candidats maximum), sélection
avant les résumés, score éditorial minimum 70, contexte de décision compact, identifiants de
sélection contraints par enum, contrôle 3–5 rubriques avec au moins 2 articles chacune pour une
une complète de 15–20 articles, refus des finalisations prématurées tant que des moyens de
recherche restent disponibles. Domaines en échec répété évités pour la génération courante.
`Selection.headline` et `CoverItem.headline` permettent des titres français pour la une.
Les anciens documents sans ce champ restent lisibles.

Budgets : 1 plan, 6 décisions, 24 résumés nouveaux, 2 recherches web, 2 recherches catalogue,
24 extractions et 20 tentatives d'import web, 4 filtres de recherche sur le modèle économique.
`.env.example` et les deux limites locales ont été
mis à jour sans toucher à la clé. Trois préparations peuvent s'exécuter simultanément.
Les modèles restent gpt-5.4-nano / gpt-5.4-mini. `usage.cost` fournit une estimation standard
USD avec prise en compte du cache et des outils web, pas une facture ni une limite monétaire.
Les métriques détaillées et le plan sont enregistrés dans l'inspecteur.

Le frontend est l’unique vue de lecture des couvertures. L’inspecteur `/admin/covers`
ouvre l’édition choisie via `/reader/?cover={id}`, sans générer de nouvelle couverture.
L’ancienne route HTML de lecture et ses assets ont été supprimés ; l’API JSON reste disponible.

Le quota par source par défaut est passé à 3 pour ce format (reste réglable par requête).
Les quotas et doublons sont appliqués en conservant l'ordre du modèle ; chaque retrait est audité.
Le rédacteur GPT-5 utilise `reasoning=low`. Une finalisation n'est pas une action possible quand
la capacité connue est insuffisante et qu'une recherche reste possible. Les recherches catalogue
et web passent un filtre éditorial supplémentaire avant résumé. Les résultats web sont vérifiés
comme articles avec extraction de date. Les actualités de plus de 45 jours ou les actualités web
non datées sont écartées ; les lectures de fond suivent l'exception décrite en tête du document.
Les anciennes couvertures ne sont pas réécrites.

Huit nouvelles sources économiques collectées via `examples/sources-economy.json` : Franceinfo,
RFI, Le Monde, Alternatives économiques, BFM, Le Figaro, CNBC et NPR. 710 articles au moment de
cet ajout, 43 sources ; La Tribune et The Conversation ont été ignorés après erreur HTTP.
La diversification a été optimisée : caractéristiques préparées une seule fois et similarités
actualisées incrémentalement. 346 ms mesurées pour classement + pool de 96 sur 548 articles,
contre 134 secondes pour la version intermédiaire. Un test empêche la répétition des tokenisations.

Les paragraphes suivants décrivent les étapes historiques et leurs chiffres au moment des essais.
En cas de contradiction sur les défauts, cette mise à jour et le code actuel prévalent.

## Mise à jour : sources web sans flux

L'admin et `/v1/sources` acceptent `kind=website` (page de blog ou de rubrique).
`/v1/ingest` accepte `website_urls`. `broadwai/website.py` découvre les liens HTML/JSON-LD,
filtre les pages utilitaires et vérifie les pages d'articles avant import avec métadonnées et texte.
La collecte est bornée à 50 pages candidates, cinq requêtes simultanées et 100 secondes par site.
Pas de navigateur JavaScript, de sitemap ou de pagination automatique dans cette version.
Les protections réseau existantes restent appliquées et aucun LLM n'est appelé par la collecte.

`validate_source` privilégie un flux valide puis vérifie un échantillon d'articles à défaut de flux.
Les propositions conservent leur `kind`, repris à l'approbation. Quota : cinq téléchargements au plus
par proposition. La migration au démarrage étend les types de sources et ajoute `kind` aux anciennes
propositions avec la valeur `rss`, sans supprimer de données. Redémarrer le backend pour l'appliquer.

Tests réels sans écriture en base : deux articles collectés via HTML sur le blog de Simon Willison
et deux sur le Guardian. Les tests de migration et d'approbation RSS/site web passent sur PostgreSQL
avec des schémas isolés. `scripts.smoke_website` permet de reproduire le test réseau sans modèle.
La reconnaissance reste heuristique : les métadonnées seules ne garantissent pas une page d'article.

## Mise à jour : découverte web hébergée

La recherche web utilise désormais OpenAI Responses `web_search`, sans clé de recherche séparée.
`broadwai/web_search.py` récupère les citations et références consultées du fournisseur ; le backend importe
uniquement les articles dont il a pu extraire le texte. `Article.discovery` conserve la provenance.
`broadwai/discovery.py` vérifie les flux RSS/Atom pour l'action `propose_source` du rédacteur.
La nouvelle table `source_proposals` et les routes `/v1/source-proposals` permettent d'examiner,
d'approuver ou de refuser ces flux dans l'admin. Seule une approbation les ajoute aux sources.

Limites : deux recherches, vingt tentatives d'import et deux propositions par couverture par défaut.
Les téléchargements de découverte et de validation de flux ont des quotas distincts de ceux de la
présélection. Le modèle et la recherche tournent chez OpenAI ; les extractions et PostgreSQL restent
sur le backend. Configuration : `WEB_SEARCH_ENABLED`, `MAX_DISCOVERED_ARTICLES`,
`MAX_SOURCE_PROPOSALS`, ainsi que la clé et les noms de modèles existants.
Les noms recommandés sont maintenant inscrits dans `.env.example` (nano/mini GPT-5.4).
La clé a été renseignée localement par l'utilisateur ; ne jamais l'afficher.

Les comptes de catalogue et l'absence de fiches/couvertures indiqués plus bas sont l'instantané
antérieur au premier test réel. Consulter `/health` et `data/live-cover.json` pour l'état courant.
Le test réel se lance maintenant avec « Générer ma une » dans le frontend. Voir le README.

Nouvelle inspection : `/admin/covers` et `GET /v1/covers` affichent l'historique. Les prochaines
couvertures enregistrent `diagnostics.version=1` (profil, paramètres sans secrets, scores et
shortlists, événements d'extraction/résumé/cache, candidats, décisions et outils). `usage.model_calls`
conserve les métriques par appel. Les trois essais déjà stockés restent explicitement marqués
« trace ancienne, partielle » : aucune reconstruction des anciens scores. Pas de nouvelle génération
payante pour ajouter cette inspection. Validation : 62 tests locaux et un test PostgreSQL ciblé
de persistance/relecture du journal. L'audit est disponible après enregistrement final, sans SSE.
Ce mode active `discover_web` et `discover_sources` : la finalisation doit être précédée d'une
tentative de recherche puis d'examen de source. Les échecs sont rapportés, pas masqués.
Les répertoires RSS sont exclus de l'import d'articles. Les deux pages RSS importées pendant
le deuxième essai restent archivées dans le catalogue avec `discovery.kind=source_directory`
et sont exclues du classement. La détection de ces pages est heuristique.

Résultat des tests réels : trois couvertures ont été créées et relues dans PostgreSQL. Dernière :
`b8f7f069405144dbb1b68eff647227da`, statut `complete`, cinq articles. Elle a exécuté une recherche
web hébergée et tenté `propose_source` pour la BCE. Les extractions BCE et la validation de source
ont échoué avec `ClientConnectorCertificateError` ; aucun flux n'a été proposé/activé et aucun
article BCE n'a été importé. La couverture finale utilise donc le catalogue existant. Ne pas
présenter cet essai comme une démonstration réussie d'ajout d'une source réelle.

État après essais : 546 entrées au catalogue (dont deux répertoires RSS exclus du classement),
23 fiches, trois couvertures et 35 sources actives. `data/live-cover.md` présente le dernier résultat
et `data/live-cover.json` conserve la trace. Les deux premiers résultats restent accessibles par
leurs identifiants en base. Vérifications : 60 tests locaux passent, plus cinq tests PostgreSQL
exécutés séparément ; Ruff passe. Les tests d'intégration vérifient approbation/refus et idempotence
dans un schéma isolé. Aucun certificat n'a été contourné. La qualité éditoriale reste à améliorer :
le modèle a dû corriger plusieurs propositions dépassant le quota de sources ou contenant un ID
inconnu ; le backend les a toutes refusées avant l'enregistrement final.

## Objectif et demande en cours

Projet de hackathon : un agrégateur d'information personnalisé, inspiré de Feedly, Hacker News
et Reddit. Produire une « couverture » : une sélection courte d'articles pertinents, résumés,
catégorisés et accompagnés d'une justification adaptée au lecteur.

Le hackathon exige une vraie logique agentique : le LLM doit prendre des décisions et orchestrer
des actions. Une chaîne fixe de résumés ne suffit pas. La boucle du rédacteur implémente cette
capacité avec des outils bornés.

La priorité demandée est le backend de collecte et de création de couverture. L'utilisateur a
ensuite demandé une admin simple, PostgreSQL, puis un catalogue réel suffisamment fourni pour
tester une couverture. Les thèmes souhaités sont IA, développement, infrastructure, cybersécurité,
sciences, **économie et actualité générale**, en français et en anglais.

Prochaine étape produit : premier essai réel de génération sur ce catalogue. Aucune couverture
n'a encore été générée avec un fournisseur LLM ; ne pas confondre tests simulés et validation réelle.

## Décisions retenues

- Python 3.12+, FastAPI, Pydantic, PostgreSQL avec Psycopg et pool de connexions.
- Catalogue partagé entre lecteurs ; classement et composition personnalisés par requête.
- Collecte RSS/Atom et API officielle Hacker News. Extraction du texte des candidats à la demande.
- Classement lexical BM25 avant les appels LLM pour limiter les coûts.
- Fiches structurées produites par un modèle économique, indépendantes du lecteur et mises en cache.
- Le rédacteur reçoit ces fiches, pas tous les articles complets.
- Adaptateur OpenAI Responses avec sorties structurées ; noms des modèles configurables.
- Recherche OpenAI hébergée facultative via WEB_SEARCH_ENABLED. Le rédacteur peut travailler uniquement avec le catalogue.
- Admin HTML/CSS/JavaScript simple, sans framework ni étape de build.

## Parcours implémenté

1. Enregistrer les sources puis collecter titres, URL, dates, langues et extraits dans PostgreSQL.
   Les URL sont normalisées et les réimportations sont idempotentes.
2. Recevoir un profil : identifiant utilisateur, intérêts pondérés, langues, exclusions, notes et
   articles déjà vus. Le profil est fourni à chaque requête, sans table de profils persistants.
3. Présélectionner par pertinence lexicale et fraîcheur ; filtrer les exclusions et articles consommés,
   puis diversifier les sources et limiter les doublons proches.
4. Extraire les textes avec Trafilatura. En cas d'échec, exploiter seulement l'extrait disponible en
   indiquant sa provenance. Un titre seul ne permet pas de produire une fiche.
5. Générer ou réutiliser les fiches : cache par identifiant d'article, hash du contenu et version
   incluant prompt/modèle. Les fiches peuvent être partagées entre lecteurs.
6. Le rédacteur choisit une action JSON : `search_catalog`, `search_web`, `read_article` ou `finalize`.
   Le backend exécute l'action et renvoie son résultat au LLM avant la décision suivante.
7. Valider la sélection finale : identifiants autorisés, taille, doublons et quotas de sources.
   Une proposition invalide revient au modèle pour correction. Une sélection de secours explicite
   est possible si le modèle échoue ou si le budget est épuisé.
8. Persister la couverture, ses fiches, justifications, avertissements, trace d'actions et usage tokens.
9. Enregistrer le feedback. `open`, `useful`, `already_known`, `not_interested` excluent ensuite
   l'article consommé ; une simple `impression` ne suffit pas.

L'apprentissage d'une mémoire utilisateur à partir du feedback fait partie de la vision initiale,
mais **n'est pas implémenté**. Les notes présentes sont celles transmises dans le profil.

## Cartographie du code

| Fichier | Responsabilité |
|---|---|
| `broadwai/api.py` | FastAPI, démarrage, santé, couvertures, feedback, verrous locaux |
| `broadwai/models.py` | Contrats Pydantic : articles, profils, fiches, couvertures, événements |
| `broadwai/config.py` | Paramètres `.env`, limites et disponibilité LLM |
| `broadwai/sources.py` | CRUD des sources, collectes admin, navigation dans les articles |
| `broadwai/retrieval.py` | RSS/Atom, Hacker News et extraction |
| `broadwai/network.py` | Téléchargements publics bornés, contrôle DNS et redirections |
| `broadwai/ranking.py` | BM25, fraîcheur, exclusions et diversification |
| `broadwai/llm.py` | Prompts, adaptateur OpenAI, sorties structurées et budget |
| `broadwai/pipeline.py` | Boucle agentique, cache, validation et repli explicite |
| `broadwai/store.py`, `schema.sql` | Persistance PostgreSQL et schéma initial répétable |
| `broadwai/static/admin.*` | Interface locale de gestion des sources et consultation |
| `examples/sources.json` | Catalogue reproductible de 35 sources |
| `frontend/src/reader.js`, `api.js` | Profil local, requête de couverture et appels API |
| `scripts/seed_sources.py` | Validation et import des sources via l'API, collecte optionnelle |
| `scripts/audit_catalog.py` | Audit PostgreSQL et extraction d'un échantillon sans LLM |
| `tests/` | Tests unitaires/API et intégration PostgreSQL |

## Données PostgreSQL

| Table | Contenu |
|---|---|
| `articles` | Identifiant, URL unique, date de collecte et payload JSONB : titre, domaine, texte, extrait, dates, langue, état d'extraction |
| `briefs` | Fiches JSONB, clé composée article/hash du contenu/version |
| `covers` | Couvertures JSONB avec identifiant et utilisateur |
| `feedback` | Événements utilisateur/couverture/article, type et date ; événements identiques dédupliqués |
| `sources` | Nom, type RSS/HN, URL, activation, limite, dernière collecte et rapport |
| `source_articles` | Associations plusieurs-à-plusieurs entre sources et articles |

Supprimer une source conserve les articles. Les collectes directes par `/v1/ingest` ne créent pas
rétroactivement les associations admin. `put_article` préserve un texte déjà extrait lorsqu'une
nouvelle collecte n'apporte qu'un extrait. Les changements futurs du schéma devront être migrés
explicitement ; il n'y a pas encore d'outil de migrations versionnées.

## État réel vérifié le 26 septembre 2026

- PostgreSQL fonctionne et le backend s'y connecte.
- **35 sources actives, 544 articles distincts, 43 domaines éditeurs.**
- 534 articles ont une date de publication et 500 un extrait. Zéro fiche et zéro couverture.
- Derniers rapports de collecte des sources enregistrées : aucune erreur.
- Sources notamment : Python, Cloudflare, Hacker News, Hugging Face, Google Research, DeepMind,
  GitHub, Kubernetes, CERT-FR, CNRS, Quanta, NASA, Franceinfo, France 24, RFI, Le Monde,
  BBC, The Guardian, FRED et Our World in Data. Liste exhaustive dans `examples/sources.json`.
- Les candidats ACM Queue, BCE et BLS ont échoué à la validation et n'ont pas été enregistrés.
- Sur six articles échantillonnés : cinq textes exploitables ; un article du Monde renvoie une
  page de blocage JavaScript. Ce faux texte a été retiré en conservant les métadonnées et l'extrait.
- La détection de certains messages de blocage courts est maintenant testée dans `Collector.extract`.
  Elle ne constitue pas une détection universelle des paywalls ou du contenu incomplet.
- Les 539 autres articles sont encore à l'état `excerpt` : l'extraction complète est faite à la demande.
- Aucun appel LLM payant n'a été effectué. Clé OpenAI et noms des deux modèles non configurés.

Rapports locaux : `data/catalog-audit.json` et `data/sources-import-report.json`. Le dossier `data/`
est ignoré par Git ; il ne sera pas présent sur une nouvelle machine. Le dernier rapport d'import
décrit son exécution, pas nécessairement tout l'historique.

## Reprendre et lancer le premier test

Le développement courant est sur Windows/PowerShell. `.venv` existe déjà. Le serveur a été relancé
sur **http://127.0.0.1:8010** ; le README utilise 8000 comme exemple générique. Vérifier `/health`
avant de démarrer un autre processus. Utiliser un seul worker pour les verrous actuels.

```powershell
# Depuis la racine du dépôt
Invoke-RestMethod http://127.0.0.1:8010/health

# Seulement si le serveur n'est pas déjà lancé
.\.venv\Scripts\python.exe -m uvicorn broadwai.api:app --host 127.0.0.1 --port 8010

# Ajouter les sources absentes et collecter leurs articles, sans LLM
.\.venv\Scripts\python.exe -m scripts.seed_sources --base-url http://127.0.0.1:8010 --collect --only-new

# Audit et extractions réelles, sans LLM
.\.venv\Scripts\python.exe -m scripts.audit_catalog --extract-sample 6
```

Pour créer une couverture, renseigner localement `OPENAI_API_KEY`, `SUMMARY_MODEL`, `EDITOR_MODEL`
dans `.env`, puis redémarrer l'API. Ne pas écraser un `.env` existant avec l'exemple. Ne pas copier
les secrets dans une réponse, un document ou un commit. `/health` doit afficher
`llm_configured: true` ; cela vérifie la configuration, pas la validité de la clé chez le fournisseur.

Ouvrir `http://127.0.0.1:5173/`, régler son profil et cliquer sur « Générer ma une ».
Ce bouton déclenche de vrais appels LLM facturables. La taille se règle à 15, 18 ou 20 articles,
avec au plus trois par source. Les thèmes utilisent des mots-clés bilingues car BM25
ne traduit pas les intérêts. Vérifier liens, fidélité des fiches, diversité, justifications, trace,
usage et statut : `complete`, `partial` ou `fallback`. Un HTTP 200 ne prouve pas une couverture
complète ou de bonne qualité. Relire ensuite la couverture par son identifiant pour vérifier
sa persistance. Sans configuration LLM, la création répond HTTP 503.

## API et interface

- `/admin` : sources éditables, collecte individuelle/globale, articles paginés, filtres et détails.
- `/docs` : contrat OpenAPI interactif, permet de tester la création de couverture.
- `GET /health`, `POST /v1/ingest`, `GET /v1/articles`.
- `POST /v1/covers`, `GET /v1/covers/{id}`, `POST /v1/feedback`.
- `GET/POST /v1/sources`, `PUT/DELETE /v1/sources/{id}`.
- `POST /v1/sources/collect`, `POST /v1/sources/{id}/collect`.
- `GET /v1/admin/articles`, `GET /v1/admin/articles/{id}`.

L'admin ne génère aucune fiche et n'a pas encore de formulaire de création de couverture.
La génération répond à la fin du traitement, avec un délai global maximal de 300 secondes.
Il n'existe pas encore de streaming SSE ni de progression affichée en direct.

## Validation et limites à connaître

Les validations précédentes ont passé 51 tests unitaires/API et quatre tests d'intégration
PostgreSQL. Après l'ajout de la protection contre les interstitiels, les 18 tests du fichier
`test_retrieval.py` passent, ainsi que Ruff sur les fichiers concernés. La suite complète n'a
pas été relancée après cette dernière correction. Aucun test réel du fournisseur LLM à ce stade.

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
.\.venv\Scripts\python.exe -m pytest -q
# Pour l'intégration : définir TEST_DATABASE_URL vers l'instance de test avant cette commande
.\.venv\Scripts\python.exe -m pytest tests/test_postgres.py -q
```

Les tests PostgreSQL utilisent un schéma isolé créé puis supprimé ; sans `TEST_DATABASE_URL`, ils
sont ignorés. Les autres tests utilisent des doublures sans crédits LLM. La CI fournit PostgreSQL.

Points de vigilance pour la suite :

- API locale sans authentification ; `user_id` n'est pas une preuve d'identité.
- Téléchargements limités aux adresses publiques, redirections et DNS validés, délais et tailles bornés.
  Préserver ces protections ; ne pas contourner les paywalls ni désactiver TLS pour ajouter une source.
- Articles et pages externes sont des données non fiables, jamais des instructions pour les agents.
- Budgets de tours, téléchargements, recherches et appels de résumé ; budget tokens estimé,
  pas plafond monétaire garanti. Pas de réessais automatiques des appels LLM.
- Verrous par processus seulement, pas de file de jobs, de cache verrouillé entre workers ni de collecte planifiée.
- Classement lexical, pas d'embeddings ; similarité des titres, pas de regroupement sémantique des événements.
- Chargement des derniers articles limité par `MAX_CATALOG_ARTICLES` ; à faire évoluer pour un grand corpus.
- Pas encore de vérification factuelle automatique ni d'évaluation de la personnalisation auprès de lecteurs.

Ordre de travail conseillé : valider une couverture réelle avec le catalogue existant via le lecteur,
examiner ses résultats et coûts, puis améliorer la progression si nécessaire. Mesurer ensuite
les besoins de classement sémantique, de regroupement d'actualités et de mémoire utilisateur.
