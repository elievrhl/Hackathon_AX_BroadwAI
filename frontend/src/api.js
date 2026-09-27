// Same-origin requests: Vite proxies these paths in development; FastAPI serves the build.
export class ApiError extends Error {
  constructor(message, status = 0) { super(message); this.status = status; }
}

export async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      ...options, headers: { Accept: 'application/json', ...options.headers },
    });
  } catch {
    throw new ApiError('Le serveur est inaccessible. Vérifiez que le backend tourne, puis consultez l’historique avant de relancer une génération.');
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const messages = {
      429: 'Une couverture est déjà en préparation. Attendez sa fin et actualisez l’historique.',
      503: 'La génération est indisponible. Vérifiez la clé API et les modèles dans le fichier .env du serveur.',
      504: 'La préparation a dépassé le délai disponible. Les résumés déjà créés sont conservés. Consultez l’historique avant de réessayer.',
    };
    throw new ApiError(messages[response.status] || (typeof data?.detail === 'string' ? data.detail : `Erreur du serveur (${response.status}).`), response.status);
  }
  if (data === null) throw new ApiError('Le serveur n’a pas renvoyé une réponse JSON. Vérifiez le proxy de l’API.');
  return data;
}

const post = (path, body) => request(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
export const getHealth = () => request('/health');
export const getLikes = userId => request(`/v1/likes?user_id=${encodeURIComponent(userId)}`);
export const setLike = payload => request('/v1/likes', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
export const listCovers = userId => request(`/v1/covers?limit=100${userId ? `&user_id=${encodeURIComponent(userId)}` : ''}`);
export const getCover = (id, userId) => request(`/v1/covers/${encodeURIComponent(id)}${userId ? `?user_id=${encodeURIComponent(userId)}` : ''}`);
export const createCover = payload => post('/v1/covers', payload);
export const sendFeedback = payload => post('/v1/feedback', payload);

export const getLibrary = userId => request(`/v1/library?user_id=${encodeURIComponent(userId)}`);
export const saveEdition = (userId, id) => request(`/v1/library/${encodeURIComponent(id)}?user_id=${encodeURIComponent(userId)}`, { method: 'PUT' });
export const removeEdition = (userId, id) => request(`/v1/library/${encodeURIComponent(id)}?user_id=${encodeURIComponent(userId)}`, { method: 'DELETE' });

const collectionPath = (userId, id = '') => `/v1/collections${id ? `/${encodeURIComponent(id)}` : ''}?user_id=${encodeURIComponent(userId)}`;
const jsonRequest = (path, method, body) => request(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
export const getCollections = userId => request(collectionPath(userId));
export const getCollection = (userId, id) => request(collectionPath(userId, id));
export const createCollection = (userId, data) => jsonRequest(collectionPath(userId), 'POST', data);
export const editCollection = (userId, id, data) => jsonRequest(collectionPath(userId, id), 'PATCH', data);
export const deleteCollection = (userId, id) => request(collectionPath(userId, id), { method: 'DELETE' });
export const addToCollection = (userId, id, articleId, coverId) => jsonRequest(`/v1/collections/${encodeURIComponent(id)}/articles/${encodeURIComponent(articleId)}?user_id=${encodeURIComponent(userId)}`, 'PUT', { cover_id: coverId || null });
export const removeFromCollection = (userId, id, articleId) => request(`/v1/collections/${encodeURIComponent(id)}/articles/${encodeURIComponent(articleId)}?user_id=${encodeURIComponent(userId)}`, { method: 'DELETE' });
export const importBookmarks = (userId, articleIds) => jsonRequest(`/v1/collections/import-bookmarks?user_id=${encodeURIComponent(userId)}`, 'POST', { article_ids: articleIds });
