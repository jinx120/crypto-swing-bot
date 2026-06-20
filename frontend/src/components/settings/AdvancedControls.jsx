import { useEffect, useState } from 'react'
import { api } from '../../api.js'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card.jsx'
import { Button } from '../ui/button.jsx'

export default function AdvancedControls() {
  const [strategies, setStrategies] = useState([])
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const load = async () => { try { setStrategies(await api.strategies()) } catch (e) { setErr(e.message) } }
  useEffect(() => { load() }, [])

  const ctl = async (action) => { setErr(''); setMsg(''); try { await api.control(action); setMsg(`${action} ok`) } catch (e) { setErr(e.message) } }
  const toggleLive = async (s) => { setErr(''); try { await api.setLiveEligible(s.name, !s.live_eligible); await load() } catch (e) { setErr(e.message) } }

  return (
    <Card>
      <CardHeader><CardTitle>Advanced controls</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        {err && <div className="rounded-md bg-down/15 px-3 py-2 text-sm text-down">{err}</div>}
        {msg && <div className="rounded-md bg-up/15 px-3 py-2 text-sm text-up">{msg}</div>}
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => ctl('pause')}>Pause</Button>
          <Button size="sm" variant="outline" onClick={() => ctl('resume')}>Resume</Button>
          <Button size="sm" variant="danger" onClick={() => ctl('halt')}>Halt (kill switch)</Button>
        </div>
        <div>
          <div className="mb-2 text-xs font-medium uppercase text-muted-foreground">Live eligibility</div>
          {strategies.length === 0 ? <div className="text-sm text-muted-foreground">No strategies.</div> : (
            <div className="space-y-1">
              {strategies.map((s) => (
                <div key={s.name} className="flex items-center justify-between text-sm">
                  <span>{s.label || s.name} <span className="text-muted-foreground">({s.symbol})</span></span>
                  <Button size="sm" variant={s.live_eligible ? 'default' : 'outline'} onClick={() => toggleLive(s)}>
                    {s.live_eligible ? 'live-eligible ✓' : 'mark live-eligible'}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
