import { useEffect, useState } from 'react'
import { getStats, getTopSkills, getEvolutionCandidates, discoverSkills } from '../api/client'

export default function Dashboard() {
  const [stats, setStats] = useState<any>(null)
  const [topSkills, setTopSkills] = useState<any[]>([])
  const [candidates, setCandidates] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      getStats().catch(() => null),
      getTopSkills(5).catch(() => []),
      getEvolutionCandidates(5).catch(() => []),
    ]).then(([s, t, c]) => {
      setStats(s)
      setTopSkills(t)
      setCandidates(c)
      setLoading(false)
    })
  }, [])

  if (loading) return <div>Loading dashboard...</div>

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>Dashboard</h2>

      {/* Stats cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 24 }}>
        <StatCard label="Total Skills" value={stats?.total_skills ?? 0} color="#6c63ff" />
        <StatCard label="Active Skills" value={stats?.active_skills ?? 0} color="#2ecc71" />
        <StatCard label="Total Analyses" value={stats?.total_analyses ?? 0} color="#3498db" />
        <StatCard label="Top Effective Rate" value={
          topSkills.length > 0 ? `${(topSkills[0]?.effective_rate * 100).toFixed(0)}%` : 'N/A'
        } color="#e67e22" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        {/* Top skills */}
        <div style={cardStyle}>
          <h3 style={{ marginTop: 0 }}>Top Performing Skills</h3>
          {topSkills.length === 0 ? (
            <p style={{ color: '#888' }}>No skill data yet</p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #eee' }}>
                  <th style={thStyle}>Skill</th>
                  <th style={thStyle}>Applied</th>
                  <th style={thStyle}>Effective</th>
                </tr>
              </thead>
              <tbody>
                {topSkills.map((s: any) => (
                  <tr key={s.skill_id} style={{ borderBottom: '1px solid #f0f0f0' }}>
                    <td style={tdStyle}>{s.name}</td>
                    <td style={tdStyle}>{(s.applied_rate * 100).toFixed(0)}%</td>
                    <td style={tdStyle}>
                      <span style={{
                        color: s.effective_rate > 0.7 ? '#2ecc71' : s.effective_rate > 0.4 ? '#e67e22' : '#e74c3c',
                        fontWeight: 600,
                      }}>
                        {(s.effective_rate * 100).toFixed(0)}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Evolution candidates */}
        <div style={cardStyle}>
          <h3 style={{ marginTop: 0 }}>Evolution Candidates</h3>
          {candidates.length === 0 ? (
            <p style={{ color: '#888' }}>No candidates right now</p>
          ) : (
            candidates.map((c: any) => (
              <div key={c.task_id} style={{ padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}>
                <div style={{ fontWeight: 600, fontSize: 13 }}>{c.task_id}</div>
                <div style={{ fontSize: 12, color: '#666', marginTop: 2 }}>
                  {c.execution_note?.slice(0, 100)}
                </div>
                <div style={{ fontSize: 11, color: '#999', marginTop: 4 }}>
                  {c.evolution_suggestions?.length ?? 0} suggestion(s)
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Quick actions */}
      <div style={{ marginTop: 24 }}>
        <button
          onClick={async () => {
            const result = await discoverSkills()
            alert(`Discovered ${result.discovered} skill(s)`)
          }}
          style={btnStyle}
        >
          Discover Skills
        </button>
      </div>
    </div>
  )
}

function StatCard({ label, value, color }: { label: string; value: any; color: string }) {
  return (
    <div style={{ ...cardStyle, borderTop: `3px solid ${color}` }}>
      <div style={{ fontSize: 28, fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: 13, color: '#888', marginTop: 4 }}>{label}</div>
    </div>
  )
}

const cardStyle: React.CSSProperties = {
  background: '#fff',
  borderRadius: 8,
  padding: 20,
  boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
}

const thStyle: React.CSSProperties = { textAlign: 'left', padding: '8px 4px', fontSize: 12, color: '#888' }
const tdStyle: React.CSSProperties = { padding: '8px 4px', fontSize: 13 }

const btnStyle: React.CSSProperties = {
  background: '#6c63ff',
  color: '#fff',
  border: 'none',
  borderRadius: 6,
  padding: '10px 20px',
  cursor: 'pointer',
  fontSize: 14,
}
