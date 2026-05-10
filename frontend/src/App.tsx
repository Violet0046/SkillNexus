import { Routes, Route, Link, useLocation } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import SkillList from './pages/SkillList'
import SkillDetail from './pages/SkillDetail'
import AnalysisList from './pages/AnalysisList'
import EvolutionPage from './pages/EvolutionPage'

const navItems = [
  { path: '/', label: 'Dashboard' },
  { path: '/skills', label: 'Skills' },
  { path: '/analysis', label: 'Analysis' },
  { path: '/evolution', label: 'Evolution' },
]

export default function App() {
  const location = useLocation()

  return (
    <div style={{ display: 'flex', minHeight: '100vh', fontFamily: 'system-ui, sans-serif' }}>
      {/* Sidebar */}
      <nav style={{
        width: 220,
        background: '#1a1a2e',
        color: '#eee',
        padding: '20px 0',
        display: 'flex',
        flexDirection: 'column',
      }}>
        <div style={{ padding: '0 20px 20px', borderBottom: '1px solid #333' }}>
          <h1 style={{ margin: 0, fontSize: 20, color: '#6c63ff' }}>SkillNexus</h1>
          <p style={{ margin: '4px 0 0', fontSize: 12, color: '#888' }}>Skill Evolution Platform</p>
        </div>
        <div style={{ padding: '10px 0' }}>
          {navItems.map(item => {
            const active = location.pathname === item.path ||
              (item.path !== '/' && location.pathname.startsWith(item.path))
            return (
              <Link
                key={item.path}
                to={item.path}
                style={{
                  display: 'block',
                  padding: '10px 20px',
                  color: active ? '#fff' : '#aaa',
                  background: active ? '#6c63ff' : 'transparent',
                  textDecoration: 'none',
                  fontSize: 14,
                  transition: 'all 0.2s',
                }}
              >
                {item.label}
              </Link>
            )
          })}
        </div>
      </nav>

      {/* Main content */}
      <main style={{ flex: 1, background: '#f5f5fa', padding: '24px 32px' }}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/skills" element={<SkillList />} />
          <Route path="/skills/:skillId" element={<SkillDetail />} />
          <Route path="/analysis" element={<AnalysisList />} />
          <Route path="/evolution" element={<EvolutionPage />} />
        </Routes>
      </main>
    </div>
  )
}
