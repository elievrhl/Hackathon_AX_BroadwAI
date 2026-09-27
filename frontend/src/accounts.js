import { request, setCsrfToken } from './api.js';

// Only non-sensitive device preferences remain in local storage.
export const accountKey = (id, key) => `${key}:${id}`;
export function readLocal(key, fallback = null, storage = localStorage) {
  try { return JSON.parse(storage.getItem(key)) ?? fallback; } catch { return fallback; }
}
export async function currentAccount() {
  const session = await request('/v1/auth/session');
  setCsrfToken(session.csrf_token);
  return session;
}
export async function enterAccount({ email, name, password, create }) {
  const session = await request(`/v1/auth/${create ? 'register' : 'login'}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: email.trim(), password, ...(create ? { name: name.trim() } : {}) }),
  });
  setCsrfToken(session.csrf_token);
  return session.account;
}
export async function leaveAccount() {
  await request('/v1/auth/logout', { method: 'POST' });
  setCsrfToken(null);
}
export async function saveAccountProfile(profile) {
  const result = await request('/v1/auth/profile', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ profile }),
  });
  return result.account;
}
