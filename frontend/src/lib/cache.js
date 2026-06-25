// Stale-while-revalidate cache backed by localStorage. All errors are swallowed
// so the UI never breaks on quota limits or a missing storage API.
export function readCache(key) {
  try {
    const raw = globalThis.localStorage?.getItem(key)
    return raw ? JSON.parse(raw) : null
  } catch { return null }
}

export function writeCache(key, data) {
  try { globalThis.localStorage?.setItem(key, JSON.stringify(data)) } catch { /* ignore */ }
}
