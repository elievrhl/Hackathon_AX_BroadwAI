// Prepared editorial catalogue. Sources were consulted on 27 September 2026.
// Tags are editorial choices; dates and venues come from the linked official pages.
// No live ticket inventory or playback availability is implied by this catalogue.
export const CATALOG_CHECKED_ON = '2026-09-27';

const paris = { mode: 'out', area: 'paris', language: 'fr', checkedOn: CATALOG_CHECKED_ON };
const online = { mode: 'online', language: 'fr', checkedOn: CATALOG_CHECKED_ON };

export const EVENTS_CATALOG = [
  {
    ...paris, id: 'video-games-music', kind: 'exhibition', title: 'Video Games & Music',
    description: 'Des premières bandes-son 8 bits aux orchestres : une histoire musicale du jeu vidéo à parcourir et à écouter.',
    topics: ['gaming', 'music', 'culture'], provider: 'Philharmonie de Paris',
    venue: 'Philharmonie de Paris · Paris 19e', startsOn: '2026-04-02', endsOn: '2026-11-01',
    practical: 'Réservation indispensable. Horaires et tarifs sur le site.',
    url: 'https://philharmoniedeparis.fr/fr/activite/exposition/28822-video-games-music',
  },
  {
    ...paris, id: 'hassan-hajjaj', kind: 'exhibition', title: 'Hassan Hajjaj · My Rock Stars',
    description: 'Des portraits de musiciens par Hassan Hajjaj rencontrent une création sonore d’Acid Arab, entre photographie et cultures musicales.',
    topics: ['art', 'music', 'culture'], provider: 'Philharmonie de Paris',
    venue: 'Musée de la musique · Paris 19e', startsOn: '2026-09-22', endsOn: '2027-04-25',
    practical: 'Réservation indispensable. Horaires et tarifs sur le site.',
    url: 'https://philharmoniedeparis.fr/fr/activite/exposition/30026-hassan-hajjaj-my-rock-stars',
  },
  {
    ...paris, id: 'esprit-critique', kind: 'exhibition', title: 'Esprit critique · Venez vous tester',
    description: 'Un parcours d’expériences pour observer nos biais, questionner les informations et comprendre comment se construisent nos jugements.',
    topics: ['science', 'philosophy', 'education', 'world'], provider: 'Cité des sciences',
    venue: 'Cité des sciences et de l’industrie · Paris 19e', endsOn: '2027-08-29',
    practical: 'À partir de 10 ans. Horaires et tarifs sur le site.',
    url: 'https://www.cite-sciences.fr/fr/au-programme/expos-temporaires/esprit-critique-venez-vous-tester',
  },
  {
    ...paris, id: 'frontiere', kind: 'exhibition', title: 'Frontière',
    description: 'Cartes, récits et regards de chercheurs pour explorer les frontières, leurs effets sur les populations et les échanges entre territoires.',
    topics: ['world', 'travel', 'economy', 'history'], provider: 'Cité des sciences',
    venue: 'Cité des sciences et de l’industrie · Paris 19e', startsOn: '2026-04-14', endsOn: '2027-11-07',
    // Current page heading and exhibition index agree on this end date; an older
    // video transcript on the same page still mentions 2 January 2028.
    practical: 'À partir de 12 ans. Horaires et tarifs sur le site.',
    url: 'https://www.cite-sciences.fr/fr/au-programme/expos-temporaires/frontiere',
  },
  {
    ...paris, id: 'ecran-total', kind: 'exhibition', title: 'Écran total · Gillian Brett',
    description: 'Des écrans transformés en œuvres pour regarder autrement nos technologies, le ciel et les traces écologiques de nos usages numériques.',
    topics: ['tech', 'art', 'space', 'climate'], provider: 'Cité des sciences',
    venue: 'Cité des sciences et de l’industrie · Paris 19e', endsOn: '2026-11-01',
    practical: 'À partir de 9 ans. Horaires et tarifs sur le site.',
    url: 'https://www.cite-sciences.fr/fr/au-programme/expos-temporaires/ecran-total-carte-blanche-a-gillian-brett',
  },
  {
    ...paris, id: 'machine-a-ecrire', kind: 'exhibition', title: 'Machine arrière · La machine à écrire',
    description: 'Une traversée de l’histoire du clavier et du travail de bureau, avec des objets, des récits et une immersion sonore dans les années 1930.',
    topics: ['tech', 'history', 'books'], provider: 'Cité des sciences',
    venue: 'Cité des sciences et de l’industrie · Paris 19e', endsOn: '2026-11-01',
    practical: 'À partir de 15 ans. Horaires et tarifs sur le site.',
    url: 'https://www.cite-sciences.fr/fr/au-programme/expos-temporaires/machine-arriere-2-la-machine-a-ecrire',
  },
  {
    ...paris, id: 'fete-science-arts-metiers', kind: 'event', title: 'Fête de la science aux Arts et Métiers',
    description: 'Un week-end au musée pour rencontrer les sciences et les techniques, avec une programmation autour des « Saveurs savantes ».',
    topics: ['science', 'tech', 'food', 'education'], provider: 'Musée des Arts et Métiers',
    venue: 'Musée des Arts et Métiers · Paris 3e', startsOn: '2026-10-03', endsOn: '2026-10-04',
    endsAt: '2026-10-04T18:00:00+02:00', practical: 'Les 3 et 4 octobre, de 10 h à 18 h. Programme sur le site.',
    url: 'https://www.arts-et-metiers.net/musee/week-end-fete-de-la-science',
    verificationUrl: 'https://www.arts-et-metiers.net/manifestations/evenements',
  },
  {
    ...paris, id: 'chailly-orchestre-paris', kind: 'concert', title: 'Orchestre de Paris · Riccardo Chailly',
    description: 'Tchaïkovski, Prokofiev, Barber et Bernstein réunis dans un programme traversé par les amants de Vérone.',
    topics: ['music', 'culture'], provider: 'Philharmonie de Paris',
    venue: 'Grande salle Pierre Boulez · Paris 19e',
    occurrences: ['2026-09-30T20:00:00+02:00', '2026-10-01T20:00:00+02:00'],
    practical: 'Durée annoncée : environ 1 h 34 avec entracte. Places et tarifs sur le site.',
    url: 'https://philharmoniedeparis.fr/fr/activite/concert-symphonique/29620-orchestre-de-paris-riccardo-chailly',
  },
  {
    ...online, id: 'dessous-des-cartes', kind: 'show', title: 'Le dessous des cartes',
    description: 'Des cartes pour éclairer la géopolitique, les ressources et les grands échanges qui organisent le monde.',
    topics: ['world', 'economy', 'travel', 'climate'], provider: 'ARTE', venue: 'ARTE · En ligne',
    practical: 'Une émission à retrouver sur le site d’ARTE ; disponibilité selon les épisodes.',
    url: 'https://www.arte.tv/fr/videos/RC-014036/le-dessous-des-cartes/',
  },
  {
    ...online, id: 'dessous-des-images', kind: 'show', title: 'Le dessous des images',
    description: 'Un regard sur la fabrication et la circulation des images pour comprendre ce qu’elles nous font voir, croire ou ressentir.',
    topics: ['art', 'world', 'tech', 'cinema'], provider: 'ARTE', venue: 'ARTE · En ligne',
    practical: 'Une émission à retrouver sur le site d’ARTE ; disponibilité selon les épisodes.',
    url: 'https://www.arte.tv/fr/videos/RC-023176/le-dessous-des-images/',
  },
  {
    ...online, id: 'science-cqfd', kind: 'podcast', title: 'La Science, CQFD',
    description: 'Des conversations avec des chercheurs pour explorer les découvertes, leurs méthodes et les questions qu’elles ouvrent.',
    topics: ['science', 'tech', 'space', 'health', 'climate'], provider: 'Radio France', venue: 'France Culture · En ligne',
    practical: 'Choisissez un épisode dans la collection du podcast.',
    url: 'https://www.radiofrance.fr/franceculture/podcasts/la-science-cqfd',
  },
  {
    ...online, id: 'condition-artiste', kind: 'podcast', title: 'Aux origines de la condition de l’artiste',
    description: 'Un épisode d’Entendez-vous l’éco ? sur la place des artistes dans la société et les conditions matérielles de la création.',
    topics: ['economy', 'art', 'culture', 'history', 'business'], provider: 'Radio France', venue: 'France Culture · En ligne',
    publishedOn: '2018-10-15', practical: 'Archive · 58 min · Entendez-vous l’éco ?',
    url: 'https://www.radiofrance.fr/franceculture/podcasts/entendez-vous-l-eco/aux-origines-de-la-condition-de-l-artiste-7276870',
  },
  {
    ...online, id: 'galaxie-comics', kind: 'podcast', title: 'Galaxie comics',
    description: 'Une collection de Blockbusters pour parcourir les univers Marvel et DC, leurs personnages et les artistes qui les ont façonnés.',
    topics: ['books', 'cinema', 'culture'], provider: 'Radio France', venue: 'France Inter · En ligne',
    practical: 'Une série de podcasts à explorer dans les archives de France Inter.',
    url: 'https://www.radiofrance.fr/franceinter/podcasts/serie-galaxie-comics',
  },
  {
    ...online, id: 'tout-un-plat', kind: 'show', title: 'On va déguster… Tout un plat',
    description: 'François-Régis Gaudry explore l’histoire et la préparation de classiques culinaires dans cette collection de vidéos.',
    topics: ['food'], provider: 'Radio France', venue: 'France Inter · En ligne',
    practical: 'Collection de vidéos culinaires ; choisissez un sujet sur le site.',
    url: 'https://www.radiofrance.fr/dossiers/on-va-deguster-tout-un-plat',
  },
  {
    ...online, id: 'remington-1908', kind: 'show', title: 'La machine à écrire Remington, 1908',
    description: 'Un court film pour découvrir les mécanismes d’une machine à écrire et un objet de l’histoire des communications.',
    topics: ['tech', 'history', 'books'], provider: 'Le blob', venue: 'Le blob · En ligne',
    practical: '7 min 54 · Série Théâtre des machines.',
    url: 'https://leblob.fr/videos/machine-ecrire-remington-1908',
  },
];
