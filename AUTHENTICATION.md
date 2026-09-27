# Comptes Kiosque

La connexion utilise uniquement une adresse e-mail et un mot de passe.
Les comptes, mots de passe hachés avec Argon2id, profils de lecture, sessions et
limitations de tentatives sont enregistrés dans PostgreSQL. Le lecteur
retrouve ses sujets, notes, éditions, favoris et retours depuis un autre navigateur
après connexion au même serveur. Les thèmes restent une préférence de l’appareil.

## Démarrage

1. Installer les dépendances avec `uv sync`.
2. Définir `AUTH_PUBLIC_URL` dans `.env` : l’adresse exacte du lecteur. En développement,
   `http://127.0.0.1:5173/` ; pour le build servi par FastAPI, `http://127.0.0.1:8010/reader/`.
   En production, utiliser une adresse HTTPS, par exemple `https://kiosque.example/reader/`.
3. Redémarrer FastAPI. Les tables `accounts`, `account_sessions`
   et `auth_rate_limits` sont créées par la migration additive habituelle.
4. Créer un compte avec son prénom, son adresse e-mail et un mot de passe d’au moins
   12 caractères, puis choisir ses sujets. L’inscription ne déclenche aucun appel IA.

`AUTH_PUBLIC_URL` doit correspondre à l’origine utilisée dans le navigateur, y compris
le port. Ne pas alterner `localhost` et `127.0.0.1`. Les cookies sont `HttpOnly`,
`SameSite=Lax`, et `Secure` dès que cette adresse est en HTTPS. Les jetons de session
sont aléatoires et seul leur condensat est enregistré en base. Leur durée est donnée
par `AUTH_SESSION_DAYS` (30 jours par défaut). La déconnexion révoque la session côté
serveur ; se reconnecter renouvelle son jeton. Les requêtes privées ne sont pas mises
en cache. Les opérations d’écriture nécessitent un jeton CSRF et une origine autorisée.

L’inscription par e-mail fonctionne sans service d’envoi de messages. Elle ne vérifie
pas la possession de la boîte mail. La vérification par e-mail et la récupération d’un
mot de passe oublié ne sont pas encore proposées : aucun bouton ne promet ces fonctions.

## Administration et anciennes données

Les routes de catalogue, de génération administrative et les pages d’administration
nécessitent désormais un compte administrateur. Aucun compte créé via l’interface ne
reçoit ce rôle. Depuis le terminal du serveur, après création du compte concerné :

```sh
python -m broadwai.account_admin promote administrateur@example.com
# Retirer le rôle :
python -m broadwai.account_admin demote administrateur@example.com
```

Les API lecteur vérifient la session puis l’appartenance de chaque identifiant. Omettre
`user_id` sur une lecture de couverture ne donne plus accès aux couvertures des autres.
Les API d’administration restent accessibles aux opérateurs autorisés, et les tâches
quotidiennes internes continuent à utiliser leurs profils stockés.

Les anciens profils `local-*` et leurs lectures restent en base ; ils ne sont ni supprimés,
ni attribués automatiquement à un nouvel inscrit. Ces profils ne prouvaient pas la
possession d’une adresse e-mail. Un rattachement d’anciennes données nécessite donc une
migration opérateur après vérification du propriétaire. Les profils locaux de navigateur
ne sont plus utilisés comme preuve de connexion.

## Vérification

```sh
uv run pytest -q
# Tests PostgreSQL : utiliser une base de test ; chaque test crée son schéma isolé.
TEST_DATABASE_URL=postgresql://... uv run pytest -q tests/test_auth_postgres.py
cd frontend
pnpm test
pnpm build
```

Les tests couvrent les sessions et leur révocation, les autres navigateurs, le profil
persistant, les restrictions entre lecteurs et administrateurs, CSRF, les limites de
connexion et l’absence de routes de connexion via un fournisseur externe.
Les anciens tests métier utilisent un client opérateur explicite dans `tests/client.py` ;
les tests d’authentification utilisent le vrai contrôle d’accès, sans cette substitution.
