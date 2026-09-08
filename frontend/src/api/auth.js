import { authFetch, clearAccessToken, getAccessToken, readApiError, setAccessToken } from './client.js'

async function submit(path, payload) {
  const response = await fetch(`/api/auth/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  if (!response.ok) {
    throw new Error(await readApiError(response, '认证失败，请稍后重试'))
  }
  const data = await response.json()
  setAccessToken(data.access_token)
  return data.user
}

export function login(username, password) {
  return submit('login', { username, password })
}

export function register(username, password, displayName) {
  return submit('register', { username, password, display_name: displayName })
}

export async function restoreSession() {
  if (!getAccessToken()) return null
  const response = await authFetch('/api/auth/me')
  if (!response.ok) return null
  return response.json()
}

export function logout() {
  clearAccessToken()
}
