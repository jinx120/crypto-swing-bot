import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'

const fmtTs = (ts) => ts ? new Date(ts * 1000).toLocaleString() : '—'

function StepRow({ s }) {
  return (
    <li style={{ fontSize: 12, margin: '2px 0' }}>
      <span style={{ color: s.ok ? 'var(--green)' : 'var(--red)' }}>{s.ok ? '✓' : '✗'}</span>{' '}
      {s.desc}{s.detail && <span style={{ color: 'var(--muted)' }}> — {s.detail}</span>}
      {s.screenshot_path && (
        <a style={{ marginLeft: 6 }} target="_blank" rel="noreferrer"
          href={`/api/agent/artifacts/${encodeURIComponent(s.screenshot_path.split('/').pop())}`}>screenshot</a>
      )}
    </li>
  )
}

export default function Health() {
  const [latest, setLatest] = useState(null)
  const [runs, setRuns] = useState([])
  const [drift, setDrift] = useState([])
  const [err, setErr] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [l, r, props] = await Promise.all([
        api.agentLatest(), api.agentRuns(), api.brainProposals()])
      setLatest(l && l.ts ? l : null)
      setRuns(r)
      setDrift(props.filter(p => p.source === 'usage-agent' && p.status === 'pending'))
    } catch (e) { setErr(e.message) }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  return (
    <div className="wrap">
      {err && <div className="err">{err}</div>}

      <div className="panel full">
        <h3>Last usage-agent run</h3>
        {!latest && <p className="muted">No runs yet — run <code>python -m swingbot.selftest</code>.</p>}
        {latest && (
          <p>
            <b style={{ color: latest.green ? 'var(--green)' : 'var(--red)' }}>
              {latest.green ? 'GREEN' : 'RED'}</b>
            {' '}· {fmtTs(latest.ts)} · {latest.duration_s ?? '—'}s
            {' '}· sessions {latest.traces?.filter(t => t.ok).length ?? 0}/{latest.traces?.length ?? 0} ok
            {' '}· checks: {(latest.checks || []).map(c => `${c.name}${c.ok ? '✓' : '✗'}`).join(' ')}
          </p>
        )}
        {latest?.traces?.map(t => (
          <details key={t.session}>
            <summary style={{ cursor: 'pointer' }}>
              <span style={{ color: t.ok ? 'var(--green)' : 'var(--red)' }}>{t.ok ? '✓' : '✗'}</span>{' '}
              {t.session} ({t.steps?.filter(s => s.ok).length}/{t.steps?.length} steps, {t.duration_s}s)
            </summary>
            <ul style={{ listStyle: 'none', paddingLeft: 16 }}>
              {t.steps?.map((s, i) => <StepRow key={i} s={s} />)}
            </ul>
          </details>
        ))}
      </div>

      <div className="panel full">
        <h3>Drift findings ({drift.length})</h3>
        {drift.length === 0 && <p className="muted">No pending drift — docs and behavior agree.</p>}
        {drift.map(p => (
          <div key={p.id} className="panel" style={{ margin: '8px 0' }}>
            <b>{p.action}</b> · {p.target.doc} {p.target.section}
            <div style={{ fontSize: 12 }}><b>Expected:</b> {p.target.expected}</div>
            <div style={{ fontSize: 12 }}><b>Observed:</b> {p.target.observed}</div>
            <div style={{ fontSize: 12, color: 'var(--muted)' }}>{p.target.suggestion}</div>
            <button className="act danger" style={{ marginTop: 6 }}
              onClick={async () => { await api.brainDismiss(p.id); refresh() }}>Dismiss</button>
          </div>
        ))}
      </div>

      <div className="panel full">
        <h3>Run history</h3>
        <ul style={{ listStyle: 'none', padding: 0, fontSize: 12 }}>
          {runs.slice().reverse().map((r, i) => (
            <li key={i}>
              <span style={{ color: r.green ? 'var(--green)' : 'var(--red)' }}>●</span>{' '}
              {fmtTs(r.ts)} — {r.sessions.filter(s => s.ok).length}/{r.sessions.length} sessions ok,
              {' '}{r.drift_count} drift
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
