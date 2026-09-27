# Audit structurel du pipeline — 27 septembre 2026

**Bilan : 5 couvertures abouties sur 5 après refonte, contre 4/5 avant ; moins de boucles
et de contexte répété, mais qualité éditoriale encore inégale.** Le total conservateur
des deux passes est **2,3180172 USD**, sous le plafond de 3 USD. Aucun appel payant supplémentaire
n'a été lancé pour sélectionner de meilleurs résultats.

## Protocole fixé avant la refonte

- Cinq profils : cuisine, jeux indépendants, jardinage francophone, musique/home-studio,
  mathématiques/sciences. Requêtes dans `examples/evaluation-profiles-structural.json`.
- Cible : 18 lectures ; mêmes profils, ordre, modèles et limites techniques avant/après.
- Modèles conservés : GPT-5.4 nano pour les fiches et GPT-5.4 mini pour le rédacteur.
- Catalogue de départ figé : **6 569 articles et 342 fiches**, schéma PostgreSQL local
  `audit_structure_20260927_seed`. Chaque passe utilise une copie indépendante.
- Aucun historique privé, feedback ou profil réel copié dans les schémas d'audit.
- Plafond autorisé : **3 USD pour l'ensemble**. Registre persistant partagé, réservations
  préalables, aucune relance SDK, coûts inconnus conservés. Sous-plafond initial : 1,50 USD.
- Les appels utilisent le tarif standard, avec une marge conservatrice de 20% dans le
  contrôle de dépense. La recherche hébergée réserve le contexte maximal de 400 000 tokens
  et une marge d'appels outil. Le registre n'est pas une facture du fournisseur.
- Les accès web restent en direct : leur variabilité et celle des modèles empêchent de
  considérer cinq profils comme une preuve statistique. Pas de sélection du meilleur de N essais.
- Le changement éventuel de version des fiches invalide leur cache ; son coût est inclus,
  sans attribuer artificiellement les gains à un cache préchauffé par le premier audit.

## Critères d'analyse

Mesures automatiques : nombre de lectures, statut, thèmes couverts, domaines distincts,
langues, doublons, quotas, résumés basés seulement sur un extrait, durée, appels par rôle,
tokens, coût et arrêts de budget. Les échecs et résultats partiels ne sont pas omis.

Revue éditoriale des titres, fiches et limites : adéquation aux notes, niveau, apport concret,
complémentarité, remplissage hors sujet, temporalité et honnêteté sur les contenus non lus.
Cette revue par l'assistant n'est ni une validation humaine indépendante, ni une vérification
externe de toutes les affirmations. Les mêmes critères s'appliquent aux deux passes.

## Exécution

```powershell
python -m scripts.evaluation_snapshot --destination audit_structure_20260927_seed
python -m scripts.evaluate_covers --profiles examples/evaluation-profiles-structural.json --schema audit_structure_20260927_baseline --snapshot-from audit_structure_20260927_seed --output data/evaluation/structure-20260927/baseline --spend-ledger data/evaluation/structure-20260927/spend.json --max-usd 3 --spend-ceiling 1.5
# Après refonte, même snapshot et même registre de dépense :
python -m scripts.evaluate_covers --profiles examples/evaluation-profiles-structural.json --schema audit_structure_20260927_after --snapshot-from audit_structure_20260927_seed --output data/evaluation/structure-20260927/after --spend-ledger data/evaluation/structure-20260927/spend.json --max-usd 3
```

Ajouter `--env-file CHEMIN` si la configuration locale n'est pas dans `.env`.
Les schémas de destination doivent être nouveaux ; aucun effacement de données de production.
Les traces détaillées et textes restent locaux sous `data/`, hors Git. Le rapport et les
métriques synthétiques ne contiennent ni clé ni texte intégral d'article.

La première tentative en environnement restreint a échoué sur les connexions réseau
(`APIConnectionError`) avant toute réponse du fournisseur ; elle est conservée sous
`data/evaluation/structure-20260927/before/`, mais n'est pas le résultat de référence.

