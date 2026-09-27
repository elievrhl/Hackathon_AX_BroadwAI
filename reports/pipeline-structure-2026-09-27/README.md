# Audit structurel du pipeline — 27 septembre 2026

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
