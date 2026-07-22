export function formatMoney(n) {
  const v = Number(n || 0)
  return '$' + v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function formatSignedPct(frac) {
  const pct = Number(frac || 0) * 100
  const sign = pct >= 0 ? '+' : '-'
  return `${sign}${Math.abs(pct).toFixed(1)}%`
}

export function formatSignedMoney(n) {
  const v = Number(n || 0)
  const sign = v >= 0 ? '+' : '-'
  return `${sign}$${Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}
