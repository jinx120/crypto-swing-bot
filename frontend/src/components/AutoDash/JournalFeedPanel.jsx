import { api } from '../../api.js'
import usePolling from './usePolling.js'

export default function JournalFeedPanel() {
  const { data: events } = usePolling(api.auto.journal, 10000)
  const list = events || []
  return (
    <div className="panel">
      <h3>Decision journal</h3>
      <div style={{ maxHeight: 280, overflowY: 'auto' }}>
        {list.length === 0 ? <div>No events yet.</div> : list.map((e, i) => (
          <div key={i} style={{ padding: '4px 0', borderBottom: '1px solid #2a2a2a' }}>
            <span style={{ opacity: 0.6 }}>{(e.ts || '').replace('T', ' ').slice(0, 16)} </span>
            <b>{e.kind}</b> — {e.reason}
          </div>
        ))}
      </div>
    </div>
  )
}
