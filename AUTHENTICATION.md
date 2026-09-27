# Comptes Kiosque

Les comptes, mots de passe hachés avec Argon2id, profils de lecture, identités OAuth,
sessions et limitations de tentatives sont enregistrés dans PostgreSQL. Le lecteur
retrouve ses sujets, notes, éditions, favoris et retours depuis un autre navigateur
après connexion au même serveur. Les thèmes restent une préférence de l’appareil.

## Démarrage

1. Installer les dépendances avec `uv sync`.
2. Définir `AUTH_PUBLIC_URL` dans `.env` : l’adresse exacte du lecteur. En développement,
   `http://127.0.0.1:5173/` ; pour le build servi par FastAPI, `http://127.0.0.1:8010/reader/`.
   En production, utiliser une adresse HTTPS, par exemple `https://kiosque.example/reader/`.
3. Redémarrer FastAPI. Les tables `accounts`, `account_identities`, `account_sessions`,
   `oauth_flows` et `auth_rate_limits` sont créées par la migration additive habituelle.
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
Google et Apple, lorsqu’ils sont configurés, exigent une adresse vérifiée dans leur
jeton signé. Un compte e-mail existant n’est jamais automatiquement associé à une
identité Google/Apple portant la même adresse. Utiliser sa méthode de connexion initiale.

## Connexion Google

Dans la [console Google Cloud](https://console.cloud.google.com/apis/credentials),
configurer l’écran de consentement et créer un client OAuth de type **Application Web**.
Déclarer l’URL de redirection exacte :

- développement : `http://127.0.0.1:5173/v1/auth/google/callback` ;
- production : `https://kiosque.example/v1/auth/google/callback`.

Définir `GOOGLE_CLIENT_ID` et `GOOGLE_CLIENT_SECRET` sur le serveur, puis redémarrer.
Ajouter les comptes de test à l’écran de consentement si l’application Google est en
mode test. Le parcours utilise le code d’autorisation, PKCE S256, un état à usage unique
lié au navigateur et un nonce. Le serveur vérifie la signature, l’émetteur, l’audience,
la validité temporelle, le nonce et l’adresse vérifiée du jeton d’identité.

Référence : [Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect).

## Connexion Apple

Dans [Apple Developer](https://developer.apple.com/account/resources/identifiers/list),
activer Sign in with Apple pour l’App ID principal, puis créer un **Services ID** pour
le site et le rattacher à cet App ID. Déclarer le domaine et l’URL de retour :
`https://kiosque.example/v1/auth/apple/callback`.
Apple exige un domaine HTTPS : `localhost` et les adresses IP ne conviennent pas.

Créer une clé Sign in with Apple, télécharger le fichier `.p8`, puis définir :

- `APPLE_CLIENT_ID` : le Services ID du site ;
- `APPLE_TEAM_ID` et `APPLE_KEY_ID` : les identifiants Apple Developer ;
- `APPLE_PRIVATE_KEY_PATH` : chemin du fichier `.p8` lisible par le serveur ;
- `AUTH_PUBLIC_URL` : adresse publique HTTPS du lecteur.

Conserver le fichier `.p8` hors du dépôt et des répertoires servis publiquement.
Le serveur signe un secret client ES256 de courte durée, échange le code, vérifie le
jeton d’identité et accepte les adresses de relais privé Apple. Le retour Apple est
un POST de formulaire ; son cookie de liaison est `HttpOnly; Secure; SameSite=None`,
à usage unique et limité à dix minutes. Ce cookie temporaire est distinct de la session.

Références : [Apple sur le Web](https://developer.apple.com/documentation/signinwithapple/incorporating-sign-in-with-apple-into-other-platforms),
[validation des jetons](https://developer.apple.com/documentation/signinwithapplerestapi/generate-and-validate-tokens).

Les boutons Google/Apple restent désactivés tant que leurs paramètres nécessaires ne
sont pas renseignés. Le code des deux parcours est couvert par des tests ; une connexion
réelle chez chaque fournisseur doit être validée après configuration de ses identifiants.

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
connexion, les signatures OIDC, la réutilisation d’un état OAuth et le retour POST Apple.
Les anciens tests métier utilisent un client opérateur explicite dans `tests/client.py` ;
les tests d’authentification utilisent le vrai contrôle d’accès, sans cette substitution.
