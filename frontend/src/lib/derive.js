// Pure view-logic derived from the backend response shapes. No React, no I/O.

export function loopState(health) {
  const lc = health?.lifecycle
  if (!lc) return 'STOPPED'
  if (lc.paused || lc.halted) return 'PAUSED'
  if (lc.running_actual) return 'RUNNING'
  return 'STOPPED'
}

export function modeBadge(state) {
  return String(state?.portfolio?.mode || 'paper').toUpperCase()
}

export function equityOf(state) {
  const e = state?.portfolio?.equity
  return typeof e === 'number' ? e : null
}

export function dayPnl(state) {
  const p = state?.portfolio?.day_pnl
  return typeof p === 'number' ? p : null
}

export function dayPnlPct(state) {
  const eq = equityOf(state)
  const p = dayPnl(state)
  if (eq == null || p == null || eq === 0) return null
  return (p / eq) * 100
}

export function reliabilityPct(health) {
  const r = health?.reliability?.cycle_completion_ratio
  return typeof r === 'number' ? r * 100 : null
}

const AUTH_RE = /unauthor|credential|forbidden|401|403|invalid key/i

export function brokerUnauthorized(health) {
  const err = health?.lifecycle?.startup_error
  return !!(err && AUTH_RE.test(err))
}

export function cardStatus(strategy) {
  const qty = strategy?.position?.qty
  if (typeof qty === 'number' && qty > 0) return 'long'
  if (typeof qty === 'number' && qty < 0) return 'short'
  if (strategy?.running) return 'flat'
  return 'armed'
}

export function availableToAdd(universe, watchlist) {
  const all = universe?.symbols || []
  const have = new Set(watchlist?.symbols || [])
  return all.filter((s) => !have.has(s))
}

export function lastDecision(health, name) {
  const d = health?.last_decisions_by_strategy?.[name]
  if (!d) return null
  return { code: d.decision_code, reason: d.decision_reason }
}
