# Événements — démonstration sur catalogue préparé

L’onglet **Événements** du journal affiche jusqu’à six suggestions personnalisées.
Un aperçu de trois cartes apparaît au bas de la une, même sans édition générée.
Les formats **Sortir**, **Regarder** et **Écouter** filtrent le catalogue avant classement.
La démo cible **Paris et alentours** ; les huit sorties initiales sont dans Paris.

## Pipeline

1. `src/events-catalog.js` contient 17 références éditoriales : huit sorties datées
   et neuf émissions, vidéos ou podcasts. Chaque entrée conserve son URL officielle,
   ses thèmes, sa langue, son lieu et la date de consultation de la source.
2. `eligibleEvent` retire les entrées annulées, indisponibles, de langue différente,
   de zone différente, sans lien HTTPS ou sans dates exploitables pour une sortie.
   Une exposition en cours reste éligible ; une sortie future doit commencer d’ici
   14 jours inclus. Les jours sont calculés en **Europe/Paris**, changement d’heure
   compris. Une séance disparaît à son heure de début ; la suivante prend le relais.
3. `selectEvents` compare les tags aux identifiants des sujets cochés du lecteur :
   trois points pour le premier sujet et deux pour chacun des autres sujets communs.
   Une correspondance est obligatoire ; le catalogue ne remplit pas avec du hors sujet.
4. La sélection est gloutonne et déterministe : bonus de deux points par thème du
   lecteur encore absent, deux pour un mode absent (sortie/en ligne), un pour un
   nouveau format ; pénalité d’un point par suggestion déjà choisie de même format.
   Plafond de deux suggestions par organisme et de six au total ; IDs et URLs uniques.
   Les coefficients sont des réglages de démo, sans validation statistique.
5. `Events.jsx` affiche le format, les dates, le lieu ou média, une description,
   les sujets expliquant la sélection et un lien officiel. Le classement suit
   immédiatement les modifications de sujets. La date est réévaluée chaque minute
   et au retour sur l’onglet pour retirer les entrées expirées.

Le calcul se fait dans le navigateur : aucune clé, requête réseau ni génération IA
pour cette rubrique. Aucun changement de schéma backend ou de couverture enregistrée.
Les préférences structurées du Courrier du lecteur, likes et notes libres n’alimentent
pas ce prototype ; l’interface l’explicite. Les suggestions ne sont pas sauvegardées
avec une ancienne édition : elles correspondent aux sujets et à la date actuels.

## Sources et actualisation

Sources consultées le **27 septembre 2026** : pages officielles de la Philharmonie
de Paris, de la Cité des sciences, du Musée des Arts et Métiers, d’ARTE, de Radio France
et du Blob. Les liens exacts figurent dans chaque entrée ; `verificationUrl` complète
la provenance quand la vérification s’appuie sur une page de programmation.
Les descriptions sont reformulées et les tags sont des choix éditoriaux.

- Les sorties ont `startsOn`/`endsOn` (jours ISO), éventuellement `endsAt` (heure
  exacte connue), ou `occurrences` (séances ISO avec fuseau). Sans date d’ouverture
  publiée, `checkedOn` atteste que l’exposition figurait déjà parmi celles en cours.
- `Frontière` utilise le 7 novembre 2027, date de fin dans le titre de la page et
  l’index actuel. La transcription d’une ancienne vidéo mentionne encore janvier 2028.
- La Fête de la science est confirmée les 3 et 4 octobre, de 10 h à 18 h, par
  [l’agenda officiel](https://www.arts-et-metiers.net/manifestations/evenements) ;
  [la notice officielle](https://www.arts-et-metiers.net/node/4459) décrit les
  « Saveurs savantes » et renvoie vers la page événement.
- `availableUntil` retire une vidéo lorsque la fin de disponibilité annoncée est
  atteinte (fin du jour inclus). La captation Ground Control a une échéance au
  7 février 2027. Une archive audio n’est pas supprimée sur son seul âge.
- Les pages de podcasts et collections n’impliquent pas que tous leurs épisodes
  restent lisibles. La lecture effective et les droits géographiques ne sont pas testés.
  Les pages Radio France ont notamment été consultées via leur contenu indexé.

Le catalogue n’est **pas actualisé automatiquement**. Avant une nouvelle démo,
reconsulter les sources, modifier les dates ou marquer `cancelled` / `unavailable`,
puis mettre à jour `checkedOn` et `CATALOG_CHECKED_ON`. Vérifier les créneaux,
annulations, tarifs et places sur le site de l’organisateur ; aucun stock de billets
ni réservation n’est simulé. Certaines catégories, notamment Sport, n’ont pas encore
de suggestion : une vue vide explicite est affichée.

## Vérification

`pnpm test` couvre les dates expirées, l’horizon de 14 jours, les heures de séances,
les changements d’heure, les archives, les filtres, l’adéquation aux intérêts, la
diversité, les doublons et la cohérence du catalogue. `pnpm build` produit le lecteur.
Sur le runtime Windows isolé, `node node_modules/vite/bin/vite.js build --configLoader native`
évite la résolution du fichier de configuration par esbuild hors du workspace.

Pour le contrôle navigateur sans base ni appel payant : compiler le frontend,
puis utiliser le serveur isolé `python -m tests.serve_feedback_fixture` sur le port 8012.