## Références de méthode et tarifs

- [Évaluation de changements sur des cas représentatifs](https://developers.openai.com/api/docs/guides/evaluation-best-practices)
- [GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
- [GPT-5.4 nano](https://developers.openai.com/api/docs/models/gpt-5.4-nano)

La méthode OpenAI Docs a guidé le gel des cas de test et la conservation des résultats
défavorables ; aucun changement de modèle n'est inclus dans cette expérience.

## Constats de référence

- Cuisine : 11 lectures, dont des méthodes utiles, mais aussi des études industrielles
  difficiles à justifier pour une pratique débutante à domicile. Les réserves des fiches
  répètent souvent l'absence de transcription sur des articles écrits ou les consignes
  internes de prudence. Ces mentions ne sont pas des limites concrètes du document.
- Jeux indépendants : expiration à 300 secondes, malgré 19 fiches disponibles. Une
  tentative de 17 lectures après retrait d'un doublon a été refusée pour la seule place
  manquante ; une recherche supplémentaire n'a rien ajouté avant l'expiration.
- Jardinage : 4 lectures, mais aucune méthode concrète de culture en balcon. Une annonce
  de rencontre avec une illustratrice et un article sur climat/religion sont des liens
  thématiques trop éloignés du besoin pratique. Les langues et quotas respectés ne
  suffisent donc pas à établir la qualité éditoriale.

Le sous-plafond conservateur de la première passe bloque certaines recherches : ces
résultats sont censurés par le budget, pas une mesure sans contrainte du moteur actuel.
Le coût inconnu d'un appel interrompu reste réservé dans le registre commun.

| Profil | Lectures / 18 | Résultat | Secondes | Sous-total connu USD |
| --- | ---: | --- | ---: | ---: |
| Cuisine | 11 | Partielle | 192,5 | 0,277257 |
| Jeux indépendants | — | Expiration sans couverture | 300,0 | 0,273198 |
| Jardinage | 4 | Partielle | 106,4 | 0,171392 |
| Musique | 13 | Partielle | 149,9 | 0,157644 |
| Maths/sciences | 6 | Secours, composition bloquée par budget | 96,7 | 0,086042 |

Musique mélange des lectures sur les processus musicaux et des liens trop indirects
(soins des danseurs, son quantique pour une demande home-studio). Le simple rattachement
à une rubrique technique ne prouve pas l'apport pratique.

Total connu déclaré : **0,965533 USD**, incomplet pour l'appel interrompu. Le registre,
plus conservateur (sans remise de cache), compte 1,0059692 USD de réponses reçues,
plus 20% et une réserve inconnue de 0,192438 USD : **1,39960104 USD engagés**.
158 appels envoyés ; les appels refusés avant envoi ne sont pas des dépenses inconnues.
Les métriques détaillées et les lectures publiées figurent dans `baseline.json`.

Vérification de référence : **375 tests Python réussis**, PostgreSQL inclus ;
10 tests JavaScript réussis. Aucun modèle facturé par ces tests automatisés.

## Refonte évaluée

Commit de référence poussé : `97c9de1`, branche `codex/pipeline-structural-audit`.

- Dossier factuel partagé : contribution, angle, prérequis, intégrité, nature du propos,
  risque central et temporalité décrits séparément. Résumé et points clés restent côté lecteur.
- Plus de titre recopié par le modèle, ni de verdict dépendant d'aujourd'hui dans le cache.
  L'âge est contrôlé à chaque sélection. Cache `brief-v7-dossier`, anciennes fiches lisibles.
- Aperçu sur le texte récupéré jusqu'à 1 400 caractères ; le score ordonne mais n'élimine
  plus arbitrairement sous 70. Les exclusions explicites restent éliminatoires.
- Préparation progressive : 24 fiches valides au départ pour une cible de 18 ; réserve de
  six supplémentaires si besoin. Les plafonds globaux de tentatives restent appliqués.
- Contrôleur déterministe : recherche si priorité/diversité manque ou si capacité directe
  après quotas < 80% de la cible ; au plus deux recherches locales et deux externes.
  Découverte de sources si besoin mal pourvu ; aucune recherche externe sans autorisation.
- Rédacteur limité à comparer/composer/approfondir, au plus trois tours. Rubriques provisoires,
  18 maximum plutôt que minimum obligatoire, pas d'Exploration automatique de remplissage.
- Admin : acteur serveur/rédacteur explicite, dossier lisible, distinction des contrats anciens.

Le seuil de 80%, les réserves et les limites de tours sont des choix produits testés ici,
pas des valeurs optimales démontrées. Les enveloppes techniques maximales restent celles de
référence ; le contrôleur choisit volontairement de ne pas toutes les épuiser. Le catalogue
figé contient 6 569 articles, mais chaque passe conserve le plafond de lecture actuel de
3 000 articles : la refonte du rappel catalogue n'est pas incluse dans cette comparaison.

## Revue après refonte — observations

Cuisine : les guides levain/levure et fermentation donnent davantage de contenu directement
utile, avec de vraies différences entre recette et explication. Un seul appel de composition.
Les limites sont plus spécifiques et la mention absurde d'absence de transcription sur un
article écrit a disparu. Elles restent parfois trop nombreuses ou verbeuses.
La pertinence finale n'est pas résolue : la maison de Clemenceau est un détour artificiel,
les politiques fiscales alimentaires sont trop spécialisées, et plusieurs articles sur la
fermentation se recouvrent. Les 17 lectures ne doivent pas être assimilées à 17 bonnes lectures.

Jeux indépendants : couverture enfin enregistrée, avec des lectures concrètes sur les visual
novels accessibles et le narrative design (itch.io, Yarn Spinner, auteur spécialisé).
Un seul appel de composition ; un échec réseau de fiche reste comptabilisé sans relance.
Défaut important : des annonces de moteurs/outils et des sujets de carrière design sont encore
retenus malgré la demande de méthodes et le refus des annonces commerciales. Les compteurs
automatiques de violations ne détectent pas cette mauvaise interprétation sémantique.

Jardinage : 9 textes en français, tous extraits, dont des méthodes concrètes pour pots,
balcon ombragé, aromatiques et pollinisateurs. Amélioration éditoriale visible face aux quatre
lectures générales de référence. Une lecture sur les collectivités/climat reste trop indirecte ;
le guide d'équipement d'arrosage doit aussi être jugé au regard du refus des guides d'achat.
La découverte trouve des blogs pertinents sans liste de domaines imposée.

Musique : entretien de Flying Lotus sur son travail, guides de placement des micros et
enregistrement domestique nettement mieux ciblés que la physique quantique du son en référence.
Toutefois, six guides proches sur la guitare créent de la redondance et des annonces d'albums
restent dans la sélection. Le statut « complete » mesure la taille et les contrôles techniques,
pas une validation qualitative indépendante de ces 18 lectures.

Deux fiches de cette passe ont échoué à la validation de sortie structurée, une autre sur
connexion réseau (cuisine/jeux/musique). Elles ne sont pas masquées, ni relancées ; leur
réservation financière est conservée. Les contraintes de longueur du nouveau dossier peuvent
produire des formulations trop coupées : à améliorer sans accroître les contextes répétés.

Maths/sciences : 14 lectures, mais le bénéfice qualitatif est mitigé. La probabilité géométrique
et l'explication de relativité répondent au profil ; le billet Go, les comparaisons de modèles
IA et certaines recherches quantiques spécialisées s'en éloignent ou demandent trop de prérequis.
La composition tend encore à justifier presque tous les dossiers disponibles au lieu d'en
écarter assez. Le mécanisme sait découvrir des sources sans liste imposée, mais cette passe
ne démontre pas qu'il trouve les meilleurs blogs de mathématiques.

## Comparaison finale

| Profil | Lectures avant → après | Secondes avant → après | Coût connu avant → après (USD) |
| --- | ---: | ---: | ---: |
| Cuisine | 11 → 17 | 192,5 → 143,9 | 0,277257 → 0,140043 |
| Jeux indépendants | expiration → 17 | 300,0 → 200,0 | 0,273198 → 0,152058 |
| Jardinage | 4 → 9 | 106,4 → 110,5 | 0,171392 → 0,127959 |
| Musique | 13 → 18 | 149,9 → 134,3 | 0,157644 → 0,125070 |
| Maths/sciences | 6 (secours) → 14 | 96,7 → 180,6 | 0,086042 → 0,154637 |

- Sous-total déclaré connu : **0,965533 → 0,699767 USD (-27,5%)**. Les réserves des appels
  interrompus/invalides ne permettent pas d'en faire un pourcentage de facture exact.
- Temps cumulé : 845,5 → 769,3 secondes (-9%). Maths augmente notamment parce que le
  garde-fou avait empêché la finalisation de référence ; ne pas attribuer tout l'écart au code.
- Tentatives de consultation du rédacteur : **38 → 5**. Certaines tentatives de référence
  étaient bloquées avant envoi ; ce n'est donc pas le nombre exact d'appels facturés.
- Tokens entrants déclarés au rôle rédacteur : **458 028 → 60 714 (-86,7%)**.
- Couvertures enregistrées : 4/5 → 5/5, dont une complète après ; 34 → 75 lectures.
  Ces quantités ne sont pas des scores de qualité.
- Violations mécaniques détectées : aucune sur les éditions enregistrées des deux passes.
  Des exclusions exprimées en langage naturel restent mal respectées, comme décrit ci-dessus.
- Cache : zéro réutilisation avant, une après au sein de la passe. Les deux passes partent
  du même cache gelé ; aucune réutilisation des fiches créées par la référence dans l'après.

La passe de référence a été limitée par son sous-plafond conservateur, alors que l'après
n'a pas rencontré d'arrêt USD. La navigation reste variable, et les changements ont été
orientés par la référence : il s'agit d'un audit de développement, pas d'un test aveugle.
Les détails partageables sont dans `baseline.json` et `after.json` ; aucun texte intégral
collecté ni profil privé n'est versionné.

## Dépense et vérification

Le registre partagé contient 304 réponses avec usage et 4 appels au coût exact inconnu :
1,7285452 USD connus sans remise de cache, 20% de marge sur ce montant, plus
0,24376296 USD de réserves inconnues = **2,3180172 USD comptabilisés**.
Le sous-total avec les remises déclarées est 1,665300 USD, hors ces appels inconnus.
Reste théorique sous plafond : 0,6819828 USD ; aucune relance n'est prévue.
Ce registre est un garde-fou de requêtes, pas une facture fournisseur (hors taxes/suppléments).

Tests : suite complète après refonte **389 réussis**, PostgreSQL inclus ; **16 tests ciblés
réussis** après ajout de deux cas (découverte pour manque réel et persistance du dossier).
**37 tests JavaScript réussis** (25 lecteur, 12 admin/catalogue). Ruff et syntaxe JS vérifiés.
Un avertissement de dépréciation FastAPI/httpx préexistant reste présent.

## Conclusion et suite recommandée

Conserver la séparation dossier/composition et l'arrêt des boucles de remplissage : le
coût et la capacité à aboutir progressent sur ces cas. Ne pas présenter cette branche comme
une garantie de meilleure pertinence sans régression. La priorité suivante est un contrôle
explicite de l'adéquation après lecture (contexte, exclusions et prérequis), puis un regroupement
sémantique des lectures équivalentes et une récupération catalogue au-delà des 3 000 dernières
entrées. Ces travaux et un nouvel audit payant ne sont pas inclus dans cette passe.

Les modifications sont sur la branche dédiée ; aucune fusion ni relance du serveur de
production local n'est effectuée. Les éditions d'audit vivent dans des schémas isolés.
