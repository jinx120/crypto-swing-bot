# Phase 0 — Frontend Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the current dashboard breakage — misplaced tooltips, "value is null" crashes, bad-symbol crashes, and silent backend-unreachable failures — without depending on any backend change.

**Architecture:** Pure frontend fixes. Render `Hint` tooltips through a `createPortal` to `document.body` so a `backdrop-filter` ancestor no longer captures their `position: fixed`. Harden `ChartPanel` against empty/garbage candle data. Make the API client distinguish network failures from HTTP errors, and have `App` show a clear "backend unreachable" banner.

**Tech Stack:** React 18, Vite. No JS test runner exists in this repo, so verification is `npm run build` (must succeed) plus the manual checks each task lists. Do **not** add a test framework in this phase.

**Reference:** Design spec `docs/superpowers/specs/2026-05-31-multi-asset-concurrent-trading-design.md` §3, §8.1.

**Working directory for all commands:** `frontend/` unless stated otherwise.

---

### Task 1: Tooltips render through a body portal

The `Hint` tooltip uses `position: fixed` with viewport coordinates, but renders inside
`.panel`/`.nav`, which set `backdrop-filter`. A `backdrop-filter` ancestor becomes the
containing block for `fixed` descendants, so the computed viewport coordinates and the
actual render disagree — tooltips appear in random spots. Fix: portal the tip to
`document.body`.

**Files:**
- Modify: `frontend/src/components/Hint.jsx`

- [ ] **Step 1: Add the portal import**

At the top of `frontend/src/components/Hint.jsx`, change the React import line to also
import `createPortal`:

```jsx
import { useRef, useState, useCallback } from 'react'
import { createPortal } from 'react-dom'
```

- [ ] **Step 2: Wrap the tooltip span in createPortal**

Replace the `return (...)` block's tooltip rendering. The full new return:

```jsx
  return (
    <span ref={ref} className="hint" tabIndex={0} role="note" aria-label={text}
      onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}>
      i
      {pos && createPortal(
        <span className={`hint-tip ${pos.above ? 'is-above' : 'is-below'}`}
          style={{
            left: pos.left, top: pos.top, width: pos.w,
            transform: pos.above ? 'translateY(-100%)' : 'none',
            marginTop: pos.above ? -8 : 8,
            '--arrow-x': `${pos.arrowX}px`,
          }}>
          {text}
        </span>,
        document.body
      )}
    </span>
  )
```

(Only the tooltip `<span>` is now wrapped by `createPortal(..., document.body)`; the
trigger `<span className="hint">` and its `i` text stay where they are. The position math
in `show()` is unchanged.)

- [ ] **Step 3: Build and manually verify**

Run (from `frontend/`): `npm run build`
Expected: build succeeds with no errors.

Manual check (`npm run dev`, then hover an `ⓘ` inside a glass panel deep on the page):
the tooltip appears directly next to the `ⓘ`, not offset into a random corner. Scroll the
page and hover again — still anchored correctly.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Hint.jsx
git commit -m "fix(ui): portal Hint tooltip to body to escape backdrop-filter containing block"
```

---

### Task 2: ChartPanel survives empty / malformed / bad-symbol data

When a symbol returns no candles (e.g. an unsupported pair like `BTC/USDT`), or a candle
field is null, the chart must not throw. Sanitize before `setData` and show a clear
bad-symbol empty-state.

**Files:**
- Modify: `frontend/src/components/ChartPanel.jsx`

- [ ] **Step 1: Add a candle sanitizer helper**

In `frontend/src/components/ChartPanel.jsx`, just below the `ema(...)` function (before
`tradeMarkers`), add:

```jsx
// keep only candles whose numeric fields are all finite — guards setData against nulls
function sanitize(candles) {
  if (!Array.isArray(candles)) return []
  return candles.filter(c =>
    c && [c.time, c.open, c.high, c.low, c.close].every(Number.isFinite))
}
```

- [ ] **Step 2: Use the sanitizer in the load effect**

In the `load` async function inside the fetch `useEffect`, replace:

```jsx
        const candles = r.candles || []
        dataRef.current = candles
        setCount(candles.length)
        candleRef.current?.setData(candles.map(c => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close })))
        volRef.current?.setData(candles.map(c => ({ time: c.time, value: c.volume,
          color: c.close >= c.open ? 'rgba(54,209,122,0.4)' : 'rgba(255,84,112,0.4)' })))
