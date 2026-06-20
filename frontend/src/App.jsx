import { HashRouter, Routes, Route, NavLink } from 'react-router-dom'
import { Activity, Settings as SettingsIcon } from 'lucide-react'
import { cn } from './lib/utils.js'
import MissionControl from './pages/MissionControl.jsx'
import CoinDetail from './pages/CoinDetail.jsx'
import Settings from './pages/Settings.jsx'

function TopNav() {
  const link = ({ isActive }) =>
    cn('rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground hover:text-foreground',
       isActive && 'bg-accent text-foreground')
  return (
    <nav className="sticky top-0 z-40 flex items-center gap-2 border-b border-border bg-background/80 px-4 py-2 backdrop-blur">
      <span className="mr-2 flex items-center gap-1.5 font-semibold">
        <Activity className="h-4 w-4 text-primary" /> SwingBot
      </span>
      <NavLink to="/" end className={link}>Mission Control</NavLink>
      <NavLink to="/settings" className={link}>
        <span className="inline-flex items-center gap-1"><SettingsIcon className="h-3.5 w-3.5" /> Settings</span>
      </NavLink>
    </nav>
  )
}

export default function App() {
  return (
    <HashRouter>
      <TopNav />
      <Routes>
        <Route path="/" element={<MissionControl />} />
        <Route path="/coin/:name" element={<CoinDetail />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<MissionControl />} />
      </Routes>
    </HashRouter>
  )
}
