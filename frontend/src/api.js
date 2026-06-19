const TOKEN_KEY = 'swingbot_token'
export const getToken = () => localStorage.getItem(TOKEN_KEY) || ''
export const setToken = (t) => localStorage.setItem(TOKEN_KEY, t)

async function req(method, path, body) {
  const headers = { 'Content-Type': 'application/json' }
  if (method !== 'GET') headers['X-Token'] = getToken()
  let res
  try {
    res = await fetch(path, {
      method, headers, body: body ? JSON.stringify(body) : undefined,
    })
  } catch (e) {
    const err = new Error('Cannot reach backend')
    err.network = true
    throw err
  }
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail.detail || detail.reason || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  state: () => req('GET', '/api/state'),
  journal: (strategy) => req('GET', strategy ? `/api/journal?strategy=${encodeURIComponent(strategy)}` : '/api/journal'),
  metrics: (strategy) => req('GET', strategy ? `/api/metrics?strategy=${encodeURIComponent(strategy)}` : '/api/metrics'),
  tradingHealth: () => req('GET', '/api/health/trading'),
  listProfiles: () => req('GET', '/api/profiles'),
  getProfile: (name) => req('GET', `/api/profiles/${name}`),
  saveProfile: (name, profile) => req('POST', '/api/profiles', { name, profile }),
  deleteProfile: (name) => req('DELETE', `/api/profiles/${name}`),
  credStatus: () => req('GET', '/api/credentials'),
  setCreds: (key_id, secret_key, base_url) =>
    req('PUT', '/api/credentials', { key_id, secret_key, base_url }),
  control: (action, body) => req('POST', `/api/control/${action}`, body),
  flattenStrategy: (name) => req('POST', `/api/control/${encodeURIComponent(name)}/flatten`),
  candles: (symbol, timeframe, limit = 500) => {
    const q = new URLSearchParams()
    if (symbol) q.set('symbol', symbol)
    if (timeframe) q.set('timeframe', timeframe)
    q.set('limit', String(limit))
    return req('GET', `/api/candles?${q.toString()}`)
  },
  presets: () => req('GET', '/api/presets'),
  buildStrategy: (body) => req('POST', '/api/strategy/build', body),
  backtestProfile: (profile) => req('POST', '/api/strategy/backtest', { profile }),
  // --- portfolio / arming ---
  strategies: () => req('GET', '/api/strategies'),
  arm: (name) => req('POST', '/api/strategies/arm', { name }),
  disarm: (name) => req('POST', '/api/strategies/disarm', { name }),
  setLiveEligible: (name, eligible) => req('POST', '/api/strategies/live-eligible', { name, eligible }),
  portfolioSettings: () => req('GET', '/api/portfolio/settings'),
  setPortfolioSettings: (patch) => req('PUT', '/api/portfolio/settings', patch),
  // --- universe / watchlist ---
  universe: () => req('GET', '/api/universe'),
  watchlist: () => req('GET', '/api/watchlist'),
  setWatchlist: (symbols) => req('PUT', '/api/watchlist', { symbols }),
  // --- discovery ---
  getDiscovery: () => req('GET', '/api/discovery'),
  discoveryWindows: () => req('GET', '/api/discovery/windows'),
  refreshDiscovery: (body) => req('POST', '/api/discovery/refresh', body),
  armDiscovery: (symbol, archetype, window) =>
    req('POST', '/api/discovery/arm', { symbol, archetype, window }),
  // --- decision brain ---
  brainProposals: () => req('GET', '/api/brain/proposals'),
  brainIssues: () => req('GET', '/api/brain/issues'),
  brainRecommend: () => req('POST', '/api/brain/recommend'),
  brainApply: (id) => req('POST', `/api/brain/proposals/${encodeURIComponent(id)}/apply`),
  brainDismiss: (id) => req('POST', `/api/brain/proposals/${encodeURIComponent(id)}/dismiss`),
  brainWebhookStatus: () => req('GET', '/api/brain/webhook'),
  setBrainWebhook: (url) => req('PUT', '/api/brain/webhook', { url }),
  // --- usage agent ---
  agentRuns: () => req('GET', '/api/agent/runs'),
  agentLatest: () => req('GET', '/api/agent/runs/latest'),
  auto: {
    backtestEma: () => req('GET', '/api/backtest/ema'),
    backtestKronos: () => req('GET', '/api/backtest/kronos'),
    position: () => req('GET', '/api/live/position'),
    trades: () => req('GET', '/api/live/trades'),
    journal: () => req('GET', '/api/live/journal'),
    candles: () => req('GET', '/api/live/candles'),
  },
}
