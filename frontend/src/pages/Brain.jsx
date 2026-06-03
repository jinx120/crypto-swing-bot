import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'

export default function Brain() {
  const [proposals, setProposals] = useState([])
  const [issues, setIssues] = useState([])
  const [settings, setSettings] = useState({})
  const [webhook, setWebhook] = useState('')
  const [webhookConfigured, setWebhookConfigured] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [p, i, s, w] = await Promise.all([
        api.brainProposals(), api.brainIssues(),
        api.portfolioSettings(), api.brainWebhookStatus(),
      ])
      setProposals(p); setIssues(i); setSettings(s)
      setWebhookConfigured(!!w.configured)
    } catch (e) { setErr(e.message) }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const runRecommend = async () => {
    setBusy(true); setErr('')
    try {
      await api.brainRecommend()
      setTimeout(async () => { await refresh(); setBusy(false) }, 1800)
    } catch (e) { setErr(e.message); setBusy(false) }
  }

  const toggle = async (key) => {
    try { setSettings(await api.setPortfolioSettings({ [key]: !settings[key] })) }
    catch (e) { setErr(e.message) }
  }

  const saveWebhook = async () => {
    try {
      const r = await api.setBrainWebhook(webhook)
      setWebhookConfigured(!!r.configured); setWebhook('')
    } catch (e) { setErr(e.message) }
  }

  return (
    <div className="brain-page">
      <header className="brain-header">
        <h2>Decision Brain</h2>
        <button onClick={runRecommend} disabled={busy}>
          {busy ? 'Thinking…' : 'Recommend now'}
        </button>
        <label>
          <input type="checkbox" checked={!!settings.brain_autonomous_mode}
            onChange={() => toggle('brain_autonomous_mode')} /> Autonomous
        </label>
        <label>
          <input type="checkbox" checked={!!settings.brain_auto_recommend}
            onChange={() => toggle('brain_auto_recommend')} /> Auto after discovery
        </label>
      </header>

      {err && <div className="error">{err}</div>}

      <section className="proposals">
        {proposals.length === 0 && <p>No proposals yet. Click “Recommend now”.</p>}
        {proposals.map((p) => (
          <div key={p.id} className={`proposal ${p.guardrail_status} ${p.status}`}>
            <div className="title">{p.action} · {JSON.stringify(p.target)}</div>
            <div className="meta">
              confidence {Math.round((p.confidence || 0) * 100)}% · {p.guardrail_status}
              {p.guardrail_reason ? ` (${p.guardrail_reason})` : ''} · {p.status}
            </div>
            <div className="rationale">{p.rationale}</div>
            {p.status === 'pending' && p.guardrail_status === 'approved' && (
              <button onClick={async () => { await api.brainApply(p.id); refresh() }}>Apply</button>
            )}
            {p.status === 'pending' && (
              <button onClick={async () => { await api.brainDismiss(p.id); refresh() }}>Dismiss</button>
            )}
          </div>
        ))}
      </section>

      <section className="brain-webhook">
        <h3>Discord webhook {webhookConfigured ? '(configured)' : '(not set)'}</h3>
        <input type="password" placeholder="https://discord.com/api/webhooks/…"
          value={webhook} onChange={(e) => setWebhook(e.target.value)} />
        <button onClick={saveWebhook} disabled={!webhook}>Save</button>
      </section>

      <section className="issues">
        <h3>Issues &amp; shortcomings</h3>
        {issues.length === 0 && <p>No issues logged.</p>}
        <ul>{issues.slice().reverse().map((it, i) => (
          <li key={i}>[{it.kind}] {it.detail}</li>))}</ul>
      </section>
    </div>
  )
}
