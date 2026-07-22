import { HashRouter, Routes, Route, NavLink } from 'react-router-dom'
import { cn } from './lib/utils.js'
import Home from './pages/Home.jsx'
import Coins from './pages/Coins.jsx'
import SettingsScreen from './pages/SettingsScreen.jsx'

function BottomNav() {
  const link = ({ isActive }) =>
    cn('flex-1 rounded-md px-3 py-2 text-center text-sm font-medium text-muted-foreground',
       isActive && 'bg-accent text-foreground')
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 mx-auto flex max-w-md items-center gap-1 border-t border-border bg-background/90 p-2 backdrop-blur">
      <NavLink to="/" end className={link}>Home</NavLink>
      <NavLink to="/coins" className={link}>Coins</NavLink>
      <NavLink to="/settings" className={link}>Settings</NavLink>
    </nav>
  )
}

export default function App() {
  return (
    <HashRouter>
      <div className="pb-16">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/coins" element={<Coins />} />
          <Route path="/settings" element={<SettingsScreen />} />
          <Route path="*" element={<Home />} />
        </Routes>
      </div>
      <BottomNav />
    </HashRouter>
  )
}
