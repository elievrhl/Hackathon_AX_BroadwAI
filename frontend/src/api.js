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
    if (path.includes('/messages')) throw new ApiError('La connexion avec Kiosque a été interrompue. Votre message est conservé : vous pouvez réessayer.');
    throw new ApiError('Kiosque est momentanément inaccessible. Réessayez dans quelques instants.');
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const messages = {
      401: 'Ouvrez votre espace de lecture pour continuer.',
      403: 'Cette action n’est pas disponible pour votre profil.',
      429: 'Cette action est déjà en cours. Patientez quelques instants.',
      503: 'Ce service est momentanément indisponible. Réessayez un peu plus tard.',
      504: 'L’opération prend plus de temps que prévu. Réessayez dans quelques instants.',
    };
    const detail = [400, 404, 409, 422].includes(response.status) && typeof data?.detail === 'string'
      ? data.detail : null;
    const message = messages[response.status] || detail || (path.includes('/messages')
      ? 'Votre message n’a pas pu être traité. Il est conservé pour réessayer.'
      : 'Cette action n’a pas pu aboutir. Réessayez dans quelques instants.');
    throw new ApiError(message, response.status);
  }
  if (data === null) throw new ApiError('La réponse de Kiosque n’a pas pu être lue. Réessayez dans quelques instants.');
  return data;
}

const post = (path, body, options = {}) => request(path, { ...options, method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
export const getHealth = () => request('/health');
export const getLikes = userId => request(`/v1/likes?user_id=${encodeURIComponent(userId)}`);
export const setLike = payload => request('/v1/likes', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
export const listCovers = userId => request(`/v1/covers?limit=100${userId ? `&user_id=${encodeURIComponent(userId)}` : ''}`);
export const getCover = (id, userId) => request(`/v1/covers/${encodeURIComponent(id)}${userId ? `?user_id=${encodeURIComponent(userId)}` : ''}`);
export const createCover = payload => post('/v1/covers', payload);
// Article links navigate immediately; finish recording the open event after unload.
export const sendFeedback = payload => post('/v1/feedback', payload, { keepalive: payload.kind === 'open' });

export const getLibrary = userId => request(`/v1/library?user_id=${encodeURIComponent(userId)}`);
export const saveEdition = (userId, id) => request(`/v1/library/${encodeURIComponent(id)}?user_id=${encodeURIComponent(userId)}`, { method: 'PUT' });
export const removeEdition = (userId, id) => request(`/v1/library/${encodeURIComponent(id)}?user_id=${encodeURIComponent(userId)}`, { method: 'DELETE' });

const collectionPath = (userId, id = '') => `/v1/collections${id ? `/${encodeURIComponent(id)}` : ''}?user_id=${encodeURIComponent(userId)}`;
const jsonRequest = (path, method, body) => request(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
export const getArchives = userId => request(`/v1/archives?user_id=${encodeURIComponent(userId)}`);
export const getSavedArticles = userId => request(`/v1/saved-articles?user_id=${encodeURIComponent(userId)}`);
export const saveArticle = (userId, articleId, coverId) => jsonRequest(`/v1/saved-articles/${encodeURIComponent(articleId)}?user_id=${encodeURIComponent(userId)}`, 'PUT', { cover_id: coverId || null });
export const unsaveArticle = (userId, articleId) => request(`/v1/saved-articles/${encodeURIComponent(articleId)}?user_id=${encodeURIComponent(userId)}`, { method: 'DELETE' });
export const getCollections = userId => request(collectionPath(userId));
export const getCollection = (userId, id) => request(collectionPath(userId, id));
export const createCollection = (userId, data) => jsonRequest(collectionPath(userId), 'POST', data);
export const editCollection = (userId, id, data) => jsonRequest(collectionPath(userId, id), 'PATCH', data);
export const deleteCollection = (userId, id) => request(collectionPath(userId, id), { method: 'DELETE' });
export const addToCollection = (userId, id, articleId, coverId) => jsonRequest(`/v1/collections/${encodeURIComponent(id)}/articles/${encodeURIComponent(articleId)}?user_id=${encodeURIComponent(userId)}`, 'PUT', { cover_id: coverId || null });
export const removeFromCollection = (userId, id, articleId) => request(`/v1/collections/${encodeURIComponent(id)}/articles/${encodeURIComponent(articleId)}?user_id=${encodeURIComponent(userId)}`, { method: 'DELETE' });
export const importBookmarks = (userId, articleIds) => jsonRequest(`/v1/collections/import-bookmarks?user_id=${encodeURIComponent(userId)}`, 'POST', { article_ids: articleIds });

const readerPath = userId => `/v1/readers/${encodeURIComponent(userId)}`;
export const registerDailyEdition = (userId, payload) => jsonRequest(`${readerPath(userId)}/daily-edition`, 'PUT', payload);
export const getDailyEdition = userId => request(`${readerPath(userId)}/daily-edition`);
export const getReaderFeedback = (userId, coverId) => request(`${readerPath(userId)}/feedback/${encodeURIComponent(coverId)}`);
export const getPreferences = userId => request(`${readerPath(userId)}/preferences`);
export const getReaderMessages = userId => request(`${readerPath(userId)}/messages`);
export const sendReaderMessage = (userId, value) => post(`${readerPath(userId)}/messages`, value);
export const createPreference = (userId, value) => post(`${readerPath(userId)}/preferences`, value);
export const updatePreference = (userId, id, value) => request(`${readerPath(userId)}/preferences/${encodeURIComponent(id)}`, {
  method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value),
});
export const deletePreference = (userId, id, revision) => request(`${readerPath(userId)}/preferences/${encodeURIComponent(id)}?revision=${revision}`, { method: 'DELETE' });
