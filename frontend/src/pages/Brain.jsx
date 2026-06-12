import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'

function ConfBar({ value }) {
  const pct = Math.round((value || 0) * 100)
  const color = pct >= 80 ? 'var(--green)' : pct >= 60 ? 'var(--amber)' : 'var(--red)'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 4, background: 'var(--glass-border)', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 4, transition: 'width .4s' }} />
      </div>
      <span style={{ fontSize: 11, color, fontVariantNumeric: 'tabular-nums', minWidth: 30 }}>{pct}%</span>
    </div>
  )
}

const STATUS_COLOR = { approved: 'var(--green)', blocked: 'var(--red)', pending: 'var(--amber)' }
const NON_EXECUTABLE = ['ui_fix', 'doc_fix']

export default function Brain() {
  const [proposals, setProposals] = useState([])
  const [issues, setIssues]       = useState([])
  const [settings, setSettings]   = useState({})
  const [webhook, setWebhook]     = useState('')
  const [webhookOk, setWebhookOk] = useState(false)
  const [busy, setBusy]           = useState(false)
  const [err, setErr]             = useState('')

  const refresh = useCallback(async () => {
    try {
      const [p, i, s, w] = await Promise.all([
        api.brainProposals(), api.brainIssues(),
        api.portfolioSettings(), api.brainWebhookStatus(),
      ])
      setProposals(p); setIssues(i); setSettings(s)
      setWebhookOk(!!w.configured)
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

  const saveConfig = async (patch) => {
    try { setSettings(await api.setPortfolioSettings(patch)) }
    catch (e) { setErr(e.message) }
  }

  const saveWebhook = async () => {
    try {
      const r = await api.setBrainWebhook(webhook)
      setWebhookOk(!!r.configured); setWebhook('')
    } catch (e) { setErr(e.message) }
  }

  const pendingCount   = proposals.filter(p => p.status === 'pending').length
  const approvedCount  = proposals.filter(p => p.guardrail_status === 'approved').length

  return (
    <div className="brain-page">

      {/* ── Header ── */}
      <div className="brain-hero panel">
        <div className="brain-hero-left">
          <h2 className="brain-title">Decision Brain</h2>
          <div className="brain-meta">
            <span className="brain-chip">{settings.brain_model || '—'}</span>
            <span className="brain-url" title={settings.brain_ollama_url}>
              {settings.brain_ollama_url || '—'}
            </span>
          </div>
        </div>
        <div className="brain-hero-right">
          <label className="brain-toggle">
            <input type="checkbox" checked={!!settings.brain_autonomous_mode}
              onChange={() => toggle('brain_autonomous_mode')} />
            <span>Autonomous</span>
          </label>
          <label className="brain-toggle">
            <input type="checkbox" checked={!!settings.brain_auto_recommend}
              onChange={() => toggle('brain_auto_recommend')} />
            <span>Auto after discovery</span>
          </label>
          <button className="act brain-run-btn" onClick={runRecommend} disabled={busy}>
            {busy ? 'Thinking…' : '▶ Recommend now'}
          </button>
        </div>
      </div>

      {err && <div className="error brain-err">{err}</div>}

      {/* ── Stats row ── */}
      {proposals.length > 0 && (
        <div className="brain-stats">
          <div className="brain-stat"><span className="brain-stat-val">{proposals.length}</span>total</div>
          <div className="brain-stat"><span className="brain-stat-val" style={{ color: 'var(--amber)' }}>{pendingCount}</span>pending</div>
          <div className="brain-stat"><span className="brain-stat-val" style={{ color: 'var(--green)' }}>{approvedCount}</span>approved</div>
        </div>
      )}

      {/* ── Proposals ── */}
      <div className="brain-proposals">
        {proposals.length === 0 && (
          <div className="panel brain-empty">
            <div className="brain-empty-icon">🧠</div>
            <p>No proposals yet. Click <strong>Recommend now</strong> to ask the brain for suggestions.</p>
          </div>
        )}
        {proposals.map((p) => (
          <div key={p.id} className={`panel brain-proposal gs-${p.guardrail_status} st-${p.status}`}>
            <div className="bp-top">
              <span className="bp-action">{p.action}</span>
              <span className="bp-target">{JSON.stringify(p.target)}</span>
              <span className="bp-gs" style={{ color: STATUS_COLOR[p.guardrail_status] || 'var(--muted)' }}>
                {p.guardrail_status}
              </span>
              <span className="bp-status" style={{ color: p.status === 'applied' ? 'var(--green)' : 'var(--muted)' }}>
                {p.status}
              </span>
            </div>
            <ConfBar value={p.confidence} />
            {p.guardrail_reason && (
              <div className="bp-reason">{p.guardrail_reason}</div>
            )}
            <div className="bp-rationale">{p.rationale}</div>
            {p.status === 'pending' && (
              <div className="bp-actions">
                {p.guardrail_status === 'approved' && !NON_EXECUTABLE.includes(p.action) && (
                  <button className="act" onClick={async () => { await api.brainApply(p.id); refresh() }}>Apply</button>
                )}
                <button className="act danger" onClick={async () => { await api.brainDismiss(p.id); refresh() }}>Dismiss</button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* ── Config + Webhook row ── */}
      <div className="brain-bottom-row">
        <div className="panel">
          <h3>Model &amp; connection</h3>
          <div className="brain-fields">
            <label>Model
              <input type="text" defaultValue={settings.brain_model || ''}
                onBlur={(e) => saveConfig({ brain_model: e.target.value })} />
            </label>
            <label>Ollama URL
              <input type="text" defaultValue={settings.brain_ollama_url || ''}
                placeholder="http://172.17.0.1:11434"
                onBlur={(e) => saveConfig({ brain_ollama_url: e.target.value })} />
            </label>
            <label>Confidence threshold
              <input type="number" step="0.05" min="0" max="1"
                defaultValue={settings.brain_confidence_threshold ?? 0.7}
                onBlur={(e) => saveConfig({ brain_confidence_threshold: parseFloat(e.target.value) })} />
            </label>
            <label>Timeout (s)
              <input type="number" step="1" min="1"
                defaultValue={settings.brain_timeout_s ?? 30}
                onBlur={(e) => saveConfig({ brain_timeout_s: parseInt(e.target.value, 10) })} />
            </label>
          </div>
        </div>

        <div className="panel">
          <h3>Discord webhook
            <span style={{ marginLeft: 8, color: webhookOk ? 'var(--green)' : 'var(--muted)', fontSize: 11 }}>
              {webhookOk ? '● configured' : '○ not set'}
            </span>
          </h3>
          <div className="brain-webhook-row">
            <input type="password" placeholder="https://discord.com/api/webhooks/…"
              value={webhook} onChange={(e) => setWebhook(e.target.value)} />
            <button className="act" onClick={saveWebhook} disabled={!webhook}>Save</button>
          </div>

          <h3 style={{ marginTop: 20 }}>Issues &amp; shortcomings</h3>
          {issues.length === 0
            ? <p style={{ color: 'var(--muted)', fontSize: 12, margin: 0 }}>No issues logged.</p>
            : <ul className="brain-issues">
                {issues.slice().reverse().map((it, i) => (
                  <li key={i}><span className="bi-kind">[{it.kind}]</span> {it.detail}</li>
                ))}
              </ul>
          }
        </div>
      </div>
    </div>
  )
}