```

with:

```jsx
        const candles = sanitize(r.candles)
        dataRef.current = candles
        setCount(candles.length)
        candleRef.current?.setData(candles.map(c => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close })))
        volRef.current?.setData(candles.map(c => ({ time: c.time, value: Number.isFinite(c.volume) ? c.volume : 0,
          color: c.close >= c.open ? 'rgba(54,209,122,0.4)' : 'rgba(255,84,112,0.4)' })))
```

- [ ] **Step 3: Show a bad-symbol empty-state**

Replace the existing empty-state block:

```jsx
      {count === 0 && !err && (
        <div className="chart-empty">Waiting for market data — set Alpaca credentials and an active strategy, then the poller fills this in within a minute.</div>
      )}
```

with:

```jsx
      {count === 0 && !err && (
        <div className="chart-empty">No candles for <b>{label}</b>. If you just set this up, the poller fills this in within a minute. If it stays empty, check the symbol — Alpaca uses pairs like <code>BTC/USD</code> (not <code>BTC/USDT</code>).</div>
      )}
```

- [ ] **Step 4: Build and manually verify**

Run (from `frontend/`): `npm run build`
Expected: build succeeds.

Manual check: with the dev server running, the chart panel renders without a console
crash even when `/api/candles` returns `{"candles": []}`; the bad-symbol message shows.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ChartPanel.jsx
git commit -m "fix(ui): harden ChartPanel against empty/malformed candles and bad symbols"
```

---

### Task 3: API client distinguishes network failure from HTTP error

`fetch` rejects (throws) on DNS/connection failure (`ERR_NAME_NOT_RESOLVED`) before any
response exists. Tag those errors so the UI can show a dedicated banner instead of a
generic message.

**Files:**
- Modify: `frontend/src/api.js`

- [ ] **Step 1: Wrap fetch and tag network errors**

In `frontend/src/api.js`, replace the body of `async function req(method, path, body)`
with:

```jsx
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
```

- [ ] **Step 2: Build**

Run (from `frontend/`): `npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.js
git commit -m "feat(ui): tag network failures so the UI can distinguish backend-unreachable"
```

---

### Task 4: App shows a backend-unreachable banner

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Track an unreachable flag and set it in refresh**

In `frontend/src/App.jsx`, add an `unreachable` state and set it in `refresh`. Replace the
`const [err, setErr] = useState('')` line with:

```jsx
  const [err, setErr] = useState('')
  const [unreachable, setUnreachable] = useState(false)
```

Replace the `refresh` callback body with:

```jsx
  const refresh = useCallback(async()=>{
    try {
      const s = await api.state(); setState(s); setErr(''); setUnreachable(false)
      setTrades(await api.journal()); setMetrics(await api.metrics())
    } catch(e){ setErr(e.message); if (e.network) setUnreachable(true) }
  }, [])
```

- [ ] **Step 2: Render the banner**

Immediately after the `<div className="nav"> ... </div>` block closes (before the
`{tab==='dashboard' && <StatusBanner .../>}` line), insert:

```jsx
      {unreachable && <div className="err" style={{padding:'10px 20px'}}>
        Cannot reach the backend. The dashboard can't resolve or connect to its API host.
        Check that <code>swingbot-web</code> is running and that you're loading this page
        from a resolvable host (or via the Vite <code>/api</code> proxy on port 3000).
      </div>}
```

- [ ] **Step 3: Build and manually verify**

Run (from `frontend/`): `npm run build`
Expected: build succeeds.

Manual check: stop the backend (or load the UI from a bad host) and confirm the
unreachable banner appears instead of the page silently showing dashes.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.jsx
git commit -m "feat(ui): show backend-unreachable banner on network failure"
```

---

## Self-Review Notes (for the implementer)

- Spec coverage: §8.1 tooltip portal (Task 1), null-safety (Task 2), bad-symbol (Task 2),
  backend-unreachable surfacing (Tasks 3-4). All covered.
- This phase is intentionally backend-independent: every change is in `frontend/src/` and
  verified by `npm run build` + manual inspection.
- Do not rename CSS classes; the glass theme keys off `.hint`, `.hint-tip`, `.chart-empty`,
  `.err`.
