// Local demonstration only. Passwords never leave the form or enter storage.
const ACCOUNTS = 'kiosque.accounts.v1';
const SESSION = 'kiosque.session.v1';
export const accountKey = (id, key) => `${key}:${id}`;
export function readLocal(key, fallback = null, storage = localStorage) {
  try { return JSON.parse(storage.getItem(key)) ?? fallback; } catch { return fallback; }
}
export function currentAccount(storage = localStorage) {
  const accounts = readLocal(ACCOUNTS, [], storage);
  return Array.isArray(accounts) ? accounts.find(a => a.id === readLocal(SESSION, null, storage)) || null : null;
}
export function enterAccount({ email, name, create }, storage = localStorage) {
  const address = email.trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(address)) throw new Error('Indiquez une adresse e-mail valide.');
  const accounts = readLocal(ACCOUNTS, [], storage);
  if (!Array.isArray(accounts)) throw new Error('La liste des comptes locaux est illisible.');
  let account = accounts.find(a => a.email === address);
  if (create && account) throw new Error('Ce profil existe déjà sur cet appareil. Retrouvez-le avec votre adresse e-mail.');
  if (!create && !account) throw new Error('Créez d’abord votre profil sur cet appareil.');
  if (create) {
    if (!name.trim()) throw new Error('Indiquez votre prénom.');
    const legacy = accounts.length === 0 ? readLocal('kiosque.user', null, storage) : null;
    const id = typeof legacy === 'string' && /^local-[a-z0-9-]{1,80}$/i.test(legacy) ? legacy : `local-${crypto.randomUUID()}`;
    account = { id, email: address, name: name.trim().slice(0, 40) };
    if (accounts.length === 0) {
      for (const key of ['kiosque.reader.v1', 'kiosque.saved', 'kiosque.lastCover', 'kiosque.pending']) {
        const value = storage.getItem(key);
        if (value !== null) storage.setItem(accountKey(id, key), value);
      }
    }
    storage.setItem(ACCOUNTS, JSON.stringify([...accounts, account]));
  }
  storage.setItem(SESSION, JSON.stringify(account.id));
  return account;
}
export function leaveAccount(storage = localStorage) { storage.removeItem(SESSION); }
