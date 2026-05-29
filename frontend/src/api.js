const TOKEN_KEY = 'swingbot_token'
export const getToken = () => localStorage.getItem(TOKEN_KEY) || ''
export const setToken = (t) => localStorage.setItem(TOKEN_KEY, t)

async function req(method, path, body) {
  const headers = { 'Content-Type': 'application/json' }
  if (method !== 'GET') headers['X-Token'] = getToken()
  const res = await fetch(path, {
    method, headers, body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail.detail || detail.reason || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  state: () => req('GET', '/api/state'),
  journal: () => req('GET', '/api/journal'),
  metrics: () => req('GET', '/api/metrics'),
  listProfiles: () => req('GET', '/api/profiles'),
  activeProfile: () => req('GET', '/api/profiles/active'),
  getProfile: (name) => req('GET', `/api/profiles/${name}`),
  saveProfile: (name, profile) => req('POST', '/api/profiles', { name, profile }),
  setActive: (name) => req('POST', '/api/profiles/active', { name }),
  deleteProfile: (name) => req('DELETE', `/api/profiles/${name}`),
  credStatus: () => req('GET', '/api/credentials'),
  setCreds: (key_id, secret_key, base_url) =>
    req('PUT', '/api/credentials', { key_id, secret_key, base_url }),
  control: (action, body) => req('POST', `/api/control/${action}`, body),
}
