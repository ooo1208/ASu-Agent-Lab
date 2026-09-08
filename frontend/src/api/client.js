const TOKEN_KEY = 'erp_agent_access_token'

export function getAccessToken() {
  return sessionStorage.getItem(TOKEN_KEY)
}

export function setAccessToken(token) {
  sessionStorage.setItem(TOKEN_KEY, token)
}

export function clearAccessToken() {
  sessionStorage.removeItem(TOKEN_KEY)
}

export async function authFetch(url, options = {}) {
  const token = getAccessToken()
  const headers = new Headers(options.headers || {})
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(url, { ...options, headers })
  if (response.status === 401) {
    clearAccessToken()
    window.dispatchEvent(new CustomEvent('auth-expired'))
  }
  return response
}

export async function readApiError(response, fallback) {
  try {
    const data = await response.json()
    return data.detail || fallback
  } catch {
    return fallback
  }
}
